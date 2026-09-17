"""The generate-insights job: statistics from the stored marks, a narrative from the model, both
saved on the assignment's `assignment_insights` row. Enqueued with payload {"class_assignment_id": n}
and dedupe key insights:{id}, so one assignment generates one report at a time.

Nothing a student is called ever reaches the model: the statistics are stripped of names and ids
before they go in, and the samples carry register numbers by construction."""
from typing import Any, Callable, Dict, Optional

from sms.agents.insights import build_insights
from sms.memory.db import Database
from sms.memory.metrics_hook import wire_metrics
from sms.providers.client import build_client
from sms.providers.errors import error_message
from sms.providers.ratelimit import BucketPool, RateLimitedAgent, TokenBucket
from sms.providers.registry import get_provider
from sms.providers.settings import SettingsStore
from sms.schemas.insights import InsightsInput, Sample
from sms.web.services.assignments import get_template
from sms.web.services.class_assignments import get_class_assignment
from sms.web.services.insights import (compute_stats, dedupe_key, load_insights, select_samples, upsert_insights)
from sms.worker.jobs import JobStore

INSIGHTS_KIND = "insights"
NOTHING_MARKED = "Nothing marked yet"


def _default_agent_factory(*, db: Database, settings, bucket: TokenBucket) -> Any:
    client = build_client(settings.provider, settings.api_key, base_url=settings.base_url)
    params = get_provider(settings.provider).api_params
    agent = build_insights(client=client, model=settings.model, model_api_parameters=params)
    wire_metrics(db=db, agents={"insights": agent})
    return RateLimitedAgent(agent, bucket)


def enqueue_insights(jobs: JobStore, caid: int) -> Optional[int]:
    """Queue a report for this assignment unless one is already queued or running. Returns the job
    id, or None when one was already in flight."""
    return jobs.enqueue_unique(INSIGHTS_KIND, {"class_assignment_id": caid}, dedupe_key=dedupe_key(caid))


def _anonymous(stats: Dict[str, Any]) -> Dict[str, Any]:
    """The statistics with every student reduced to their register number."""
    return {**stats, "students": [{k: v for k, v in s.items() if k not in ("name", "student_id")}
                                  for s in stats.get("students") or []]}


def run_insights_job(db: Database, jobs: JobStore, settings_store: SettingsStore, caid: int,
                     bucket: Optional[TokenBucket] = None, bucket_pool: Optional[BucketPool] = None,
                     agent_factory: Optional[Callable[..., Any]] = None) -> dict:
    """Recompute an assignment's statistics and rewrite its narrative. Returns the report (or the
    statistics when there is nothing to write about yet). A failed model call keeps the previous
    report, records the error on the row and re-raises for the worker's retry/fail handling."""
    rows = db.query("SELECT * FROM class_assignments WHERE id = :id", {"id": caid})
    if not rows:
        raise ValueError(f"class assignment {caid} not found")
    ca = get_class_assignment(db, rows[0]["class_id"], caid)
    stats = compute_stats(db, jobs, ca)
    prev = load_insights(db, caid)
    if stats["n_marked"] == 0:
        upsert_insights(db, caid, stats=stats, report=prev["report"] if prev else None, n_marked=0,
                        provider=None, model=None, error=NOTHING_MARKED)
        return stats
    tpl = get_template(db, ca["template_id"])
    settings = settings_store.for_template(tpl)
    # Everything that can go wrong from here on — a missing key included — is worth showing on the
    # panel, so it all runs inside the handler that records `error` on the row.
    try:
        if not settings.has_key:
            raise RuntimeError("No API key configured — add one under Settings")
        if bucket_pool is not None:
            bucket = bucket_pool.get(settings.provider, settings.rpm_limit)
        inp = InsightsInput(assignment_title=ca["title"], subject=ca["subject"] or "math",
                            scheme_kind=ca["scheme_kind"] or "criteria", stats=_anonymous(stats),
                            samples=[Sample(**s) for s in select_samples(db, jobs, ca, stats)])
        agent = (agent_factory or _default_agent_factory)(db=db, settings=settings,
                                                          bucket=bucket or TokenBucket(settings.rpm_limit))
        report = agent.run(inp)
    except Exception as e:  # noqa: BLE001 - recorded on the row, then handed back to the worker
        upsert_insights(db, caid, stats=stats, report=prev["report"] if prev else None,
                        n_marked=stats["n_marked"], provider=settings.provider, model=settings.model,
                        error=error_message(e))
        raise
    upsert_insights(db, caid, stats=stats, report=report.model_dump(), n_marked=stats["n_marked"],
                    provider=settings.provider, model=settings.model, error=None)
    return report.model_dump()

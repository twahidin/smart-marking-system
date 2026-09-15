from typing import Any, Callable, Optional

from sms.agents.reflection import build_reflection
from sms.learning.reflection_job import run_reflection
from sms.memory.db import Database
from sms.memory.metrics_hook import wire_metrics
from sms.pipeline.router import SubjectRouter
from sms.providers.client import build_client
from sms.providers.errors import error_message
from sms.providers.ratelimit import RateLimitedAgent, TokenBucket
from sms.providers.registry import get_provider
from sms.providers.settings import SettingsStore


def _default_agent_factory(*, db: Database, settings, bucket: TokenBucket) -> Any:
    client = build_client(settings.provider, settings.api_key, base_url=settings.base_url)
    params = get_provider(settings.provider).api_params
    agent = build_reflection(client=client, model=settings.model, model_api_parameters=params)
    wire_metrics(db=db, agents={"reflection": agent})
    return RateLimitedAgent(agent, bucket)


def open_reflection_run(db: Database, subject: str, lookback_days: int) -> int:
    """Create the reflection_runs row for a job. The worker does this once per job so retries
    update the same row instead of leaving one failed row per attempt."""
    return db.insert("INSERT INTO reflection_runs (subject, lookback_days) VALUES (:s, :d) RETURNING id",
                     {"s": SubjectRouter().resolve(subject), "d": int(lookback_days)})


def run_reflect_job(db: Database, settings_store: SettingsStore, subject: str, lookback_days: int,
                    bucket: Optional[TokenBucket] = None,
                    agent_factory: Optional[Callable[..., Any]] = None,
                    run_id: Optional[int] = None) -> int:
    """Run reflection over recent teacher corrections for one subject and record the outcome on
    a `reflection_runs` row (the one given, or a new one). Returns the number of proposed rubric
    notes. Every failure — missing key, client construction, the model call — is written to the
    row's `error` and re-raised so the worker's retry/fail handling applies."""
    subject = SubjectRouter().resolve(subject)
    if run_id is None:
        run_id = open_reflection_run(db, subject, lookback_days)
    else:
        # A retry of an earlier attempt: clear what that attempt left behind.
        db.execute("UPDATE reflection_runs SET error = NULL, finished_at = NULL WHERE id = :id", {"id": run_id})
    try:
        settings = settings_store.load()
        if not settings.has_key:
            raise RuntimeError("No API key configured — add one under Settings")
        factory = agent_factory or _default_agent_factory
        agent = factory(db=db, settings=settings, bucket=bucket or TokenBucket(settings.rpm_limit))
        proposed = run_reflection(db, agent, subject, int(lookback_days))
    except Exception as e:  # noqa: BLE001 - recorded on the run, then handed back to the worker
        db.execute("UPDATE reflection_runs SET finished_at = CURRENT_TIMESTAMP, error = :err WHERE id = :id",
                   {"err": error_message(e), "id": run_id})
        raise
    db.execute("UPDATE reflection_runs SET finished_at = CURRENT_TIMESTAMP, proposed_notes = :n WHERE id = :id",
               {"n": proposed, "id": run_id})
    return proposed

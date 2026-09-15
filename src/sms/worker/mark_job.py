from typing import Any, Callable, Optional

from sms.agents.extractor import build_extractor
from sms.agents.feedback import build_feedback
from sms.agents.marker import build_marker
from sms.agents.reviewer import build_reviewer
from sms.memory.db import Database
from sms.memory.metrics_hook import wire_metrics
from sms.pipeline.marking_pipeline import MarkingPipeline
from sms.providers.client import build_client
from sms.providers.ratelimit import RateLimitedAgent, TokenBucket
from sms.providers.registry import get_provider
from sms.providers.settings import SettingsStore
from sms.schemas.marking import Rubric
from sms.storage import PageStorage


def _default_pipeline_factory(*, db: Database, settings, subject: str,
                              bucket: Optional[TokenBucket] = None) -> MarkingPipeline:
    client = build_client(settings.provider, settings.api_key, base_url=settings.base_url)
    params = get_provider(settings.provider).api_params
    bucket = bucket or TokenBucket(settings.rpm_limit)
    agents = {
        "extractor": build_extractor(client=client, model=settings.effective_extractor_model, model_api_parameters=params),
        "marker": build_marker(client=client, model=settings.model, subject=subject, db=db, model_api_parameters=params),
        "reviewer": build_reviewer(client=client, model=settings.model, subject=subject, db=db, model_api_parameters=params),
        "feedback": build_feedback(client=client, model=settings.model, model_api_parameters=params),
    }
    wire_metrics(db=db, agents=agents)
    limited = {k: RateLimitedAgent(v, bucket) for k, v in agents.items()}
    return MarkingPipeline(db=db, subject=subject, confidence_threshold=settings.confidence_threshold, **limited)


def run_mark_job(db: Database, storage: PageStorage, settings_store: SettingsStore, submission_id: int,
                 pipeline_factory: Optional[Callable[..., Any]] = None,
                 bucket: Optional[TokenBucket] = None) -> None:
    rows = db.query("SELECT * FROM submissions WHERE id = :id", {"id": submission_id})
    if not rows:
        raise ValueError(f"submission {submission_id} not found")
    sub = rows[0]
    settings = settings_store.load()
    if not settings.has_key:
        raise RuntimeError("No API key configured — add one under Settings")
    pages = db.query("SELECT storage_path FROM pages WHERE submission_id = :id ORDER BY page_index",
                     {"id": submission_id})
    images = [storage.read(p["storage_path"]) for p in pages]
    rubric = Rubric.model_validate_json(sub["rubric_json"])
    factory = pipeline_factory or _default_pipeline_factory
    pipeline = factory(db=db, settings=settings, subject=sub["subject"], bucket=bucket)
    result = pipeline.run(images=images, assignment_context=sub["context"] or "Student script",
                          rubric=rubric, submission_id=submission_id)
    status = "needs_you" if result.escalations else "done"
    db.execute("UPDATE submissions SET status = :st, run_id = :rid, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
               {"st": status, "rid": result.run_id, "id": submission_id})

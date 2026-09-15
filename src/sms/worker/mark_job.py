import json
import logging
from typing import Any, Callable, Optional

from sms.agents.extractor import build_extractor
from sms.agents.feedback import build_feedback
from sms.agents.marker import build_marker
from sms.agents.marker_v2 import build_marker_v2
from sms.agents.reviewer import build_reviewer
from sms.agents.reviewer_v2 import build_reviewer_v2
from sms.memory.db import Database
from sms.memory.metrics_hook import wire_metrics
from sms.pipeline.marking_pipeline import MarkingPipeline
from sms.pipeline.marking_pipeline_v2 import MarkingPipelineV2
from sms.providers.client import build_client
from sms.providers.ratelimit import RateLimitedAgent, TokenBucket
from sms.providers.registry import get_provider
from sms.providers.settings import SettingsStore
from sms.schemas.marking import Rubric
from sms.storage import PageStorage
from sms.web.services.pages_cleanup import delete_submission_pages

log = logging.getLogger("sms.worker")


V2_KINDS = ("mark_scheme", "rubric")


def _default_pipeline_factory(*, db: Database, settings, subject: str, bucket: Optional[TokenBucket] = None,
                              kind: Optional[str] = None) -> Any:
    """v1 (criteria rubric) pipeline by default; the per-part v2 pipeline when `kind` is a scheme kind."""
    client = build_client(settings.provider, settings.api_key, base_url=settings.base_url)
    params = get_provider(settings.provider).api_params
    bucket = bucket or TokenBucket(settings.rpm_limit)
    extractor = build_extractor(client=client, model=settings.effective_extractor_model, model_api_parameters=params)
    feedback = build_feedback(client=client, model=settings.model, model_api_parameters=params)
    if kind in V2_KINDS:
        agents = {
            "extractor": extractor,
            "marker": build_marker_v2(client=client, model=settings.model, kind=kind, subject=subject, db=db,
                                      model_api_parameters=params),
            "reviewer": build_reviewer_v2(client=client, model=settings.model, kind=kind, subject=subject, db=db,
                                          model_api_parameters=params),
            "feedback": feedback,
        }
    else:
        agents = {
            "extractor": extractor,
            "marker": build_marker(client=client, model=settings.model, subject=subject, db=db, model_api_parameters=params),
            "reviewer": build_reviewer(client=client, model=settings.model, subject=subject, db=db, model_api_parameters=params),
            "feedback": feedback,
        }
    wire_metrics(db=db, agents=agents)
    limited = {k: RateLimitedAgent(v, bucket) for k, v in agents.items()}
    if kind in V2_KINDS:
        return MarkingPipelineV2(db=db, kind=kind, confidence_threshold=settings.confidence_threshold, **limited)
    return MarkingPipeline(db=db, subject=subject, confidence_threshold=settings.confidence_threshold, **limited)


KIND_NAMES = {"criteria": "quick mark", "mark_scheme": "mark scheme", "rubric": "rubric"}


def _v2_template(db: Database, assignment_id: Optional[int], uploaded_kind: Optional[str]) -> Optional[dict]:
    """The submission's assignment as the v2 pipeline's template dict when it has a mark scheme or a
    rubric; None (v1 path) for criteria templates or no assignment. A script whose assignment has been
    deleted, or retyped since it was uploaded (`uploaded_kind`, NULL on legacy rows), is refused with a
    non-retryable error rather than marked with the wrong pipeline — and then having its pages deleted."""
    if assignment_id is None:
        return None
    rows = db.query("SELECT subject, context, scheme_kind, questions_json, scheme_json FROM assignment_templates "
                    "WHERE id = :id", {"id": assignment_id})
    if not rows:
        raise RuntimeError("The assignment this script was uploaded for has been deleted — upload it again against "
                           "a current assignment")
    t = rows[0]
    if uploaded_kind is not None and t["scheme_kind"] != uploaded_kind:
        raise RuntimeError(f"This script was uploaded against a {KIND_NAMES.get(uploaded_kind, uploaded_kind)} assignment "
                           f"that is now a {KIND_NAMES.get(t['scheme_kind'], t['scheme_kind'])} — upload it again against "
                           "a current assignment")
    if t["scheme_kind"] not in V2_KINDS:
        return None
    return {
        "subject": t["subject"], "context": t["context"] or "", "scheme_kind": t["scheme_kind"],
        "questions": json.loads(t["questions_json"]) if t["questions_json"] else [],
        "scheme": json.loads(t["scheme_json"]) if t["scheme_json"] else [],
    }


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
    pages = db.query("SELECT storage_path, deleted_at FROM pages WHERE submission_id = :id AND kind = 'student' "
                     "ORDER BY page_index", {"id": submission_id})
    if any(p["deleted_at"] is not None for p in pages):
        raise RuntimeError("This script's pages were deleted after marking, so it cannot be marked again")
    images = [storage.read(p["storage_path"]) for p in pages]
    factory = pipeline_factory or _default_pipeline_factory
    template = _v2_template(db, sub.get("assignment_id"), sub.get("scheme_kind"))
    if template is not None:
        # the assignment's subject drives prompts/providers and the run row; the pipeline reads the same key
        pipeline = factory(db=db, settings=settings, subject=template["subject"], bucket=bucket, kind=template["scheme_kind"])
        result = pipeline.run(images=images, template=template, submission_id=submission_id)
    else:
        rubric = Rubric.model_validate_json(sub["rubric_json"])
        pipeline = factory(db=db, settings=settings, subject=sub["subject"], bucket=bucket)
        result = pipeline.run(images=images, assignment_context=sub["context"] or "Student script",
                              rubric=rubric, submission_id=submission_id)
    status = "needs_you" if result.escalations else "done"
    db.execute("UPDATE submissions SET status = :st, run_id = :rid, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
               {"st": status, "rid": result.run_id, "id": submission_id})
    if status == "done":
        # Marking is finished and recorded: a deletion failure (volume hiccup) is logged rather than
        # failing the job — the worker's hourly sweep deletes the pages later.
        try:
            delete_submission_pages(db, storage, submission_id)
        except Exception:  # noqa: BLE001
            log.exception("could not delete the pages of submission %s after marking", submission_id)

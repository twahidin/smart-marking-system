"""Worker jobs that turn an assignment's uploaded pages into structured JSON:
`paper_extract` (question paper -> questions_json) and `scheme_extract` (mark scheme / rubric pages ->
scheme_json). Both are enqueued with payload {"template_id": n} and dedupe keys paper:{id} / scheme:{id}.
Failures are recorded on the job by the worker; nothing else keeps state."""
import json
from typing import Any, Callable, List, Optional

from sms.agents.paper_extractor import build_paper_extractor
from sms.agents.scheme_extractor import build_scheme_extractor
from sms.memory.db import Database
from sms.memory.metrics_hook import wire_metrics
from sms.pipeline.marking_pipeline import image_from_bytes
from sms.providers.client import build_client
from sms.providers.ratelimit import BucketPool, RateLimitedAgent, TokenBucket
from sms.providers.registry import get_provider
from sms.providers.settings import SettingsStore
from sms.schemas.scheme import PaperExtractInput, Question, SchemeExtractInput
from sms.storage import PageStorage

PAPER_KIND = "paper_extract"
SCHEME_KIND = "scheme_extract"


def dedupe_key(what: str, template_id: int) -> str:
    """'paper' / 'scheme' -> the dedupe key shared by the API (enqueue) and the status endpoint."""
    return f"{what}:{template_id}"


def _default_paper_factory(*, db: Database, settings, bucket: TokenBucket) -> Any:
    client = build_client(settings.provider, settings.api_key, base_url=settings.base_url)
    params = get_provider(settings.provider).api_params
    agent = build_paper_extractor(client=client, model=settings.effective_extractor_model, model_api_parameters=params)
    wire_metrics(db=db, agents={"paper_extractor": agent})
    return RateLimitedAgent(agent, bucket)


def _default_scheme_factory(*, db: Database, settings, bucket: TokenBucket, kind: str,
                            questions: List[Question]) -> Any:
    client = build_client(settings.provider, settings.api_key, base_url=settings.base_url)
    params = get_provider(settings.provider).api_params
    agent = build_scheme_extractor(client=client, model=settings.effective_extractor_model, kind=kind,
                                   questions=questions, model_api_parameters=params)
    wire_metrics(db=db, agents={"scheme_extractor": agent})
    return RateLimitedAgent(agent, bucket)


def _template(db: Database, template_id: int) -> dict:
    rows = db.query("SELECT * FROM assignment_templates WHERE id = :id", {"id": template_id})
    if not rows:
        raise ValueError(f"assignment {template_id} not found")
    return rows[0]


def _page_images(db: Database, storage: PageStorage, template_id: int, kind: str) -> List[bytes]:
    rows = db.query("SELECT storage_path FROM pages WHERE template_id = :t AND kind = :k ORDER BY page_index",
                    {"t": template_id, "k": kind})
    return [storage.read(r["storage_path"]) for r in rows]


def _settings(settings_store: SettingsStore, tpl: dict):
    """The settings this assignment's extraction runs with — its own provider/model when it sets one.
    `tpl` is the assignment_templates row, which carries provider/model/extractor_model."""
    settings = settings_store.for_template(tpl)
    if not settings.has_key:
        raise RuntimeError("No API key configured — add one under Settings")
    return settings


def _bucket_for(settings, bucket: Optional[TokenBucket], bucket_pool: Optional[BucketPool]) -> TokenBucket:
    """The assignment's provider gets its own bucket from the pool, so two assignments on different
    providers do not share one provider's rate limit. Only without a pool does an explicitly passed
    bucket apply — the callers (and tests) that manage their own."""
    if bucket_pool is not None:
        return bucket_pool.get(settings.provider, settings.rpm_limit)
    return bucket or TokenBucket(settings.rpm_limit)


def run_paper_extract_job(db: Database, storage: PageStorage, settings_store: SettingsStore, template_id: int,
                          bucket: Optional[TokenBucket] = None,
                          agent_factory: Optional[Callable[..., Any]] = None,
                          bucket_pool: Optional[BucketPool] = None) -> int:
    """Transcribe the template's question paper into questions_json. Returns the number of questions."""
    tpl = _template(db, template_id)
    images = _page_images(db, storage, template_id, "paper")
    if not images:
        raise ValueError("Upload the question paper first")
    settings = _settings(settings_store, tpl)
    factory = agent_factory or _default_paper_factory
    agent = factory(db=db, settings=settings, bucket=_bucket_for(settings, bucket, bucket_pool))
    hint = f"{tpl['title']} ({tpl['subject']})"
    result = agent.run(PaperExtractInput(images=[image_from_bytes(b) for b in images], hint=hint))
    questions = [q.model_dump() for q in result.questions]
    db.execute("UPDATE assignment_templates SET questions_json = :q, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
               {"q": json.dumps(questions), "id": template_id})
    return len(questions)


def run_scheme_extract_job(db: Database, storage: PageStorage, settings_store: SettingsStore, template_id: int,
                           bucket: Optional[TokenBucket] = None,
                           agent_factory: Optional[Callable[..., Any]] = None,
                           bucket_pool: Optional[BucketPool] = None) -> int:
    """Transcribe the template's mark scheme or rubric pages into scheme_json. Returns the number of rows."""
    tpl = _template(db, template_id)
    kind = tpl["scheme_kind"]
    if kind not in ("mark_scheme", "rubric"):
        raise ValueError("Choose the assignment type (mark scheme or rubric) before reading the scheme")
    images = _page_images(db, storage, template_id, "scheme")
    if not images:
        raise ValueError("Upload the mark scheme or rubric first")
    questions = [Question.model_validate(q) for q in json.loads(tpl["questions_json"] or "[]")]
    settings = _settings(settings_store, tpl)
    factory = agent_factory or _default_scheme_factory
    agent = factory(db=db, settings=settings, bucket=_bucket_for(settings, bucket, bucket_pool), kind=kind,
                    questions=questions)
    result = agent.run(SchemeExtractInput(images=[image_from_bytes(b) for b in images], questions=questions))
    items = [i.model_dump() for i in result.items]
    db.execute("UPDATE assignment_templates SET scheme_json = :s, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
               {"s": json.dumps(items), "id": template_id})
    return len(items)

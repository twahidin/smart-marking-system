"""Re-mark one corrected part: the Marker and the Checker see only that part's question and scheme
row, with the student's correction as the transcribed answer (or the photo's transcription)."""
import logging
import uuid
from typing import Any, Callable, Optional

from sms.memory.db import Database
from sms.providers.ratelimit import BucketPool, TokenBucket
from sms.providers.settings import SettingsStore
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.marking import ReviewVerdict
from sms.schemas.marking_v2 import MarkingInputV2, ReviewInputV2
from sms.schemas.scheme import MarkSchemeEntry, Question, RubricCriterionBands, norm_qid
from sms.storage import PageStorage
from sms.web.services.assignments import get_template
from sms.worker.mark_job import _default_pipeline_factory, _v2_template

log = logging.getLogger(__name__)

FINAL = ("released", "rejected")


def _part_template(template: dict, q_id: str) -> dict:
    key = norm_qid(q_id)
    if template["scheme_kind"] == "mark_scheme":
        questions = [q for q in template.get("questions") or [] if norm_qid(q["q_id"]) == key]
        scheme = [s for s in template.get("scheme") or [] if norm_qid(s["q_id"]) == key]
    else:
        # a rubric correction names a criterion: the question list stays whole, the scheme narrows to it
        questions = list(template.get("questions") or [])
        scheme = [s for s in template.get("scheme") or [] if s["criterion"] == q_id]
    return {**template, "questions": questions, "scheme": scheme}


def _max_of(part_template: dict) -> float:
    if part_template["scheme_kind"] == "mark_scheme":
        return float(sum(m["marks"] for s in part_template["scheme"] for m in s["marks"]))
    return float(max((b["marks"] for s in part_template["scheme"] for b in s["bands"]), default=0))


def _marks_of(mark: Any, scheme_kind: str) -> float:
    return float(mark.total if scheme_kind == "mark_scheme" else mark.marks)


def run_remark_job(db: Database, storage: PageStorage, settings_store: SettingsStore, correction_id: int,
                   pipeline_factory: Optional[Callable[..., Any]] = None,
                   bucket: Optional[TokenBucket] = None, bucket_pool: Optional[BucketPool] = None) -> None:
    rows = db.query("SELECT c.*, s.assignment_id, s.scheme_kind, s.subject FROM student_corrections c "
                    "JOIN submissions s ON s.id = c.submission_id WHERE c.id = :id", {"id": correction_id})
    if not rows:
        raise ValueError(f"correction {correction_id} not found")
    c = rows[0]
    if c["status"] in FINAL:
        log.info("correction %s is already %s; not re-marking", correction_id, c["status"])
        return
    try:
        tpl = get_template(db, c["assignment_id"])
        settings = settings_store.for_template(tpl)
        if bucket_pool is not None:
            bucket = bucket_pool.get(settings.provider, settings.rpm_limit)
        template = _v2_template(db, c["assignment_id"], c["scheme_kind"])
        if template is None:
            raise RuntimeError("This assignment has no mark scheme or rubric to re-mark against")
        part = _part_template(template, c["q_id"])
        if not part["questions"] or not part["scheme"]:
            raise RuntimeError(f"Part {c['q_id']} is not in the scheme any more")
        factory = pipeline_factory or _default_pipeline_factory
        pipeline = factory(db=db, settings=settings, subject=template["subject"], bucket=bucket, kind=template["scheme_kind"])
        questions = [Question.model_validate(q) for q in part["questions"]]
        text = (c["text"] or "").strip()
        if not text and c["page_id"] is not None:
            page = db.query("SELECT storage_path FROM pages WHERE id = :p", {"p": c["page_id"]})[0]
            ex = pipeline._extract([storage.read(page["storage_path"])], template["subject"], questions,
                                   template.get("context") or "", "en")
            text = "\n".join(f"{q.transcribed_answer}\n{q.workings}".strip() for q in ex.questions)
        ex_qid = c["q_id"] if part["scheme_kind"] == "mark_scheme" else part["questions"][0]["q_id"]
        extracted = ExtractedScript(questions=[ExtractedQuestion(q_id=ex_qid, transcribed_answer=text, workings="", confidence=1.0)])
        scheme = ([MarkSchemeEntry.model_validate(s) for s in part["scheme"]] if part["scheme_kind"] == "mark_scheme"
                  else [RubricCriterionBands.model_validate(s) for s in part["scheme"]])
        notes = template.get("context") or ""
        marked = pipeline.marker.run(MarkingInputV2(kind=part["scheme_kind"], extracted=extracted, questions=questions, scheme=scheme, notes=notes))
        reviewed = pipeline.reviewer.run(ReviewInputV2(kind=part["scheme_kind"], extracted=extracted, questions=questions, scheme=scheme,
                                                       notes=notes, marks=pipeline._blind_script(marked)))
        marks = marked.parts or marked.rubric
        mark = marks[0] if marks else None
        total = _marks_of(mark, part["scheme_kind"]) if mark else 0.0
        just = (mark.justification if mark else "") or ""
        verdict = next((v for v in reviewed.verdicts), None)
        if verdict is not None and verdict.verdict == ReviewVerdict.ADJUST and verdict.adjusted is not None:
            total = _marks_of(verdict.adjusted, part["scheme_kind"])
        note = f"Marker: {just}".rstrip()
        if verdict is not None:
            note += f"\nChecker: {verdict.verdict.value}: {verdict.reviewer_note}".rstrip()
        db.execute("UPDATE student_corrections SET status = 'remarked', remark_total = :t, remark_max = :m, remark_note = :n, "
                   "remark_run_id = :r, error = NULL WHERE id = :id AND status = 'submitted'",
                   {"t": total, "m": _max_of(part), "n": note, "r": uuid.uuid4().hex[:12], "id": correction_id})
    except Exception as e:  # noqa: BLE001
        db.execute("UPDATE student_corrections SET error = :e WHERE id = :id AND status = 'submitted'", {"e": str(e)[:500], "id": correction_id})
        raise

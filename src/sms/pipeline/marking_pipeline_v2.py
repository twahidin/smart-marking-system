"""Per-part marking pipeline (version 2), used when a submission's assignment has a mark scheme or a
rubric: extract (segmented by the paper's parts) -> mark per part / criterion -> blind review ->
merge with escalation -> feedback -> persist as final_marks_json {"version": 2, ...}."""
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from sms.memory.db import Database
from sms.memory.extraction_cache import ExtractionCache
from sms.pipeline.marking_pipeline import image_from_bytes
from sms.pipeline.router import SubjectRouter
from sms.schemas.extraction import ExtractionInput, ExtractedScript
from sms.schemas.feedback import FeedbackInput, FeedbackReport
from sms.schemas.marking import MarkedQuestion, MarkedScript, ReviewVerdict, ReviewVerdictItem, ReviewedScript
from sms.schemas.marking_v2 import (
    SCHEME_KINDS,
    AllocationMark,
    MarkedScriptV2,
    MarkingInputV2,
    PartMark,
    ReviewInputV2,
    ReviewedScriptV2,
    RubricMark,
)
from sms.schemas.scheme import Question

# The only strings written to teacher_queue.reason by this pipeline.
ILLEGIBLE = "illegible"
NOT_IN_SCHEME = "not in scheme"
REVIEWER_ESCALATED = "reviewer escalated"
LOW_CONFIDENCE = "low confidence"
DISAGREE = "marker/reviewer disagree"

Mark = Union[PartMark, RubricMark]


@dataclass
class MarkingResultV2:
    run_id: str
    extracted: ExtractedScript
    final: MarkedScriptV2
    escalations: Dict[str, str] = field(default_factory=dict)  # q_id / criterion -> reason
    feedback: Optional[FeedbackReport] = None


def _key(m: Mark) -> str:
    return m.q_id if isinstance(m, PartMark) else m.criterion


def _blind(m: Mark) -> Mark:
    """The marker's mark without its reasoning, so the reviewer re-marks rather than reads along."""
    if isinstance(m, PartMark):
        return m.model_copy(update={"justification": "",
                                    "awarded": [a.model_copy(update={"why": ""}) for a in m.awarded]})
    return m.model_copy(update={"justification": "", "descriptor_met": ""})


def _as_marked_question(m: Mark) -> MarkedQuestion:
    if isinstance(m, PartMark):
        scores = [a.marks if a.got else 0 for a in m.awarded] or [m.total]
        return MarkedQuestion(q_id=m.q_id, criterion_scores=scores, total=m.total, confidence=m.confidence,
                              rationale=m.justification)
    rationale = f"Band {m.band}: {m.justification}".strip().rstrip(":")
    return MarkedQuestion(q_id=m.criterion, criterion_scores=[m.marks], total=m.marks, confidence=m.confidence,
                          rationale=rationale)


def feedback_input_for_v2(final: MarkedScriptV2, reviewed: ReviewedScriptV2, escalations: Dict[str, str],
                          student_context: Optional[str] = None) -> FeedbackInput:
    """Adapt v2 marks to the v1 FeedbackInput so build_feedback needs no change: each part / criterion
    becomes a MarkedQuestion (q_id -> total, rationale = justification; rubric rationale in band language)."""
    marks = [_as_marked_question(m) for m in (final.parts if final.kind == "mark_scheme" else final.rubric)]
    verdicts = [
        ReviewVerdictItem(q_id=v.q_id, verdict=v.verdict,
                          adjusted_total=(v.adjusted.total if isinstance(v.adjusted, PartMark)
                                          else v.adjusted.marks if isinstance(v.adjusted, RubricMark) else None),
                          reviewer_note=v.reviewer_note)
        for v in reviewed.verdicts
    ]
    return FeedbackInput(
        reviewed=ReviewedScript(verdicts=verdicts, final_marks=marks, disagreement_flags=sorted(escalations)),
        final_marks=MarkedScript(marks=marks),
        final_result_set=not escalations,
        student_context=student_context,
    )


class MarkingPipelineV2:
    """Orchestrates extract -> mark per part -> review -> merge -> feedback -> persist for one script."""

    def __init__(self, db: Database, extractor: Any, marker: Any, reviewer: Any, feedback: Any, kind: str,
                 confidence_threshold: float = 0.0):
        if kind not in SCHEME_KINDS:
            raise ValueError(f"v2 pipeline kind must be one of {SCHEME_KINDS}, got {kind!r}")
        self.db = db
        self.extractor = extractor
        self.marker = marker
        self.reviewer = reviewer
        self.feedback = feedback
        self.kind = kind
        self.cache = ExtractionCache(db)
        self.confidence_threshold = confidence_threshold

    # --- run -------------------------------------------------------------------------------------

    def run(self, images: List[bytes], template: dict, submission_id: Optional[int] = None) -> MarkingResultV2:
        """`template` is the assignment as a dict: subject, context (notes), questions, scheme (and scheme_kind)."""
        run_id = uuid.uuid4().hex[:12]
        subject = SubjectRouter().resolve(template.get("subject") or "math")
        questions = [Question.model_validate(q) for q in template.get("questions") or []]
        scheme = list(template.get("scheme") or [])
        notes = (template.get("context") or "").strip()

        extracted = self._extract(images, subject, questions, notes)
        marked = self.marker.run(MarkingInputV2(kind=self.kind, extracted=extracted, questions=questions,
                                                scheme=scheme, notes=notes))
        reviewed = self.reviewer.run(ReviewInputV2(kind=self.kind, extracted=extracted, questions=questions,
                                                   scheme=scheme, notes=notes, marks=self._blind_script(marked)))
        final, escalations = self._merge(marked, reviewed, extracted)
        feedback_report = self.feedback.run(feedback_input_for_v2(final, reviewed, escalations))
        self._persist(run_id, subject, template, questions, scheme, notes, extracted, marked, reviewed,
                      feedback_report, final, escalations, submission_id)
        return MarkingResultV2(run_id=run_id, extracted=extracted, final=final, escalations=escalations,
                               feedback=feedback_report)

    # --- stages ----------------------------------------------------------------------------------

    def _extract(self, images: List[bytes], subject: str, questions: List[Question], notes: str) -> ExtractedScript:
        # Cache key covers the pages and the labels they are segmented by: the same pages segmented by a
        # different question list (or by none, v1) are a different extraction.
        page_hashes = [self.cache.hash_image(b) for b in images]
        labels = ",".join(q.q_id for q in questions)
        composite = self.cache.hash_image(("|".join(page_hashes) + "#v2#" + labels).encode())
        cached = self.cache.get(composite, subject)
        if cached is not None:
            return ExtractedScript.model_validate(cached)
        context = f"{subject} script, {len(questions)} question part(s)" + (f". Notes: {notes}" if notes else "")
        extracted = self.extractor.run(ExtractionInput(
            assignment_context=context, images=[image_from_bytes(b) for b in images], questions=questions))
        self.cache.put(composite, subject, extracted.model_dump())
        return extracted

    def _blind_script(self, marked: MarkedScriptV2) -> MarkedScriptV2:
        return MarkedScriptV2(kind=marked.kind, parts=[_blind(p) for p in marked.parts],
                              rubric=[_blind(r) for r in marked.rubric])

    def _merge(self, marked: MarkedScriptV2, reviewed: ReviewedScriptV2,
               extracted: ExtractedScript) -> Tuple[MarkedScriptV2, Dict[str, str]]:
        verdicts = {v.q_id: v for v in reviewed.verdicts}
        illegible = {q.q_id for q in extracted.questions if q.needs_human_transcription}
        if self.kind == "mark_scheme":
            marks: List[Mark] = list(marked.parts)
        else:
            marks = list(marked.rubric)
            # a rubric marks one response: if any of it is unreadable every criterion goes to the teacher
            illegible = {r.criterion for r in marked.rubric} if illegible else set()
        final: List[Mark] = []
        escalations: Dict[str, str] = {}
        for m in marks:
            merged, reason = self._merge_one(m, verdicts.get(_key(m)), _key(m) in illegible)
            final.append(merged)
            if reason:
                escalations[_key(m)] = reason
        if self.kind == "mark_scheme":
            return MarkedScriptV2(kind="mark_scheme", parts=final), escalations  # type: ignore[arg-type]
        return MarkedScriptV2(kind="rubric", rubric=final), escalations  # type: ignore[arg-type]

    def _merge_one(self, m: Mark, verdict, illegible: bool) -> Tuple[Mark, Optional[str]]:
        if illegible:
            return m, ILLEGIBLE
        if verdict is not None and verdict.verdict == ReviewVerdict.ESCALATE:
            return m, REVIEWER_ESCALATED
        if verdict is not None and verdict.verdict == ReviewVerdict.ADJUST:
            adjusted = verdict.adjusted
            same_shape = isinstance(adjusted, type(m))
            same_total = same_shape and (adjusted.total == m.total if isinstance(m, PartMark) else adjusted.marks == m.marks)
            if not same_total:
                return m, DISAGREE  # marks differ (or no corrected mark given): the teacher decides
            # same marks, different allocation / band wording: take the reviewer's correction quietly
            m = adjusted.model_copy(update={"q_id": m.q_id} if isinstance(m, PartMark) else {"criterion": m.criterion})
        if isinstance(m, PartMark) and not m.in_scheme:
            return m, NOT_IN_SCHEME
        if self.confidence_threshold and m.confidence < self.confidence_threshold:
            return m, LOW_CONFIDENCE
        return m, None

    def _persist(self, run_id: str, subject: str, template: dict, questions: List[Question], scheme: list,
                 notes: str, extracted: ExtractedScript, marked: MarkedScriptV2, reviewed: ReviewedScriptV2,
                 feedback: FeedbackReport, final: MarkedScriptV2, escalations: Dict[str, str],
                 submission_id: Optional[int]) -> None:
        scheme_json = {
            "scheme_kind": self.kind,
            "questions": [q.model_dump() for q in questions],
            "scheme": [s.model_dump() if hasattr(s, "model_dump") else s for s in scheme],
            "notes": notes,
        }
        final_json = {"version": 2, "kind": final.kind, "parts": [p.model_dump() for p in final.parts],
                      "rubric": [r.model_dump() for r in final.rubric]}
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, marks_json, "
                "reviewed_json, feedback_json, final_marks_json, submission_id, final_status) "
                "VALUES (:run_id, 'complete', :subject, :rubric, :extracted, :marks, :reviewed, :feedback, "
                ":final_marks, :submission_id, :status)",
                {
                    "run_id": run_id,
                    "subject": subject,
                    "rubric": json.dumps(scheme_json),
                    "extracted": extracted.model_dump_json(),
                    "marks": marked.model_dump_json(),
                    "reviewed": reviewed.model_dump_json(),
                    "feedback": feedback.model_dump_json(),
                    "final_marks": json.dumps(final_json),
                    "submission_id": submission_id,
                    "status": "escalated" if escalations else "complete",
                },
            )
            for key, reason in escalations.items():
                tx.execute(
                    "INSERT INTO teacher_queue (run_id, q_id, reason, status, submission_id) "
                    "VALUES (:run_id, :q_id, :reason, 'pending', :submission_id)",
                    {"run_id": run_id, "q_id": key, "reason": reason, "submission_id": submission_id},
                )
            if submission_id is not None:
                tx.execute("UPDATE submissions SET marks_version = 2 WHERE id = :id", {"id": submission_id})

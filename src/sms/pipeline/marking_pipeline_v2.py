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
from sms.schemas.scheme import MarkSchemeEntry, Question, RubricCriterionBands

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


def _row_key(row: Any) -> str:
    return row.q_id if isinstance(row, MarkSchemeEntry) else row.criterion


def _marks_of(m: Mark) -> int:
    return m.total if isinstance(m, PartMark) else m.marks


def normalise_against_scheme(mark: Mark, row: Any) -> Tuple[Mark, bool]:
    """Reconcile an LLM mark with the scheme it claims to follow. Returns (mark, in_scheme).
    PartMark + MarkSchemeEntry: every awarded label must exist in the row (else not in scheme); each
    allocation's marks are taken from the row by label and the total recomputed from the allocations
    marked got. A part the marker flagged in_scheme=False stays out of the scheme.
    RubricMark + RubricCriterionBands: the band must exist in the criterion (else not in scheme) and its
    marks are taken from the rubric."""
    if isinstance(mark, PartMark) and isinstance(row, MarkSchemeEntry):
        if not mark.in_scheme:
            return mark, False
        row_marks = {mp.label: mp.marks for mp in row.marks}
        if any(a.label not in row_marks for a in mark.awarded):
            return mark, False
        awarded = [a.model_copy(update={"marks": row_marks[a.label]}) for a in mark.awarded]
        total = sum(a.marks for a in awarded if a.got) if awarded else mark.total
        return mark.model_copy(update={"awarded": awarded, "total": total}), True
    if isinstance(mark, RubricMark) and isinstance(row, RubricCriterionBands):
        bands = {b.band: b.marks for b in row.bands}
        if mark.band not in bands:
            return mark, False
        return mark.model_copy(update={"marks": bands[mark.band]}), True
    return mark, False


def _missing_mark(row: Any) -> Mark:
    """The mark recorded for a scheme part / criterion the marker returned nothing for."""
    if isinstance(row, MarkSchemeEntry):
        return PartMark(q_id=row.q_id, awarded=[AllocationMark(label=mp.label, marks=mp.marks, got=False) for mp in row.marks],
                        total=0, justification="Marker returned no mark for this part", in_scheme=True, confidence=0.0)
    return RubricMark(criterion=row.criterion, band="", marks=0, justification="Marker returned no mark for this criterion",
                      confidence=0.0)


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
        final, escalations = self._merge(marked, reviewed, extracted, scheme)
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

    def _merge(self, marked: MarkedScriptV2, reviewed: ReviewedScriptV2, extracted: ExtractedScript,
               scheme: list) -> Tuple[MarkedScriptV2, Dict[str, str]]:
        """Walk the scheme (rows for a mark scheme, criteria for a rubric), not the marker's output: every
        scheme part gets a final mark, a part the marker skipped is synthesised and escalated, a part the
        marker invented is kept but escalated as not in the scheme."""
        verdicts = {v.q_id: v for v in reviewed.verdicts}
        illegible = {q.q_id for q in extracted.questions if q.needs_human_transcription}
        if self.kind == "mark_scheme":
            marker_marks: List[Mark] = list(marked.parts)
            rows: List[Any] = [MarkSchemeEntry.model_validate(r) for r in scheme]
        else:
            marker_marks = list(marked.rubric)
            rows = [RubricCriterionBands.model_validate(c) for c in scheme]
            # a rubric marks one response: if any of it is unreadable every criterion goes to the teacher
            illegible = {c.criterion for c in rows} if illegible else set()
        by_key: Dict[str, Mark] = {}
        for m in marker_marks:  # duplicate q_ids / criteria: the first one counts
            by_key.setdefault(_key(m), m)
        rows_by_key: Dict[str, Any] = {}
        for r in rows:
            rows_by_key.setdefault(_row_key(r), r)

        final: List[Mark] = []
        escalations: Dict[str, str] = {}
        for key, row in rows_by_key.items():
            m = by_key.get(key)
            if m is None:
                # The marker returned nothing for this part: 0 marks with no confidence at all. Escalated as
                # "low confidence" because that is the queue reason that means "the marker could not mark
                # this" — the five reason strings are fixed for the record and the review queue.
                final.append(_missing_mark(row))
                escalations[key] = LOW_CONFIDENCE
                continue
            merged, reason = self._merge_one(m, row, verdicts.get(key), key in illegible)
            final.append(merged)
            if reason:
                escalations[key] = reason
        for key, m in by_key.items():
            if key not in rows_by_key:  # invented part / criterion: kept as the marker's proposal, teacher decides
                final.append(m)
                escalations[key] = NOT_IN_SCHEME
        if self.kind == "mark_scheme":
            return MarkedScriptV2(kind="mark_scheme", parts=final), escalations  # type: ignore[arg-type]
        return MarkedScriptV2(kind="rubric", rubric=final), escalations  # type: ignore[arg-type]

    def _merge_one(self, m: Mark, row: Any, verdict, illegible: bool) -> Tuple[Mark, Optional[str]]:
        # Reason priority: illegible -> not in scheme -> reviewer escalated -> disagree -> low confidence.
        # The marker's in_scheme / allocation check comes before any verdict so a reviewer's ADJUST
        # (whose adjusted part defaults to in_scheme=True) can never un-escalate an uncovered answer.
        if illegible:
            return m, ILLEGIBLE
        normalised, in_scheme = normalise_against_scheme(m, row)
        if not in_scheme:
            return m, NOT_IN_SCHEME
        m = normalised
        # A missing reviewer verdict counts as APPROVE: the marker's (normalised) mark stands.
        if verdict is not None and verdict.verdict == ReviewVerdict.ESCALATE:
            return m, REVIEWER_ESCALATED
        if verdict is not None and verdict.verdict == ReviewVerdict.ADJUST:
            adjusted = verdict.adjusted
            if not isinstance(adjusted, type(m)):
                return m, DISAGREE  # no usable corrected mark: the teacher sees both views
            adjusted, adj_in_scheme = normalise_against_scheme(adjusted, row)
            if not adj_in_scheme or _marks_of(adjusted) != _marks_of(m):
                return m, DISAGREE  # marks differ (or the correction is unmappable): the teacher decides
            # same marks, different allocation / band wording: take the reviewer's correction quietly,
            # keeping the marker's in_scheme and the lower of the two confidences
            m = adjusted.model_copy(update={
                "confidence": min(m.confidence, adjusted.confidence),
                **({"in_scheme": m.in_scheme} if isinstance(m, PartMark) else {}),
            })
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

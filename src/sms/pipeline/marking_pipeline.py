import base64
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional

import instructor

from sms.memory.db import Database
from sms.memory.extraction_cache import ExtractionCache
from sms.pipeline.router import SubjectRouter
from sms.schemas.extraction import ExtractionInput, ExtractedScript
from sms.schemas.feedback import FeedbackInput, FeedbackReport
from sms.schemas.marking import (
    MarkingInput,
    MarkedQuestion,
    MarkedScript,
    ReviewInput,
    ReviewVerdict,
    ReviewedScript,
    Rubric,
)


@dataclass
class MarkingResult:
    run_id: str
    extracted: ExtractedScript
    final_marks: MarkedScript
    escalations: List[str] = field(default_factory=list)
    feedback: Optional[FeedbackReport] = None


def image_from_bytes(b: bytes) -> instructor.Image:
    """Wrap page bytes (JPEG/PNG) as an instructor.Image for a vision call."""
    b64 = base64.b64encode(b).decode()
    try:
        return instructor.Image.from_raw_base64(b64)
    except ValueError:
        return instructor.Image(source=f"data:image/png;base64,{b64}", media_type="image/png", data=b64)


class MarkingPipeline:
    """Orchestrates extract -> mark -> review -> merge -> feedback -> persist."""

    def __init__(self, db: Database, extractor: Any, marker: Any, reviewer: Any, feedback: Any, subject: str,
                 confidence_threshold: float = 0.0):
        self.db = db
        self.extractor = extractor
        self.marker = marker
        self.reviewer = reviewer
        self.feedback = feedback
        self.subject = SubjectRouter().resolve(subject)
        self.cache = ExtractionCache(db)
        self.confidence_threshold = confidence_threshold

    def run(self, images: List[bytes], assignment_context: str, rubric: Rubric,
            submission_id: Optional[int] = None) -> MarkingResult:
        run_id = uuid.uuid4().hex[:12]
        image_hashes = [self.cache.hash_image(b) for b in images]
        composite_hash = self.cache.hash_image("|".join(image_hashes).encode())

        extracted = self._extract(composite_hash, images, assignment_context)
        marked = self.marker.run(
            MarkingInput(extracted=extracted, rubric=rubric, assignment_context=assignment_context)
        )
        reviewed = self.reviewer.run(self._review_input(extracted, marked, rubric, assignment_context))
        final_marks, escalation_reasons = self._merge(marked, reviewed, extracted)
        escalations = list(escalation_reasons.keys())
        feedback_report = self.feedback.run(
            FeedbackInput(
                reviewed=reviewed,
                final_marks=final_marks,
                final_result_set=not escalations,
            )
        )
        self._persist(run_id, rubric, extracted, marked, reviewed, feedback_report, escalation_reasons,
                      final_marks, submission_id)
        return MarkingResult(run_id=run_id, extracted=extracted, final_marks=final_marks,
                             escalations=escalations, feedback=feedback_report)

    def _extract(self, composite_hash: str, images: List[bytes], assignment_context: str) -> ExtractedScript:
        cached = self.cache.get(composite_hash, self.subject)
        if cached is not None:
            return ExtractedScript.model_validate(cached)
        extracted = self.extractor.run(
            ExtractionInput(
                assignment_context=assignment_context,
                images=[image_from_bytes(b) for b in images],
            )
        )
        self.cache.put(composite_hash, self.subject, extracted.model_dump())
        return extracted

    def _review_input(self, extracted: ExtractedScript, marked: MarkedScript, rubric: Rubric, ctx: str) -> ReviewInput:
        stripped = MarkedScript(
            marks=[
                MarkedQuestion(
                    q_id=m.q_id,
                    criterion_scores=m.criterion_scores,
                    total=m.total,
                    confidence=m.confidence,
                    rationale="",
                    evidence="",
                )
                for m in marked.marks
            ]
        )
        return ReviewInput(extracted=extracted, marks=stripped, rubric=rubric, assignment_context=ctx)

    def _merge(self, marked: MarkedScript, reviewed: ReviewedScript, extracted: ExtractedScript):
        final: List[MarkedQuestion] = []
        escalation_reasons: dict = {}
        by_q = {v.q_id: v for v in reviewed.verdicts}
        illegible = {q.q_id for q in extracted.questions if q.needs_human_transcription}
        for m in marked.marks:
            v = by_q.get(m.q_id)
            reason = None
            if m.q_id in illegible:
                reason = "illegible transcription"
            elif v is None or v.verdict == ReviewVerdict.APPROVE:
                if self.confidence_threshold and m.confidence < self.confidence_threshold:
                    reason = "low marker confidence"
                else:
                    final.append(m)
            elif v.verdict == ReviewVerdict.ADJUST and v.adjusted_criterion_scores is not None:
                adjusted_total = v.adjusted_total if v.adjusted_total is not None else sum(v.adjusted_criterion_scores)
                final.append(
                    MarkedQuestion(
                        q_id=m.q_id,
                        criterion_scores=v.adjusted_criterion_scores,
                        total=adjusted_total,
                        confidence=m.confidence,
                        rationale=m.rationale,
                        evidence=m.evidence,
                    )
                )
            else:
                reason = "reviewer escalated"
            if reason:
                escalation_reasons[m.q_id] = reason
                final.append(m)
        return MarkedScript(marks=final), escalation_reasons

    def _persist(self, run_id: str, rubric: Rubric, extracted: ExtractedScript, marked: MarkedScript,
                 reviewed: ReviewedScript, feedback: FeedbackReport, escalation_reasons: dict,
                 final_marks: MarkedScript, submission_id: Optional[int]) -> None:
        escalations = list(escalation_reasons.keys())
        self.db.execute(
            "INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, marks_json, "
            "reviewed_json, feedback_json, final_marks_json, submission_id, final_status) "
            "VALUES (:run_id, 'complete', :subject, :rubric, :extracted, :marks, :reviewed, :feedback, "
            ":final_marks, :submission_id, :status)",
            {
                "run_id": run_id,
                "subject": self.subject,
                "rubric": rubric.model_dump_json(),
                "extracted": extracted.model_dump_json(),
                "marks": marked.model_dump_json(),
                "reviewed": reviewed.model_dump_json(),
                "feedback": feedback.model_dump_json(),
                "final_marks": final_marks.model_dump_json(),
                "submission_id": submission_id,
                "status": "escalated" if escalations else "complete",
            },
        )
        for q_id, reason in escalation_reasons.items():
            self.db.execute(
                "INSERT INTO teacher_queue (run_id, q_id, reason, status, submission_id) "
                "VALUES (:run_id, :q_id, :reason, 'pending', :submission_id)",
                {"run_id": run_id, "q_id": q_id, "reason": reason, "submission_id": submission_id},
            )

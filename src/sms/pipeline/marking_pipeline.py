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


def _image_from_bytes(b: bytes) -> instructor.Image:
    b64 = base64.b64encode(b).decode()
    try:
        return instructor.Image.from_raw_base64(b64)
    except ValueError:
        return instructor.Image(source=f"data:image/png;base64,{b64}", media_type="image/png", data=b64)


class MarkingPipeline:
    """Orchestrates extract -> mark -> review -> merge -> feedback -> persist."""

    def __init__(self, db: Database, extractor: Any, marker: Any, reviewer: Any, feedback: Any, subject: str):
        self.db = db
        self.extractor = extractor
        self.marker = marker
        self.reviewer = reviewer
        self.feedback = feedback
        self.subject = SubjectRouter().resolve(subject)
        self.cache = ExtractionCache(db)

    def run(self, images: List[bytes], assignment_context: str, rubric: Rubric) -> MarkingResult:
        run_id = uuid.uuid4().hex[:12]
        image_hashes = [self.cache.hash_image(b) for b in images]
        composite_hash = self.cache.hash_image("|".join(image_hashes).encode())

        extracted = self._extract(composite_hash, images, assignment_context)
        marked = self.marker.run(
            MarkingInput(extracted=extracted, rubric=rubric, assignment_context=assignment_context)
        )
        reviewed = self.reviewer.run(self._review_input(extracted, marked, rubric, assignment_context))
        final_marks, escalations = self._merge(marked, reviewed)
        feedback_report = self.feedback.run(
            FeedbackInput(
                reviewed=reviewed,
                final_marks=final_marks,
                final_result_set=not escalations,
            )
        )
        self._persist(run_id, rubric, extracted, marked, reviewed, feedback_report, escalations)
        return MarkingResult(run_id=run_id, extracted=extracted, final_marks=final_marks,
                             escalations=escalations, feedback=feedback_report)

    def _extract(self, composite_hash: str, images: List[bytes], assignment_context: str) -> ExtractedScript:
        cached = self.cache.get(composite_hash, self.subject)
        if cached is not None:
            return ExtractedScript.model_validate(cached)
        extracted = self.extractor.run(
            ExtractionInput(
                assignment_context=assignment_context,
                images=[_image_from_bytes(b) for b in images],
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

    def _merge(self, marked: MarkedScript, reviewed: ReviewedScript):
        final: List[MarkedQuestion] = []
        escalations: List[str] = []
        by_q = {v.q_id: v for v in reviewed.verdicts}
        for m in marked.marks:
            v = by_q.get(m.q_id)
            if v is None or v.verdict == ReviewVerdict.APPROVE:
                final.append(m)
            elif v.verdict == ReviewVerdict.ADJUST and v.adjusted_criterion_scores is not None:
                final.append(
                    MarkedQuestion(
                        q_id=m.q_id,
                        criterion_scores=v.adjusted_criterion_scores,
                        total=v.adjusted_total or sum(v.adjusted_criterion_scores),
                        confidence=m.confidence,
                        rationale=m.rationale,
                        evidence=m.evidence,
                    )
                )
            else:
                escalations.append(m.q_id)
                final.append(m)
        return MarkedScript(marks=final), escalations

    def _persist(self, run_id: str, rubric: Rubric, extracted: ExtractedScript, marked: MarkedScript,
                 reviewed: ReviewedScript, feedback: FeedbackReport, escalations: List[str]) -> None:
        self.db.execute(
            "INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, marks_json, "
            "reviewed_json, feedback_json, final_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                "complete",
                self.subject,
                rubric.model_dump_json(),
                extracted.model_dump_json(),
                marked.model_dump_json(),
                reviewed.model_dump_json(),
                feedback.model_dump_json(),
                "escalated" if escalations else "complete",
            ),
        )
        for q_id in escalations:
            self.db.execute(
                "INSERT INTO teacher_queue (run_id, q_id, reason, status) VALUES (?, ?, ?, 'pending')",
                (run_id, q_id, "reviewer escalated"),
            )

"""Escalation reasons: the codes the pipelines store in teacher_queue.reason, and the one sentence a
teacher reads for each. Shared by the detail page, the review queue and the marking record so every
surface says the same thing."""
from typing import Dict, Optional

TEACHER_TO_REVIEW = "Teacher to review"

# Queue reasons (marking_pipeline_v2 and the v1 pipeline) -> what the teacher reads.
REASON_TEXT: Dict[str, str] = {
    "illegible": "Unclear handwriting",
    "not in scheme": "Answer not in the scheme — different method",
    "reviewer escalated": "Marker and reviewer disagreed",
    "marker/reviewer disagree": "Marker and reviewer disagreed",
    "low confidence": "Low confidence",
    # v1 wording (marking_pipeline)
    "low marker confidence": "Low confidence",
    "illegible transcription": "Unclear handwriting",
}


def reason_text(reason: Optional[str]) -> str:
    """The teacher-facing reason for an escalated part; unknown reasons read "Teacher to review"."""
    if not reason:
        return TEACHER_TO_REVIEW
    return REASON_TEXT.get(reason.strip().lower(), TEACHER_TO_REVIEW)

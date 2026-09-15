"""Every escalation code the pipelines store reads as one teacher-facing sentence, the same on the
detail page, in the review queue and in the marking record."""
import pytest

from sms.reasons import TEACHER_TO_REVIEW, reason_text
from sms.records import builder


@pytest.mark.parametrize("code, text", [
    # v2 (marking_pipeline_v2)
    ("illegible", "Unclear handwriting"),
    ("not in scheme", "Answer not in the scheme — different method"),
    ("reviewer escalated", "Marker and reviewer disagreed"),
    ("marker/reviewer disagree", "Marker and reviewer disagreed"),
    ("low confidence", "Low confidence"),
    # v1 (marking_pipeline)
    ("illegible transcription", "Unclear handwriting"),
    ("low marker confidence", "Low confidence"),
])
def test_reason_text_for_every_pipeline_code(code, text):
    assert reason_text(code) == text
    assert reason_text(code.upper() + "  ") == text


def test_unknown_or_missing_reason_reads_teacher_to_review():
    assert reason_text(None) == TEACHER_TO_REVIEW
    assert reason_text("") == TEACHER_TO_REVIEW
    assert reason_text("something new") == TEACHER_TO_REVIEW


def test_record_builder_uses_the_shared_mapping():
    assert builder.reason_text is reason_text

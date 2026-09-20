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
    ("input truncated", "The files were too large to read completely — check this part against the original"),
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


def test_every_reason_the_v2_pipeline_can_store_has_a_sentence():
    """The pipeline's reason constants and the mapping are one set: a new reason must land in both."""
    from sms.pipeline import marking_pipeline_v2 as p2
    from sms.reasons import REASON_TEXT

    codes = {p2.ILLEGIBLE, p2.NOT_IN_SCHEME, p2.REVIEWER_ESCALATED, p2.DISAGREE, p2.LOW_CONFIDENCE, p2.INPUT_TRUNCATED}
    assert len(codes) == 6 and codes <= set(REASON_TEXT)


def test_record_builder_uses_the_shared_mapping():
    assert builder.reason_text is reason_text

import pytest

from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.marking import MarkedQuestion, ReviewVerdict
from sms.schemas.feedback import FeedbackReport
from sms.schemas.reflection import ReflectionUpdate


def test_extracted_question_confidence_bounds():
    with pytest.raises(ValueError):
        ExtractedQuestion(q_id="q1", transcribed_answer="x=3", confidence=1.5)


def test_marked_question_fields():
    mq = MarkedQuestion(q_id="q1", criterion_scores=[1, 2], total=3, confidence=0.8, rationale="ok")
    assert mq.total == 3


def test_review_verdict_enum():
    assert ReviewVerdict.APPROVE.value == "APPROVE"
    assert ReviewVerdict.ADJUST.value == "ADJUST"
    assert ReviewVerdict.ESCALATE.value == "ESCALATE"


def test_schema_docstrings_present():
    for schema in (ExtractedScript, FeedbackReport, ReflectionUpdate):
        assert schema.__doc__ and schema.__doc__.strip()

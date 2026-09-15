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


def test_extraction_input_questions_default_empty_and_prompt_mentions_segmenting():
    import instructor, openai
    from sms.agents.extractor import build_extractor
    from sms.schemas.extraction import ExtractionInput
    from sms.schemas.scheme import Question
    assert ExtractionInput(assignment_context="c", images=[]).questions == []
    inp = ExtractionInput(assignment_context="c", images=[], questions=[Question(q_id="1a", text="Solve", max_marks=2)])
    assert inp.questions[0].q_id == "1a"
    agent = build_extractor(client=instructor.from_openai(openai.OpenAI(api_key="x")), model="m")
    prompt = agent.system_prompt_generator.generate_prompt()
    assert "segment" in prompt.lower() and "q_id" in prompt

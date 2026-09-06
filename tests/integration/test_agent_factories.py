import openai
import pytest

import instructor

from sms.agents.extractor import build_extractor
from sms.agents.feedback import build_feedback
from sms.agents.marker import build_marker
from sms.agents.reflection import build_reflection
from sms.agents.reviewer import build_reviewer
from sms.memory.db import Database
from sms.schemas.extraction import ExtractionInput, ExtractedScript
from sms.schemas.feedback import FeedbackInput, FeedbackReport
from sms.schemas.marking import MarkingInput, MarkedScript, ReviewInput, ReviewedScript
from sms.schemas.reflection import ReflectionInput, ReflectionUpdate


@pytest.fixture
def client():
    return instructor.from_openai(openai.OpenAI(api_key="test-key"))


def test_extractor_factory(client):
    agent = build_extractor(client=client, model="gpt-5-mini")
    assert agent.input_schema is ExtractionInput
    assert agent.output_schema is ExtractedScript


def test_marker_factory_registers_providers(client, tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    agent = build_marker(client=client, model="gpt-5-mini", subject="math", db=db)
    assert agent.input_schema is MarkingInput
    assert agent.output_schema is MarkedScript
    assert "rubric_notes" in agent.system_prompt_generator.context_providers
    assert "exemplar_cases" in agent.system_prompt_generator.context_providers


def test_reviewer_factory_registers_providers(client, tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    agent = build_reviewer(client=client, model="gpt-5-mini", subject="math", db=db)
    assert agent.input_schema is ReviewInput
    assert agent.output_schema is ReviewedScript
    assert "rubric_notes" in agent.system_prompt_generator.context_providers


def test_feedback_factory(client):
    agent = build_feedback(client=client, model="gpt-5-mini")
    assert agent.input_schema is FeedbackInput
    assert agent.output_schema is FeedbackReport


def test_reflection_factory(client):
    agent = build_reflection(client=client, model="gpt-5-mini")
    assert agent.input_schema is ReflectionInput
    assert agent.output_schema is ReflectionUpdate


def test_marker_rejects_unknown_subject(client):
    with pytest.raises(KeyError):
        build_marker(client=client, model="gpt-5-mini", subject="fiction", db=None)

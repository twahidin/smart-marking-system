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


def test_factories_accept_model_api_parameters():
    from sms.agents.extractor import build_extractor
    from sms.agents.feedback import build_feedback
    from sms.agents.marker import build_marker
    from sms.agents.reflection import build_reflection
    from sms.agents.reviewer import build_reviewer
    import instructor, openai
    client = instructor.from_openai(openai.OpenAI(api_key="x"))
    for build in (build_extractor, build_feedback, build_reflection):
        agent = build(client=client, model="m", model_api_parameters={"max_tokens": 10})
        assert agent.model_api_parameters == {"max_tokens": 10}
    for build in (build_marker, build_reviewer):
        agent = build(client=client, model="m", subject="math", model_api_parameters={"max_tokens": 10})
        assert agent.model_api_parameters == {"max_tokens": 10}


# --- v2 (per-part) marker and reviewer -----------------------------------------------------------

def test_marker_v2_factory_builds_per_kind_with_providers(client, tmp_path):
    from sms.agents.marker_v2 import build_marker_v2
    from sms.schemas.marking_v2 import MarkedScriptV2, MarkingInputV2

    db = Database(path=str(tmp_path / "s.db"))
    agent = build_marker_v2(client=client, model="gpt-5-mini", kind="mark_scheme", subject="math", db=db,
                            model_api_parameters={"max_tokens": 10})
    assert agent.input_schema is MarkingInputV2 and agent.output_schema is MarkedScriptV2
    assert agent.model_api_parameters == {"max_tokens": 10}
    assert "rubric_notes" in agent.system_prompt_generator.context_providers
    assert "exemplar_cases" in agent.system_prompt_generator.context_providers
    assert "in_scheme" in agent.system_prompt_generator.generate_prompt()
    rubric = build_marker_v2(client=client, model="m", kind="rubric", subject="language")
    assert rubric.system_prompt_generator.context_providers == {}
    assert "band" in rubric.system_prompt_generator.generate_prompt().lower()
    with pytest.raises(KeyError):
        build_marker_v2(client=client, model="m", kind="criteria", subject="math")
    with pytest.raises(KeyError):
        build_marker_v2(client=client, model="m", kind="mark_scheme", subject="fiction")


def test_reviewer_v2_factory_builds_per_kind_with_providers(client, tmp_path):
    from sms.agents.reviewer_v2 import build_reviewer_v2
    from sms.schemas.marking_v2 import ReviewInputV2, ReviewedScriptV2

    db = Database(path=str(tmp_path / "s.db"))
    agent = build_reviewer_v2(client=client, model="gpt-5-mini", kind="mark_scheme", subject="science", db=db,
                              model_api_parameters={"max_tokens": 3})
    assert agent.input_schema is ReviewInputV2 and agent.output_schema is ReviewedScriptV2
    assert agent.model_api_parameters == {"max_tokens": 3}
    assert "rubric_notes" in agent.system_prompt_generator.context_providers
    prompt = agent.system_prompt_generator.generate_prompt()
    assert "APPROVE" in prompt and "ESCALATE" in prompt
    assert "band" in build_reviewer_v2(client=client, model="m", kind="rubric").system_prompt_generator.generate_prompt().lower()
    with pytest.raises(KeyError):
        build_reviewer_v2(client=client, model="m", kind="criteria")

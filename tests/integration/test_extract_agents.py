import io

import instructor
import openai
import pytest
from PIL import Image

from sms.agents.paper_extractor import build_paper_extractor
from sms.agents.scheme_extractor import build_scheme_extractor
from sms.pipeline.marking_pipeline import image_from_bytes
from sms.schemas.scheme import (
    MarkPoint, MarkSchemeEntry, PaperExtract, PaperExtractInput, Question, RubricExtract, SchemeExtract,
    SchemeExtractInput,
)


@pytest.fixture
def client():
    return instructor.from_openai(openai.OpenAI(api_key="test-key"))


QUESTIONS = [Question(q_id="1a", text="Solve 2x + 3 = 7", max_marks=2), Question(q_id="1b", text="Hence find x^2", max_marks=1)]


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return buf.getvalue()


def stub_client(canned):
    """A real Instructor client (AgentConfig insists on one) whose completion call is replaced by a
    stub that records the call and returns the canned response_model instance."""
    client = instructor.from_openai(openai.OpenAI(api_key="test-key"))
    client.calls = []

    def create(**kwargs):
        client.calls.append(kwargs)
        assert isinstance(canned, kwargs["response_model"])
        return canned

    client.create = create
    return client


def test_paper_extractor_factory(client):
    agent = build_paper_extractor(client=client, model="gpt-5-mini")
    assert agent.input_schema is PaperExtractInput and agent.output_schema is PaperExtract
    assert build_paper_extractor(client=client, model="m", model_api_parameters={"max_tokens": 5}).model_api_parameters == {"max_tokens": 5}
    prompt = agent.system_prompt_generator.generate_prompt()
    assert "part" in prompt.lower() and "max_marks" in prompt


def test_scheme_extractor_factory_mark_scheme_lists_the_questions(client):
    agent = build_scheme_extractor(client=client, model="gpt-5-mini", kind="mark_scheme", questions=QUESTIONS)
    assert agent.input_schema is SchemeExtractInput and agent.output_schema is SchemeExtract
    prompt = agent.system_prompt_generator.generate_prompt()
    assert "1a" in prompt and "1b" in prompt and "Solve 2x + 3 = 7" in prompt
    assert "M1" in prompt and "A1" in prompt
    # without questions the prompt still builds, minus the question list
    bare = build_scheme_extractor(client=client, model="m", kind="mark_scheme").system_prompt_generator.generate_prompt()
    assert "Solve 2x + 3 = 7" not in bare


def test_scheme_extractor_factory_rubric_and_params(client):
    agent = build_scheme_extractor(client=client, model="gpt-5-mini", kind="rubric", questions=None,
                                   model_api_parameters={"max_tokens": 7})
    assert agent.output_schema is RubricExtract and agent.model_api_parameters == {"max_tokens": 7}
    assert "band" in agent.system_prompt_generator.generate_prompt().lower()


def test_scheme_extractor_rejects_other_kinds(client):
    with pytest.raises(ValueError):
        build_scheme_extractor(client=client, model="m", kind="criteria")


def test_paper_extractor_runs_against_a_stub_client():
    canned = PaperExtract(questions=QUESTIONS)
    stub = stub_client(canned)
    agent = build_paper_extractor(client=stub, model="gpt-5-mini")
    out = agent.run(PaperExtractInput(images=[image_from_bytes(_png())], hint="Sec 4 maths"))
    assert out is canned
    call = stub.calls[0]
    assert call["model"] == "gpt-5-mini" and call["response_model"] is PaperExtract
    assert call["messages"][0]["role"] == "system" and call["messages"][-1]["role"] == "user"


def test_scheme_extractor_runs_against_a_stub_client():
    canned = SchemeExtract(items=[MarkSchemeEntry(q_id="1a", answer="x = 2", marks=[MarkPoint(label="M1", marks=1)])])
    stub = stub_client(canned)
    agent = build_scheme_extractor(client=stub, model="m", kind="mark_scheme", questions=QUESTIONS)
    out = agent.run(SchemeExtractInput(images=[image_from_bytes(_png())], questions=QUESTIONS))
    assert out is canned and stub.calls[0]["response_model"] is SchemeExtract

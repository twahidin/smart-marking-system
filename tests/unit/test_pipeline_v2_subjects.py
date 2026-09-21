"""Task 7: threading MT's language and the subject notes (MT, Computing) through the v2 pipeline —
the extractor context, the marker/reviewer background, and student-facing feedback in the MT language.
Builds on the `Fake` agent, `db`/`png_bytes` fixtures, `EX`/`MARKED` fixtures and the `_template` helper
already in test_pipeline_v2_files (extended there with subject=/language=/kind= for this file)."""
import instructor
import openai
import pytest

from sms.agents.marker_v2 import build_marker_v2
from sms.agents.reviewer_v2 import build_reviewer_v2
from sms.pipeline.marking_pipeline_v2 import MarkingPipelineV2
from sms.schemas.feedback import FeedbackInput
from sms.schemas.marking import MarkedScript, ReviewedScript
from sms.schemas.marking_v2 import ReviewedScriptV2
from sms.subjects import scheme_prompts
from tests.unit.test_pipeline_v2_files import EX, FEEDBACK, MARKED, Fake, _template, db, png_bytes  # noqa: F401


@pytest.fixture
def client():
    # A real (but network-free) instructor client: AgentConfig validates `client` as an
    # instructor.core.client.Instructor instance, so a bare stand-in object fails pydantic validation —
    # this is the same fixture tests/integration/test_agent_factories.py already uses for the same reason.
    return instructor.from_openai(openai.OpenAI(api_key="test-key"))


def test_mt_language_reaches_extractor_context_and_feedback(db, png_bytes):  # noqa: F811
    vision, feedback = Fake(EX), Fake(FEEDBACK)
    p = MarkingPipelineV2(db=db, extractor=vision, marker=Fake(MARKED), reviewer=Fake(ReviewedScriptV2(verdicts=[])),
                          feedback=feedback, kind="rubric")
    p.run(images=[png_bytes], template=_template(subject="mt", language="zh", kind="rubric"))
    assert "Chinese" in vision.calls[0].assignment_context and "do not translate" in vision.calls[0].assignment_context
    assert feedback.calls[0].feedback_language == "zh"


def test_other_subjects_feedback_in_english(db, png_bytes):  # noqa: F811
    feedback = Fake(FEEDBACK)
    p = MarkingPipelineV2(db=db, extractor=Fake(EX), marker=Fake(MARKED), reviewer=Fake(ReviewedScriptV2(verdicts=[])),
                          feedback=feedback, kind="mark_scheme")
    p.run(images=[png_bytes], template=_template(subject="math", kind="mark_scheme"))
    assert feedback.calls[0].feedback_language == "en"


def test_mt_without_a_language_falls_back_to_english_feedback(db, png_bytes):  # noqa: F811
    """A legacy / unset assignment_templates.language: MT still gets a script's-language extractor note,
    but feedback falls back to English rather than crashing on a missing code."""
    vision, feedback = Fake(EX), Fake(FEEDBACK)
    p = MarkingPipelineV2(db=db, extractor=vision, marker=Fake(MARKED), reviewer=Fake(ReviewedScriptV2(verdicts=[])),
                          feedback=feedback, kind="rubric")
    p.run(images=[png_bytes], template=_template(subject="mt", language=None, kind="rubric"))
    assert "the script's language" in vision.calls[0].assignment_context
    assert feedback.calls[0].feedback_language == "en"


def test_extraction_cache_key_depends_on_language(db, png_bytes):  # noqa: F811
    """The same pages, marked for two different MT languages, must not share a cached extraction — the
    language is part of the extractor's context and so must be part of the cache key."""
    vision = Fake(EX)
    p = MarkingPipelineV2(db=db, extractor=vision, marker=Fake(MARKED), reviewer=Fake(ReviewedScriptV2(verdicts=[])),
                          feedback=Fake(FEEDBACK), kind="rubric")
    p.run(images=[png_bytes], template=_template(subject="mt", language="zh", kind="rubric"))
    p.run(images=[png_bytes], template=_template(subject="mt", language="ms", kind="rubric"))
    assert len(vision.calls) == 2
    assert "Chinese" in vision.calls[0].assignment_context
    assert "Malay" in vision.calls[1].assignment_context


def test_feedback_input_defaults_to_english():
    fi = FeedbackInput(reviewed=ReviewedScript(verdicts=[], final_marks=[], disagreement_flags=[]),
                       final_marks=MarkedScript(marks=[]), final_result_set=True)
    assert fi.feedback_language == "en"


def test_marker_v2_background_carries_computings_subject_note(client):
    agent = build_marker_v2(client=client, kind="mark_scheme", subject="computing")
    assert any("Never claim to have run anything" in b for b in agent.system_prompt_generator.background)


def test_reviewer_v2_background_carries_computings_subject_note(client):
    agent = build_reviewer_v2(client=client, kind="mark_scheme", subject="computing")
    assert any("Never claim to have run anything" in b for b in agent.system_prompt_generator.background)


def test_marker_v2_background_carries_mts_subject_note_with_a_generic_language_phrase(client):
    agent = build_marker_v2(client=client, kind="rubric", subject="mt")
    assert any("do not translate" in b and "the assignment's language" in b
              for b in agent.system_prompt_generator.background)
    assert not any("{language}" in b for b in agent.system_prompt_generator.background)


def test_reviewer_v2_background_carries_mts_subject_note(client):
    agent = build_reviewer_v2(client=client, kind="rubric", subject="mt")
    assert any("the assignment's language" in b for b in agent.system_prompt_generator.background)


def test_marker_v2_background_unaffected_for_a_subject_without_a_note(client):
    agent = build_marker_v2(client=client, kind="mark_scheme", subject="math")
    assert agent.system_prompt_generator.background == scheme_prompts.MARK_SCHEME["background"]

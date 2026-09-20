import pytest
from pydantic import ValidationError

from sms.pipeline.router import SubjectRouter
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.marking import ReviewVerdict
from sms.schemas.marking_v2 import (
    AllocationMark,
    DoublePenalty,
    MarkedScriptV2,
    MarkingInputV2,
    PartMark,
    ReviewInputV2,
    ReviewVerdictV2,
    ReviewedScriptV2,
    RubricMark,
)
from sms.schemas.scheme import Band, MarkPoint, MarkSchemeEntry, Question, RubricCriterionBands
from sms.subjects import scheme_prompts


def _part(total, got=(True, True), q_id="1a", **kw):
    return PartMark(
        q_id=q_id,
        awarded=[AllocationMark(label="M1", marks=1, got=got[0], why="substitution"),
                 AllocationMark(label="A1", marks=1, got=got[1], why="final answer")],
        total=total, justification="M1 for the substitution", **kw,
    )


def test_part_mark_defaults_and_bounds():
    p = _part(2)
    assert p.in_scheme is True and 0 <= p.confidence <= 1
    with pytest.raises(ValidationError):
        _part(2, confidence=1.5)
    with pytest.raises(ValidationError):
        PartMark(q_id="1a", awarded=[], total=-1, justification="", confidence=0.5)


def test_part_mark_total_must_equal_sum_of_got_allocations():
    ok = MarkedScriptV2(kind="mark_scheme", parts=[_part(1, got=(True, False))])
    assert ok.parts[0].total == 1
    with pytest.raises(ValidationError, match="1a"):
        _part(2, got=(True, False))
    # the validator lives on PartMark, so a reviewer's adjusted part is checked too
    with pytest.raises(ValidationError, match="1a"):
        ReviewVerdictV2(q_id="1a", verdict="ADJUST", adjusted={
            "q_id": "1a", "awarded": [{"label": "M1", "marks": 1, "got": True, "why": ""}], "total": 2,
            "justification": "", "confidence": 0.5})


def test_allocation_mark_marks_is_required():
    with pytest.raises(ValidationError):
        AllocationMark(label="M1", got=True, why="")


def test_marked_script_v2_skips_total_check_when_no_allocations_listed():
    # in_scheme=False parts may carry no allocation at all; the total is then the marker's proposal.
    p = PartMark(q_id="2", awarded=[], total=1, justification="different method", in_scheme=False, confidence=0.4)
    assert MarkedScriptV2(kind="mark_scheme", parts=[p]).parts[0].in_scheme is False


def test_marked_script_v2_rubric_kind():
    rm = RubricMark(criterion="Organisation", band="4", marks=8, descriptor_met="clear paragraphs",
                    justification="well ordered", confidence=0.8)
    s = MarkedScriptV2(kind="rubric", rubric=[rm])
    assert s.parts == [] and s.rubric[0].marks == 8
    with pytest.raises(ValidationError):
        MarkedScriptV2(kind="criteria", rubric=[rm])


def test_marking_input_v2_accepts_either_scheme_shape():
    extracted = ExtractedScript(questions=[ExtractedQuestion(q_id="1a", transcribed_answer="x=2", confidence=0.9)])
    qs = [Question(q_id="1a", text="Solve", max_marks=2)]
    ms = MarkingInputV2(kind="mark_scheme", extracted=extracted, questions=qs, notes="ECF applies",
                        scheme=[MarkSchemeEntry(q_id="1a", answer="x = 2", marks=[MarkPoint(label="M1", marks=1)])])
    assert isinstance(ms.scheme[0], MarkSchemeEntry)
    rb = MarkingInputV2(kind="rubric", extracted=extracted, questions=qs,
                        scheme=[RubricCriterionBands(criterion="Content", bands=[Band(band="A", marks=5)])])
    assert isinstance(rb.scheme[0], RubricCriterionBands)
    # plain dicts (straight from scheme_json) are coerced to the right model
    d = MarkingInputV2(kind="rubric", extracted=extracted, questions=[],
                       scheme=[{"criterion": "Content", "bands": [{"band": "A", "marks": 5}]}])
    assert isinstance(d.scheme[0], RubricCriterionBands) and d.notes == ""


def test_review_schemas_v2():
    extracted = ExtractedScript(questions=[])
    marks = MarkedScriptV2(kind="mark_scheme", parts=[_part(2)])
    ri = ReviewInputV2(kind="mark_scheme", extracted=extracted, questions=[], scheme=[], notes="", marks=marks)
    assert ri.marks.parts[0].q_id == "1a"
    v = ReviewVerdictV2(q_id="1a", verdict=ReviewVerdict.ADJUST, adjusted=_part(1, got=(True, False)), reviewer_note="A1 lost")
    assert isinstance(v.adjusted, PartMark)
    rv = ReviewVerdictV2(q_id="Content", verdict="ADJUST",
                         adjusted=RubricMark(criterion="Content", band="B", marks=4, justification="", confidence=0.7))
    assert isinstance(rv.adjusted, RubricMark) and rv.verdict is ReviewVerdict.ADJUST
    plain = ReviewVerdictV2(q_id="1a", verdict="APPROVE")
    assert plain.adjusted is None and plain.reviewer_note == ""
    assert ReviewedScriptV2(verdicts=[v, rv, plain]).verdicts[2].verdict is ReviewVerdict.APPROVE


def test_double_penalty_needs_at_least_two_parts():
    dp = DoublePenalty(error="sign error in 1a", q_ids=["1a", "1b"])
    assert dp.q_ids == ["1a", "1b"]
    with pytest.raises(ValidationError):
        DoublePenalty(error="sign error", q_ids=["1a"])


def test_reviewed_script_v2_double_penalties_defaults_empty():
    empty = ReviewedScriptV2(verdicts=[])
    assert empty.double_penalties == []
    flagged = ReviewedScriptV2(verdicts=[], double_penalties=[DoublePenalty(error="carried the same slip twice",
                                                                             q_ids=["1a", "1b"])])
    assert flagged.double_penalties[0].error == "carried the same slip twice"


def test_scheme_prompt_configs_have_marker_and_reviewer_keys():
    keys = {"background", "steps", "output_instructions", "reviewer_background", "reviewer_steps",
            "reviewer_output_instructions"}
    for cfg in (scheme_prompts.MARK_SCHEME, scheme_prompts.RUBRIC):
        assert keys <= set(cfg) and all(cfg[k] for k in keys)
    joined = " ".join(" ".join(v) for v in scheme_prompts.MARK_SCHEME.values()).lower()
    assert "in_scheme" in joined and "never invent" in joined and "method" in joined
    assert "double_penalties" in joined and "never deduct the same slip twice" in joined
    rubric_joined = " ".join(" ".join(v) for v in scheme_prompts.RUBRIC.values()).lower()
    assert "band" in rubric_joined
    assert "a weakness counts once" in rubric_joined and "double_penalties" in rubric_joined


def test_router_scheme_prompt_config():
    router = SubjectRouter()
    assert router.scheme_prompt_config("mark_scheme") is scheme_prompts.MARK_SCHEME
    assert router.scheme_prompt_config("rubric") is scheme_prompts.RUBRIC
    with pytest.raises(KeyError):
        router.scheme_prompt_config("criteria")


def test_text_segment_input_carries_every_source_and_the_paper_parts():
    from sms.schemas.segment import TextSegmentInput, TextSource

    inp = TextSegmentInput(assignment_context="computing submission, 1 part(s)",
                           questions=[Question(q_id="1", text="Print 1", max_marks=1)],
                           sources=[TextSource(name="handwritten pages", text="[1] plan"),
                                    TextSource(name="prog.py", text="   1 | print(1)")])
    assert [s.name for s in inp.sources] == ["handwritten pages", "prog.py"]
    assert isinstance(inp.questions[0], Question) and inp.model_dump()["sources"][1]["text"] == "   1 | print(1)"
    # questions is optional (a paper with no listed parts), sources is not
    assert TextSegmentInput(assignment_context="c", sources=[]).questions == []
    with pytest.raises(ValidationError):
        TextSegmentInput(assignment_context="c")


def test_text_segmenter_asks_for_the_source_tag_the_detail_page_matches_on():
    """get_submission marks a file as used when the transcription contains "[<file name>", so the
    segmenter's instructions must ask for exactly that prefix."""
    import instructor
    import openai

    from sms.agents.text_segmenter import build_text_segmenter
    from sms.schemas.segment import TextSegmentInput

    agent = build_text_segmenter(client=instructor.from_openai(openai.OpenAI(api_key="x")), model="m")
    assert agent.input_schema is TextSegmentInput and agent.output_schema is ExtractedScript
    prompt = agent.system_prompt_generator.generate_prompt()
    assert "[prog.py L12-30]" in prompt and "[results.xlsx Marks!B4]" in prompt and "[handwritten pages]" in prompt
    assert "verbatim" in prompt.lower() and "one ExtractedQuestion per listed part" in prompt

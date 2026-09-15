import pytest
from pydantic import ValidationError

from sms.pipeline.router import SubjectRouter
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.marking import ReviewVerdict
from sms.schemas.marking_v2 import (
    AllocationMark,
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


def test_scheme_prompt_configs_have_marker_and_reviewer_keys():
    keys = {"background", "steps", "output_instructions", "reviewer_background", "reviewer_steps",
            "reviewer_output_instructions"}
    for cfg in (scheme_prompts.MARK_SCHEME, scheme_prompts.RUBRIC):
        assert keys <= set(cfg) and all(cfg[k] for k in keys)
    joined = " ".join(" ".join(v) for v in scheme_prompts.MARK_SCHEME.values()).lower()
    assert "in_scheme" in joined and "never invent" in joined and "method" in joined
    assert "band" in " ".join(" ".join(v) for v in scheme_prompts.RUBRIC.values()).lower()


def test_router_scheme_prompt_config():
    router = SubjectRouter()
    assert router.scheme_prompt_config("mark_scheme") is scheme_prompts.MARK_SCHEME
    assert router.scheme_prompt_config("rubric") is scheme_prompts.RUBRIC
    with pytest.raises(KeyError):
        router.scheme_prompt_config("criteria")

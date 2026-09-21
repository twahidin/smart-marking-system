"""Slice 4, cross-subject rule: an error costs marks exactly once. The reviewer flags every part or
criterion the same slip was deducted under (double_penalties), and the merge restores all but the
first deduction — or, when it cannot tell which allocation to restore, escalates instead of guessing.

Builds its own `_pipeline_with` / `_template` helpers (the brief's stubs by those names do not exist
yet) on top of the `Fake` agent, `db` fixture and feedback stub already in test_pipeline_v2_files."""
from sms.pipeline.marking_pipeline_v2 import MarkingPipelineV2
from sms.schemas.marking_v2 import (
    AllocationMark,
    DoublePenalty,
    MarkedScriptV2,
    PartMark,
    ReviewedScriptV2,
    RubricMark,
)
from tests.unit.test_pipeline_v2_files import EX, Fake, _feedback_stub, db  # noqa: F401 (db is a fixture)


def _part(q, allocs):
    return PartMark(q_id=q, awarded=[AllocationMark(label=l, marks=m, got=g) for l, m, g in allocs],
                    total=sum(m for _, m, g in allocs if g))


def _pipeline_with(db, marked, reviewed, kind="mark_scheme"):
    return MarkingPipelineV2(db=db, extractor=Fake(EX), segmenter=None, marker=Fake(marked), reviewer=Fake(reviewed),
                             feedback=_feedback_stub(), kind=kind)


def _template(parts):
    """A mark-scheme template with one row per part, its allocations covering every label (M1/A1/B1)
    the tests award, so normalise_against_scheme always finds the part's labels in the row."""
    return {"subject": "math", "context": "", "scheme_kind": "mark_scheme",
            "questions": [{"q_id": q, "text": q, "max_marks": 2} for q in parts],
            "scheme": [{"q_id": q, "answer": "", "marks": [{"label": l, "marks": 1} for l in ("M1", "A1", "B1")],
                       "notes": ""} for q in parts]}


def _rubric_template(criteria):
    return {"subject": "language", "context": "", "scheme_kind": "rubric",
            "questions": [{"q_id": c, "text": c, "max_marks": 4} for c in criteria],
            "scheme": [{"criterion": c, "bands": [{"band": "A", "marks": 4}, {"band": "B", "marks": 2}]}
                      for c in criteria]}


def test_double_penalty_restores_the_later_part(db):
    marked = MarkedScriptV2(kind="mark_scheme", parts=[_part("1a", [("M1", 1, True), ("A1", 1, False)]),
                                                        _part("1b", [("B1", 1, False)])])
    reviewed = ReviewedScriptV2(verdicts=[], double_penalties=[DoublePenalty(error="sign error in 1a", q_ids=["1a", "1b"])])
    p = _pipeline_with(db, marked, reviewed)
    res = p.run(images=[b"x"], template=_template(parts=["1a", "1b"]))
    b = next(x for x in res.final.parts if x.q_id == "1b")
    assert b.total == 1 and b.awarded[0].got and b.awarded[0].why == "already penalised in 1a"
    assert "1b" not in res.escalations


def test_double_penalty_matches_a_scheme_that_spells_ids_with_brackets(db):
    """The reviewer's q_ids are normalised before lookup ("1(b)" -> "1b"), so a scheme written "1(a)"
    is matched rather than silently missed — and the restored part still names the raw "1(a)"."""
    marked = MarkedScriptV2(kind="mark_scheme", parts=[_part("1(a)", [("M1", 1, True), ("A1", 1, False)]),
                                                        _part("1(b)", [("B1", 1, False)])])
    reviewed = ReviewedScriptV2(verdicts=[], double_penalties=[DoublePenalty(error="sign error in 1(a)",
                                                                             q_ids=["1(a)", "1(b)"])])
    p = _pipeline_with(db, marked, reviewed)
    res = p.run(images=[b"x"], template=_template(parts=["1(a)", "1(b)"]))
    b = next(x for x in res.final.parts if x.q_id == "1(b)")
    assert b.total == 1 and b.awarded[0].got and b.awarded[0].why == "already penalised in 1(a)"
    assert "already penalised in 1(a)." in b.justification
    assert "1(b)" not in res.escalations


def test_double_penalty_ambiguous_escalates(db):
    marked = MarkedScriptV2(kind="mark_scheme", parts=[_part("1a", [("A1", 1, False)]),
                                                        _part("1b", [("M1", 1, False), ("A1", 1, False)])])
    reviewed = ReviewedScriptV2(verdicts=[], double_penalties=[DoublePenalty(error="same slip", q_ids=["1a", "1b"])])
    res = _pipeline_with(db, marked, reviewed).run(images=[b"x"], template=_template(parts=["1a", "1b"]))
    assert res.escalations["1b"] == "double penalty"


def test_double_penalty_rubric_keeps_band_and_notes(db):
    # rubric kind: the later criterion keeps its band; justification gains the note; no escalation.
    marked = MarkedScriptV2(kind="rubric", rubric=[
        RubricMark(criterion="Content", band="A", marks=4, justification="strong ideas", confidence=0.9),
        RubricMark(criterion="Language", band="B", marks=2, justification="accurate but plain", confidence=0.9),
    ])
    reviewed = ReviewedScriptV2(verdicts=[], double_penalties=[DoublePenalty(error="repeated grammar slip",
                                                                             q_ids=["Content", "Language"])])
    p = _pipeline_with(db, marked, reviewed, kind="rubric")
    res = p.run(images=[b"x"], template=_rubric_template(criteria=["Content", "Language"]))
    content = next(r for r in res.final.rubric if r.criterion == "Content")
    language = next(r for r in res.final.rubric if r.criterion == "Language")
    assert content.band == "A" and content.marks == 4
    assert language.band == "B" and language.marks == 2
    assert "already penalised under Content" in language.justification
    assert "Language" not in res.escalations

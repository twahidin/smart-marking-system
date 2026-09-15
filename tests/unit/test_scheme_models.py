import pytest
from pydantic import ValidationError

from sms.schemas.scheme import (
    Band, MarkPoint, MarkSchemeEntry, Question, RubricCriterionBands, norm_qid, q_label, scheme_total,
)


def test_models_are_re_exported_from_the_assignments_service():
    from sms.web.services import assignments as svc
    assert svc.Question is Question and svc.MarkPoint is MarkPoint and svc.MarkSchemeEntry is MarkSchemeEntry
    assert svc.Band is Band and svc.RubricCriterionBands is RubricCriterionBands


def test_models_validate_as_before():
    q = Question(q_id="1a", text="Solve", max_marks=2)
    assert q.model_dump() == {"q_id": "1a", "text": "Solve", "max_marks": 2}
    e = MarkSchemeEntry(q_id="1a", answer="x = 2", marks=[MarkPoint(label="M1", marks=1)])
    assert e.notes == "" and e.marks[0].marks == 1
    r = RubricCriterionBands(criterion="Structure", bands=[Band(band="A", marks=5)])
    assert r.bands[0].descriptor == ""
    with pytest.raises(ValidationError):
        Question(q_id="", max_marks=1)
    with pytest.raises(ValidationError):
        MarkPoint(label="M1", marks=-1)


@pytest.mark.parametrize("q_id, label", [
    ("1a", "1(a)"),
    ("2bii", "2(b)(ii)"),
    ("3", "3"),
    ("1ai", "1(a)(i)"),
    ("4iii", "4(iii)"),
    ("q1", "Q1"),
    ("Q2b", "Q2(b)"),
    ("1A", "1(a)"),
    ("3(c)", "3(c)"),
    ("Section A", "Section A"),
    ("", ""),
])
def test_q_label(q_id, label):
    assert q_label(q_id) == label


@pytest.mark.parametrize("raw, norm", [
    ("1a", "1a"), ("Q1(a)", "1a"), ("q1 (a)", "1a"), ("1 a", "1a"), ("1.a", "1a"), ("2(b)(ii)", "2bii"), ("Q2", "2"),
    ("1A", "1a"), (" 1a ", "1a"), ("Content", "content"), ("Section A", "sectiona"), ("", ""), (None, ""),
    ("quality", "quality"),  # only a leading q followed by a digit is a question prefix
])
def test_norm_qid(raw, norm):
    assert norm_qid(raw) == norm


QS = [Question(q_id="1a", text="", max_marks=2), Question(q_id="1b", text="", max_marks=3),
      Question(q_id="2", text="", max_marks=4)]
MS = [MarkSchemeEntry(q_id="1a", answer="", marks=[MarkPoint(label="M1", marks=1), MarkPoint(label="A1", marks=1)]),
      MarkSchemeEntry(q_id="2", answer="", marks=[MarkPoint(label="B1", marks=1)])]
RB = [RubricCriterionBands(criterion="Content", bands=[Band(band="A", marks=6), Band(band="B", marks=4)]),
      RubricCriterionBands(criterion="Style", bands=[Band(band="A", marks=4)])]


def test_scheme_total_mark_scheme_uses_scheme_rows_then_question_marks():
    # 1a: scheme allocation (2); 1b: no scheme row -> question max (3); 2: scheme allocation (1)
    assert scheme_total("mark_scheme", QS, MS) == 6
    # without questions the scheme rows alone count
    assert scheme_total("mark_scheme", [], MS) == 3
    # dicts (as stored in questions_json / scheme_json) are accepted too
    assert scheme_total("mark_scheme", [q.model_dump() for q in QS], [m.model_dump() for m in MS]) == 6


def test_scheme_total_rubric_sums_the_top_band_per_criterion():
    assert scheme_total("rubric", QS, RB) == 10
    assert scheme_total("rubric", [], []) == 0


def test_scheme_total_criteria_sums_question_marks():
    assert scheme_total("criteria", QS, []) == 9
    assert scheme_total("criteria", [], []) == 0

import json

import pytest

from sms.memory.db import Database
from sms.pipeline.marking_pipeline_v2 import MarkingPipelineV2, MarkingResultV2, feedback_input_for_v2
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript, ExtractionInput
from sms.schemas.feedback import FeedbackInput, FeedbackReport, PerQuestionComment
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
from sms.schemas.scheme import MarkSchemeEntry, Question, RubricCriterionBands


class StubAgent:
    def __init__(self, canned):
        self._canned = canned
        self.calls = []

    def run(self, user_input):
        self.calls.append(user_input)
        return self._canned


QUESTIONS = [{"q_id": "1a", "text": "Solve 3x = 9", "max_marks": 2}, {"q_id": "1b", "text": "Hence x^2", "max_marks": 1}]
SCHEME = [
    {"q_id": "1a", "answer": "x = 3", "marks": [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 1}], "notes": ""},
    {"q_id": "1b", "answer": "9", "marks": [{"label": "B1", "marks": 1}], "notes": "ECF from 1a"},
]
TEMPLATE = {"subject": "math", "context": "ECF applies", "scheme_kind": "mark_scheme",
            "questions": QUESTIONS, "scheme": SCHEME}
RUBRIC_SCHEME = [{"criterion": "Content", "bands": [{"band": "A", "marks": 5, "descriptor": "rich"}, {"band": "B", "marks": 3, "descriptor": "some"}]},
                 {"criterion": "Language", "bands": [{"band": "A", "marks": 5, "descriptor": "accurate"}]}]
RUBRIC_TEMPLATE = {"subject": "language", "context": "", "scheme_kind": "rubric",
                   "questions": [{"q_id": "1", "text": "Essay", "max_marks": 10}], "scheme": RUBRIC_SCHEME}


def extracted(illegible=()):
    return ExtractedScript(questions=[
        ExtractedQuestion(q_id="1a", transcribed_answer="x=3", workings="3x=9", confidence=0.9,
                          needs_human_transcription="1a" in illegible),
        ExtractedQuestion(q_id="1b", transcribed_answer="9", confidence=0.9, needs_human_transcription="1b" in illegible),
    ])


def part(q_id, got, total, **kw):
    labels = {"1a": [("M1", 1), ("A1", 1)], "1b": [("B1", 1)]}[q_id]
    return PartMark(q_id=q_id, awarded=[AllocationMark(label=l, marks=m, got=g, why="w") for (l, m), g in zip(labels, got)],
                    total=total, justification=f"{q_id} justified", **kw)


def marked(parts=None):
    return MarkedScriptV2(kind="mark_scheme", parts=parts or [part("1a", (True, True), 2, confidence=0.9),
                                                             part("1b", (True,), 1, confidence=0.9)])


def reviewed(*verdicts):
    default = {"1a": ReviewVerdictV2(q_id="1a", verdict=ReviewVerdict.APPROVE),
               "1b": ReviewVerdictV2(q_id="1b", verdict=ReviewVerdict.APPROVE)}
    for v in verdicts:
        default[v.q_id] = v
    return ReviewedScriptV2(verdicts=list(default.values()))


FEEDBACK = FeedbackReport(summary="Nice.", strengths=["method"],
                          per_question_comments=[PerQuestionComment(q_id="1a", comment="c", suggested_action="a")],
                          improvement_plan=["p"], next_steps=["n"])


def make(tmp_path, *, extract=None, mark=None, review=None, kind="mark_scheme", threshold=0.0):
    db = Database(path=str(tmp_path / "s.db"))
    agents = dict(extractor=StubAgent(extract or extracted()), marker=StubAgent(mark or marked()),
                  reviewer=StubAgent(review or reviewed()), feedback=StubAgent(FEEDBACK))
    return db, agents, MarkingPipelineV2(db=db, kind=kind, confidence_threshold=threshold, **agents)


def queue(db):
    return {r["q_id"]: r["reason"] for r in db.query("SELECT q_id, reason FROM teacher_queue WHERE status = 'pending'")}


def test_v2_happy_path_persists_version_2_shape(tmp_path):
    db, agents, pipeline = make(tmp_path)
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) VALUES ('t', 'math', 'c', '{}', 'marking') RETURNING id")
    result = pipeline.run(images=[b"img"], template=TEMPLATE, submission_id=sid)
    assert isinstance(result, MarkingResultV2)
    assert result.escalations == {} and result.feedback is FEEDBACK
    assert [p.q_id for p in result.final.parts] == ["1a", "1b"] and result.final.kind == "mark_scheme"
    run = db.query("SELECT * FROM marking_runs WHERE run_id = :r", {"r": result.run_id})[0]
    assert run["final_status"] == "complete" and run["subject"] == "math" and run["submission_id"] == sid
    final = json.loads(run["final_marks_json"])
    assert final["version"] == 2 and final["kind"] == "mark_scheme" and final["rubric"] == []
    assert final["parts"][0]["q_id"] == "1a" and final["parts"][0]["awarded"][0]["label"] == "M1"
    assert json.loads(run["rubric_json"]) == {"scheme_kind": "mark_scheme", "questions": QUESTIONS, "scheme": SCHEME, "notes": "ECF applies"}
    assert json.loads(run["marks_json"])["parts"][0]["justification"] == "1a justified"
    assert json.loads(run["reviewed_json"])["verdicts"][0]["verdict"] == "APPROVE"
    assert db.query("SELECT marks_version FROM submissions WHERE id = :id", {"id": sid})[0]["marks_version"] == 2
    assert queue(db) == {}


def test_v2_extractor_gets_the_questions_and_marker_reviewer_get_the_scheme(tmp_path):
    db, agents, pipeline = make(tmp_path)
    pipeline.run(images=[b"img"], template=TEMPLATE)
    ex = agents["extractor"].calls[0]
    assert isinstance(ex, ExtractionInput) and [q.q_id for q in ex.questions] == ["1a", "1b"]
    assert "ECF applies" in ex.assignment_context
    mi = agents["marker"].calls[0]
    assert isinstance(mi, MarkingInputV2) and mi.kind == "mark_scheme" and mi.notes == "ECF applies"
    assert isinstance(mi.scheme[0], MarkSchemeEntry) and isinstance(mi.questions[0], Question)
    ri = agents["reviewer"].calls[0]
    assert isinstance(ri, ReviewInputV2) and ri.scheme == mi.scheme and ri.questions == mi.questions
    # anti-anchoring: the reviewer sees allocations and totals but no justifications
    assert ri.marks.parts[0].total == 2 and ri.marks.parts[0].awarded[0].got is True
    assert ri.marks.parts[0].justification == "" and ri.marks.parts[0].awarded[0].why == ""
    assert agents["marker"].calls[0].extracted.questions[0].transcribed_answer == "x=3"


def test_v2_extraction_cache_keyed_by_pages_and_questions(tmp_path):
    db, agents, pipeline = make(tmp_path)
    pipeline.run(images=[b"img"], template=TEMPLATE)
    pipeline.run(images=[b"img"], template=TEMPLATE)
    assert len(agents["extractor"].calls) == 1
    other = dict(TEMPLATE, questions=QUESTIONS[:1])
    pipeline.run(images=[b"img"], template=other)
    assert len(agents["extractor"].calls) == 2


def test_v2_escalates_illegible(tmp_path):
    db, agents, pipeline = make(tmp_path, extract=extracted(illegible=("1b",)))
    result = pipeline.run(images=[b"img"], template=TEMPLATE)
    assert result.escalations == {"1b": "illegible"}
    assert queue(db) == {"1b": "illegible"}
    assert db.query("SELECT final_status FROM marking_runs")[0]["final_status"] == "escalated"


def test_v2_escalates_not_in_scheme_even_when_reviewer_approves(tmp_path):
    db, agents, pipeline = make(tmp_path, mark=marked([part("1a", (True, False), 1, in_scheme=False, confidence=0.9),
                                                       part("1b", (True,), 1, confidence=0.9)]))
    result = pipeline.run(images=[b"img"], template=TEMPLATE)
    assert result.escalations == {"1a": "not in scheme"} and queue(db) == {"1a": "not in scheme"}
    assert result.final.parts[0].in_scheme is False and result.final.parts[0].total == 1


def test_v2_escalates_reviewer_escalate(tmp_path):
    db, agents, pipeline = make(tmp_path, review=reviewed(ReviewVerdictV2(q_id="1a", verdict=ReviewVerdict.ESCALATE, reviewer_note="odd")))
    result = pipeline.run(images=[b"img"], template=TEMPLATE)
    assert result.escalations == {"1a": "reviewer escalated"} and queue(db) == {"1a": "reviewer escalated"}


def test_v2_escalates_low_confidence(tmp_path):
    db, agents, pipeline = make(tmp_path, threshold=0.6,
                                mark=marked([part("1a", (True, True), 2, confidence=0.4), part("1b", (True,), 1, confidence=0.9)]))
    result = pipeline.run(images=[b"img"], template=TEMPLATE)
    assert result.escalations == {"1a": "low confidence"} and queue(db) == {"1a": "low confidence"}
    # no threshold: the same marks pass
    (tmp_path / "b").mkdir()
    db2, _, p2 = make(tmp_path / "b", mark=marked([part("1a", (True, True), 2, confidence=0.4), part("1b", (True,), 1, confidence=0.9)]))
    assert p2.run(images=[b"img"], template=TEMPLATE).escalations == {}


def test_v2_adjust_with_same_total_is_a_silent_correction(tmp_path):
    adjusted = part("1a", (False, True), 1, confidence=0.95)
    # marker said M1 only; reviewer says A1 only — same total, allocation corrected quietly
    db, agents, pipeline = make(tmp_path, mark=marked([part("1a", (True, False), 1, confidence=0.9), part("1b", (True,), 1, confidence=0.9)]),
                                review=reviewed(ReviewVerdictV2(q_id="1a", verdict=ReviewVerdict.ADJUST, adjusted=adjusted, reviewer_note="A1 not M1")))
    result = pipeline.run(images=[b"img"], template=TEMPLATE)
    assert result.escalations == {}
    final_1a = result.final.parts[0]
    assert [a.got for a in final_1a.awarded] == [False, True] and final_1a.total == 1 and final_1a.q_id == "1a"
    assert queue(db) == {}


def test_v2_adjust_with_different_total_or_no_part_is_a_disagreement(tmp_path):
    db, agents, pipeline = make(tmp_path, review=reviewed(
        ReviewVerdictV2(q_id="1a", verdict=ReviewVerdict.ADJUST, adjusted=part("1a", (True, False), 1), reviewer_note="A1 lost"),
        ReviewVerdictV2(q_id="1b", verdict=ReviewVerdict.ADJUST, reviewer_note="forgot the part")))
    result = pipeline.run(images=[b"img"], template=TEMPLATE)
    assert result.escalations == {"1a": "marker/reviewer disagree", "1b": "marker/reviewer disagree"}
    assert queue(db) == {"1a": "marker/reviewer disagree", "1b": "marker/reviewer disagree"}
    # the marker's part is kept as the proposal; the reviewer's view lives in reviewed_json
    assert result.final.parts[0].total == 2
    assert json.loads(db.query("SELECT reviewed_json FROM marking_runs")[0]["reviewed_json"])["verdicts"][0]["adjusted"]["total"] == 1


def test_v2_illegible_wins_over_other_reasons(tmp_path):
    db, agents, pipeline = make(tmp_path, extract=extracted(illegible=("1a",)), threshold=0.99,
                                review=reviewed(ReviewVerdictV2(q_id="1a", verdict=ReviewVerdict.ESCALATE)))
    result = pipeline.run(images=[b"img"], template=TEMPLATE)
    assert result.escalations["1a"] == "illegible"


def test_v2_rubric_kind(tmp_path):
    marks = MarkedScriptV2(kind="rubric", rubric=[
        RubricMark(criterion="Content", band="A", marks=5, descriptor_met="rich", justification="rich ideas", confidence=0.9),
        RubricMark(criterion="Language", band="A", marks=5, justification="accurate", confidence=0.3),
    ])
    review = ReviewedScriptV2(verdicts=[
        ReviewVerdictV2(q_id="Content", verdict=ReviewVerdict.ADJUST,
                        adjusted=RubricMark(criterion="Content", band="B", marks=3, justification="some ideas", confidence=0.8)),
        ReviewVerdictV2(q_id="Language", verdict=ReviewVerdict.APPROVE),
    ])
    ex = ExtractedScript(questions=[ExtractedQuestion(q_id="1", transcribed_answer="essay text", confidence=0.9)])
    db, agents, pipeline = make(tmp_path, kind="rubric", extract=ex, mark=marks, review=review, threshold=0.5)
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) VALUES ('t', 'language', 'c', '{}', 'marking') RETURNING id")
    result = pipeline.run(images=[b"img"], template=RUBRIC_TEMPLATE, submission_id=sid)
    assert result.escalations == {"Content": "marker/reviewer disagree", "Language": "low confidence"}
    assert result.final.kind == "rubric" and result.final.parts == []
    assert isinstance(agents["marker"].calls[0].scheme[0], RubricCriterionBands)
    assert agents["reviewer"].calls[0].marks.rubric[0].justification == "" and agents["reviewer"].calls[0].marks.rubric[0].descriptor_met == ""
    run = db.query("SELECT * FROM marking_runs")[0]
    final = json.loads(run["final_marks_json"])
    assert final["version"] == 2 and final["kind"] == "rubric" and final["parts"] == [] and final["rubric"][0]["criterion"] == "Content"
    assert json.loads(run["rubric_json"])["scheme_kind"] == "rubric" and run["subject"] == "language"
    assert queue(db) == {"Content": "marker/reviewer disagree", "Language": "low confidence"}
    assert db.query("SELECT marks_version FROM submissions WHERE id = :id", {"id": sid})[0]["marks_version"] == 2


def test_v2_rubric_illegible_response_escalates_every_criterion(tmp_path):
    marks = MarkedScriptV2(kind="rubric", rubric=[RubricMark(criterion="Content", band="A", marks=5, confidence=0.9),
                                                  RubricMark(criterion="Language", band="A", marks=5, confidence=0.9)])
    ex = ExtractedScript(questions=[ExtractedQuestion(q_id="1", transcribed_answer="??", confidence=0.1, needs_human_transcription=True)])
    review = ReviewedScriptV2(verdicts=[ReviewVerdictV2(q_id="Content", verdict="APPROVE"), ReviewVerdictV2(q_id="Language", verdict="APPROVE")])
    db, agents, pipeline = make(tmp_path, kind="rubric", extract=ex, mark=marks, review=review)
    result = pipeline.run(images=[b"img"], template=RUBRIC_TEMPLATE)
    assert result.escalations == {"Content": "illegible", "Language": "illegible"}


def test_v2_feedback_input_adapter(tmp_path):
    db, agents, pipeline = make(tmp_path, review=reviewed(ReviewVerdictV2(q_id="1b", verdict=ReviewVerdict.ESCALATE, reviewer_note="hmm")))
    pipeline.run(images=[b"img"], template=TEMPLATE)
    fi = agents["feedback"].calls[0]
    assert isinstance(fi, FeedbackInput) and fi.final_result_set is False
    q1a = fi.final_marks.marks[0]
    assert q1a.q_id == "1a" and q1a.total == 2 and q1a.criterion_scores == [1, 1] and q1a.rationale == "1a justified"
    assert fi.reviewed.verdicts[1].verdict is ReviewVerdict.ESCALATE and fi.reviewed.verdicts[1].reviewer_note == "hmm"
    assert fi.reviewed.disagreement_flags == ["1b"]
    # rubric marks speak in band language
    rub = MarkedScriptV2(kind="rubric", rubric=[RubricMark(criterion="Content", band="B", marks=3, justification="some ideas", confidence=0.8)])
    fi2 = feedback_input_for_v2(rub, ReviewedScriptV2(verdicts=[]), escalations={})
    assert fi2.final_result_set is True and fi2.final_marks.marks[0].q_id == "Content"
    assert fi2.final_marks.marks[0].total == 3 and "Band B" in fi2.final_marks.marks[0].rationale


def test_v2_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError):
        make(tmp_path, kind="criteria")

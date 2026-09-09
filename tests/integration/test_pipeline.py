import pytest

from sms.memory.db import Database
from sms.pipeline.marking_pipeline import MarkingResult, MarkingPipeline
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.feedback import FeedbackReport, PerQuestionComment
from sms.schemas.marking import (
    MarkedQuestion,
    MarkedScript,
    ReviewVerdict,
    ReviewVerdictItem,
    ReviewedScript,
)


class StubAgent:
    """Duck-typed AtomicAgent stub: records calls, returns canned output."""

    def __init__(self, canned, input_schema, output_schema):
        self._canned = canned
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.calls = []

    def run(self, user_input):
        self.calls.append(user_input)
        return self._canned


EXTRACTED_STUB = ExtractedScript(questions=[
    ExtractedQuestion(q_id="q1", transcribed_answer="x=3", workings="3x=9", confidence=0.95),
])

MARKED_STUB = MarkedScript(marks=[
    MarkedQuestion(q_id="q1", criterion_scores=[2, 1], total=3, confidence=0.7,
                   rationale="method right", evidence="3x=9"),
])

REVIEWED_STUB = ReviewedScript(
    verdicts=[ReviewVerdictItem(q_id="q1", verdict=ReviewVerdict.APPROVE, reviewer_note="agree")],
    final_marks=[],
    disagreement_flags=[],
)

FEEDBACK_STUB = FeedbackReport(
    summary="Great work overall.",
    strengths=["Clear method"],
    per_question_comments=[PerQuestionComment(q_id="q1", comment="Good method", suggested_action="Practise rounding")],
    improvement_plan=["Rounding practice"],
    next_steps=["Retry worksheet"],
)


@pytest.fixture
def rubric():
    from sms.schemas.marking import Rubric, RubricCriterion
    return Rubric(criterion_defs=[
        RubricCriterion(id="c1", description="method", max_score=2),
        RubricCriterion(id="c2", description="accuracy", max_score=2),
    ])


def test_pipeline_runs_and_persists(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    extractor = StubAgent(EXTRACTED_STUB, None, None)
    marker = StubAgent(MARKED_STUB, None, None)
    reviewer = StubAgent(REVIEWED_STUB, None, None)
    feedback = StubAgent(FEEDBACK_STUB, None, None)
    pipeline = MarkingPipeline(db=db, extractor=extractor, marker=marker,
                               reviewer=reviewer, feedback=feedback, subject="math")
    result = pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)

    assert isinstance(result, MarkingResult)
    assert result.feedback.summary.startswith("Great")
    assert result.escalations == []
    assert result.final_marks.marks[0].q_id == "q1"
    rows = db.query("SELECT * FROM marking_runs WHERE final_status = 'complete'")
    assert rows and rows[0]["feedback_json"]


def test_pipeline_escalates_on_escalate_verdict(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    reviewed = ReviewedScript(
        verdicts=[ReviewVerdictItem(q_id="q1", verdict=ReviewVerdict.ESCALATE, reviewer_note="ambiguous rubric")],
        final_marks=[],
        disagreement_flags=["q1"],
    )
    pipeline = MarkingPipeline(
        db=db,
        extractor=StubAgent(EXTRACTED_STUB, None, None),
        marker=StubAgent(MARKED_STUB, None, None),
        reviewer=StubAgent(reviewed, None, None),
        feedback=StubAgent(FEEDBACK_STUB, None, None),
        subject="math",
    )
    result = pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    assert result.escalations == ["q1"]
    queued = db.query("SELECT * FROM teacher_queue WHERE status = 'pending'")
    assert queued and queued[0]["q_id"] == "q1"


def test_pipeline_reviewer_input_strips_marker_rationale(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    reviewer = StubAgent(REVIEWED_STUB, None, None)
    pipeline = MarkingPipeline(
        db=db,
        extractor=StubAgent(EXTRACTED_STUB, None, None),
        marker=StubAgent(MARKED_STUB, None, None),
        reviewer=reviewer,
        feedback=StubAgent(FEEDBACK_STUB, None, None),
        subject="math",
    )
    pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    review_input = reviewer.calls[0]
    assert review_input.marks.marks[0].rationale == ""
    assert review_input.marks.marks[0].criterion_scores == [2, 1]


def test_pipeline_uses_extraction_cache_on_second_run(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    extractor = StubAgent(EXTRACTED_STUB, None, None)
    pipeline = MarkingPipeline(
        db=db,
        extractor=extractor,
        marker=StubAgent(MARKED_STUB, None, None),
        reviewer=StubAgent(REVIEWED_STUB, None, None),
        feedback=StubAgent(FEEDBACK_STUB, None, None),
        subject="math",
    )
    pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    assert len(extractor.calls) == 1


def test_pipeline_escalates_low_confidence_below_threshold(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    low_conf_marked = MarkedScript(marks=[
        MarkedQuestion(q_id="q1", criterion_scores=[2, 1], total=3, confidence=0.3,
                       rationale="unsure", evidence="3x=9"),
    ])
    pipeline = MarkingPipeline(
        db=db,
        extractor=StubAgent(EXTRACTED_STUB, None, None),
        marker=StubAgent(low_conf_marked, None, None),
        reviewer=StubAgent(REVIEWED_STUB, None, None),
        feedback=StubAgent(FEEDBACK_STUB, None, None),
        subject="math",
        confidence_threshold=0.5,
    )
    result = pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    assert result.escalations == ["q1"]
    queued = db.query("SELECT * FROM teacher_queue WHERE status = 'pending'")
    assert queued and queued[0]["reason"] == "low marker confidence"


def test_pipeline_no_escalation_above_threshold(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    pipeline = MarkingPipeline(
        db=db,
        extractor=StubAgent(EXTRACTED_STUB, None, None),
        marker=StubAgent(MARKED_STUB, None, None),
        reviewer=StubAgent(REVIEWED_STUB, None, None),
        feedback=StubAgent(FEEDBACK_STUB, None, None),
        subject="math",
        confidence_threshold=0.5,
    )
    result = pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    assert result.escalations == []


def test_pipeline_escalates_illegible_transcription(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    illegible_extract = ExtractedScript(questions=[
        ExtractedQuestion(q_id="q1", transcribed_answer="??", workings="", confidence=0.1,
                           needs_human_transcription=True),
    ])
    pipeline = MarkingPipeline(
        db=db,
        extractor=StubAgent(illegible_extract, None, None),
        marker=StubAgent(MARKED_STUB, None, None),
        reviewer=StubAgent(REVIEWED_STUB, None, None),
        feedback=StubAgent(FEEDBACK_STUB, None, None),
        subject="math",
    )
    result = pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    assert result.escalations == ["q1"]
    queued = db.query("SELECT * FROM teacher_queue WHERE status = 'pending'")
    assert queued and queued[0]["reason"] == "illegible transcription"

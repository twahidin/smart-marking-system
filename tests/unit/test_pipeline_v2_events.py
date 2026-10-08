"""The pipeline tells a listener when each crew member starts and finishes, and what they thought
per part. A listener that raises never breaks marking."""
from sms.pipeline.events import StageEvent
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.marking import ReviewVerdict
from sms.schemas.marking_v2 import AllocationMark, MarkedScriptV2, PartMark, ReviewVerdictV2, ReviewedScriptV2
from tests.unit.test_pipeline_v2_double_penalty import _template
from tests.unit.test_pipeline_v2_files import Fake, _feedback_stub, db  # noqa: F401
from sms.pipeline.marking_pipeline_v2 import MarkingPipelineV2

EX = ExtractedScript(questions=[
    ExtractedQuestion(q_id="1a", transcribed_answer="x=-2", workings="", confidence=0.9),
    ExtractedQuestion(q_id="1b", transcribed_answer="?", workings="", confidence=0.2, needs_human_transcription=True),
])
MARKED = MarkedScriptV2(kind="mark_scheme", parts=[
    PartMark(q_id="1a", awarded=[AllocationMark(label="M1", marks=1, got=True)], total=1, justification="M1 for factorising"),
    PartMark(q_id="1b", awarded=[AllocationMark(label="B1", marks=1, got=False)], total=0, justification="B1 lost: illegible"),
])
REVIEWED = ReviewedScriptV2(verdicts=[
    ReviewVerdictV2(q_id="1a", verdict=ReviewVerdict.APPROVE, reviewer_note="Agree"),
    ReviewVerdictV2(q_id="1b", verdict=ReviewVerdict.ESCALATE, reviewer_note="Cannot read it either"),
])


def _pipeline(db):
    return MarkingPipelineV2(db=db, extractor=Fake(EX), segmenter=None, marker=Fake(MARKED), reviewer=Fake(REVIEWED),
                             feedback=_feedback_stub(), kind="mark_scheme")


def test_events_follow_the_stages_with_per_part_notes(db):
    seen = []
    p = _pipeline(db)
    p.on_event = seen.append
    p.run(images=[b"x"], template=_template(parts=["1a", "1b"]))
    flow = [(e.stage, e.kind) for e in seen if e.kind != "note"]
    assert flow == [("read", "started"), ("read", "finished"), ("mark", "started"), ("mark", "finished"),
                    ("check", "started"), ("check", "finished"), ("feedback", "started"), ("feedback", "finished"),
                    ("done", "finished")]
    notes = [(e.stage, e.q_id, e.note) for e in seen if e.kind == "note"]
    assert ("read", "1b", "Hard to read — the teacher may need to look at the page") in notes
    assert ("mark", "1a", "M1 for factorising") in notes
    assert ("check", "1b", "ESCALATE: Cannot read it either") in notes
    assert any(s == "done" and q == "1b" for s, q, _ in notes)


def test_a_failing_listener_never_fails_marking(db):
    def boom(_: StageEvent) -> None:
        raise RuntimeError("listener broke")
    p = _pipeline(db)
    p.on_event = boom
    res = p.run(images=[b"x"], template=_template(parts=["1a", "1b"]))
    assert res.run_id


def test_no_listener_is_the_default(db):
    assert _pipeline(db).on_event is None

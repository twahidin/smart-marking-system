"""The v2 pipeline's file paths: a files-only submission is segmented instead of transcribed, a mixed
one feeds the page transcription into the segmenter as one more source, and a pages-only script never
touches the segmenter at all."""
import io

import pytest
from PIL import Image

from sms.files.render import Rendered
from sms.memory.db import Database
from sms.pipeline.marking_pipeline_v2 import MarkingPipelineV2
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript, ExtractionInput
from sms.schemas.feedback import FeedbackReport
from sms.schemas.marking_v2 import AllocationMark, MarkedScriptV2, PartMark, ReviewedScriptV2
from sms.schemas.segment import TextSegmentInput


class Fake:
    def __init__(self, out):
        self.out, self.calls = out, []

    def run(self, inp):
        self.calls.append(inp)
        return self.out


EX = ExtractedScript(questions=[ExtractedQuestion(q_id="1", transcribed_answer="[prog.py L1-3] print(1)",
                                                  workings="", confidence=0.9)])
MARKED = MarkedScriptV2(kind="mark_scheme", parts=[PartMark(q_id="1", awarded=[AllocationMark(label="B1", marks=1, got=True)],
                                                            total=1)])
FEEDBACK = FeedbackReport(summary="Nice.", strengths=["structure"], per_question_comments=[],
                          improvement_plan=["p"], next_steps=["n"])


def _template(subject="computing", language=None, kind="mark_scheme"):
    """`subject`/`language`/`kind` let subject/language-threading tests (test_pipeline_v2_subjects.py)
    reuse this same shape; `language` mirrors assignment_templates.language (None unless the assignment
    is MT) and `kind` picks a scheme shaped for a mark scheme or a rubric."""
    if kind == "rubric":
        scheme = [{"criterion": "1", "bands": [{"band": "A", "marks": 1, "descriptor": ""}]}]
    else:
        scheme = [{"q_id": "1", "answer": "print(1)", "marks": [{"label": "B1", "marks": 1}], "notes": ""}]
    return {"subject": subject, "context": "Write a program that prints 1", "scheme_kind": kind,
            "questions": [{"q_id": "1", "text": "Print 1", "max_marks": 1}],
            "scheme": scheme, "language": language}


def _feedback_stub():
    return Fake(FEEDBACK)


@pytest.fixture
def db(tmp_path):
    return Database(path=str(tmp_path / "s.db"))


@pytest.fixture
def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def _pipeline(db, vision, segmenter):
    return MarkingPipelineV2(db=db, extractor=vision, segmenter=segmenter, marker=Fake(MARKED),
                             reviewer=Fake(ReviewedScriptV2(verdicts=[])), feedback=_feedback_stub(),
                             kind="mark_scheme")


def test_files_only_skips_vision_and_segments(db):
    vision, seg = Fake(EX), Fake(EX)
    p = _pipeline(db, vision, seg)
    p.run(images=[], template=_template(), files=[Rendered("prog.py", "py", "syntax: ok\n   1 | print(1)\n", "1 line", False)])
    assert vision.calls == [] and len(seg.calls) == 1
    assert [s.name for s in seg.calls[0].sources] == ["prog.py"]
    assert isinstance(seg.calls[0], TextSegmentInput)
    assert [q.q_id for q in seg.calls[0].questions] == ["1"]
    assert "computing" in seg.calls[0].assignment_context


def test_mixed_feeds_transcription_into_segmenter(db, png_bytes):
    vision, seg = Fake(EX), Fake(EX)
    p = _pipeline(db, vision, seg)
    p.run(images=[png_bytes], template=_template(), files=[Rendered("s.xlsx", "xlsx", "sheet Marks\n  B1 = 1\n", "1 sheet", False)])
    assert len(vision.calls) == 1 and len(seg.calls) == 1
    assert isinstance(vision.calls[0], ExtractionInput)
    assert [s.name for s in seg.calls[0].sources] == ["handwritten pages", "s.xlsx"]
    # the pages arrive tagged in the same form the segmenter is asked to quote back
    assert "[handwritten pages q1] [prog.py L1-3] print(1)" in seg.calls[0].sources[0].text


def test_an_unanswered_page_part_is_left_out_of_the_page_source(db, png_bytes):
    """A part with nothing on the pages must not contribute a bare tag for the segmenter to copy."""
    blank = ExtractedScript(questions=[ExtractedQuestion(q_id="1", transcribed_answer="  ", workings="",
                                                         confidence=0.4)])
    vision, seg = Fake(blank), Fake(EX)
    p = _pipeline(db, vision, seg)
    p.run(images=[png_bytes], template=_template(), files=[Rendered("prog.py", "py", "x", "1 line", False)])
    assert seg.calls[0].sources[0].text == ""


def test_mixed_keeps_the_pages_illegible_flag_through_the_segmenter(db, png_bytes):
    """The segmenter reads the transcription as text and cannot tell what the camera could not read:
    a part the pages flagged illegible still reaches the teacher."""
    illegible = ExtractedScript(questions=[ExtractedQuestion(q_id="1", transcribed_answer="x", workings="",
                                                             confidence=0.2, needs_human_transcription=True)])
    p = _pipeline(db, Fake(illegible), Fake(EX))
    res = p.run(images=[png_bytes], template=_template(),
                files=[Rendered("s.xlsx", "xlsx", "sheet Marks\n  B1 = 1\n", "1 sheet", False)])
    assert res.escalations == {"1": "illegible"}
    assert res.extracted.questions[0].needs_human_transcription is True
    assert res.extracted.questions[0].confidence == 0.2  # the lower of the two


def test_files_only_never_inherits_a_page_flag(db):
    """No pages, nothing to carry: the segmenter's own confidence stands."""
    p = _pipeline(db, Fake(EX), Fake(EX))
    res = p.run(images=[], template=_template(), files=[Rendered("prog.py", "py", "x", "1 line", False)])
    assert res.escalations == {} and res.extracted.questions[0].confidence == 0.9


def test_pages_only_never_calls_segmenter(db, png_bytes):
    vision, seg = Fake(EX), Fake(EX)
    _pipeline(db, vision, seg).run(images=[png_bytes], template=_template())
    assert seg.calls == []


def test_truncated_file_escalates_every_part(db):
    p = _pipeline(db, Fake(EX), Fake(EX))
    res = p.run(images=[], template=_template(), files=[Rendered("big.py", "py", "…", "x", True)])
    assert res.escalations == {"1": "input truncated"}


def test_truncated_file_does_not_overwrite_a_stronger_reason(db):
    """A part the marker already flagged keeps its own reason: truncation only fills the gaps."""
    illegible = ExtractedScript(questions=[ExtractedQuestion(q_id="1", transcribed_answer="", confidence=0.1,
                                                             needs_human_transcription=True)])
    p = _pipeline(db, Fake(illegible), Fake(illegible))
    res = p.run(images=[], template=_template(), files=[Rendered("big.py", "py", "…", "x", True)])
    assert res.escalations == {"1": "illegible"}


def test_truncation_escalations_reach_the_queue(db):
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) "
                    "VALUES ('t', 'computing', 'c', '{}', 'marking') RETURNING id")
    p = _pipeline(db, Fake(EX), Fake(EX))
    res = p.run(images=[], template=_template(), files=[Rendered("big.py", "py", "…", "x", True)], submission_id=sid)
    rows = db.query("SELECT q_id, reason FROM teacher_queue WHERE run_id = :r", {"r": res.run_id})
    assert [(r["q_id"], r["reason"]) for r in rows] == [("1", "input truncated")]
    assert db.query("SELECT final_status FROM marking_runs WHERE run_id = :r", {"r": res.run_id})[0]["final_status"] == "escalated"


def test_segment_is_cached_by_source_hashes(db):
    seg = Fake(EX)
    p = _pipeline(db, Fake(EX), seg)
    f = [Rendered("prog.py", "py", "x", "1 line", False)]
    p.run(images=[], template=_template(), files=f)
    p.run(images=[], template=_template(), files=f)
    assert len(seg.calls) == 1


def test_changed_notes_is_a_different_segmentation(db):
    """The notes reach the segmenter inside its context, so they belong in the cache digest — as they
    already do for `_extract`. The same file marked under different notes is segmented twice."""
    seg = Fake(EX)
    p = _pipeline(db, Fake(EX), seg)
    f = [Rendered("prog.py", "py", "x", "1 line", False)]
    t = _template()
    p.run(images=[], template={**t, "context": "Sec 3 · loops"}, files=f)
    p.run(images=[], template={**t, "context": "Sec 3 · loops, ignore the comments"}, files=f)
    assert len(seg.calls) == 2
    assert seg.calls[0].assignment_context != seg.calls[1].assignment_context


def test_changed_file_text_is_a_different_segmentation(db):
    seg = Fake(EX)
    p = _pipeline(db, Fake(EX), seg)
    p.run(images=[], template=_template(), files=[Rendered("prog.py", "py", "x", "1 line", False)])
    p.run(images=[], template=_template(), files=[Rendered("prog.py", "py", "y", "1 line", False)])
    assert len(seg.calls) == 2


def test_files_without_a_segmenter_is_a_clear_error(db):
    p = MarkingPipelineV2(db=db, extractor=Fake(EX), marker=Fake(MARKED), reviewer=Fake(ReviewedScriptV2(verdicts=[])),
                          feedback=_feedback_stub(), kind="mark_scheme")
    with pytest.raises(RuntimeError, match="cannot read files"):
        p.run(images=[], template=_template(), files=[Rendered("prog.py", "py", "x", "1 line", False)])


def test_run_stays_backwards_compatible_without_files(db, png_bytes):
    """Existing callers pass (images, template, submission_id) only."""
    vision = Fake(EX)
    p = MarkingPipelineV2(db=db, extractor=vision, marker=Fake(MARKED), reviewer=Fake(ReviewedScriptV2(verdicts=[])),
                          feedback=_feedback_stub(), kind="mark_scheme")
    res = p.run([png_bytes], _template(), None)
    assert res.escalations == {} and len(vision.calls) == 1

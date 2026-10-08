import json

import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.marking import ReviewVerdict
from sms.schemas.marking_v2 import AllocationMark, MarkedScriptV2, PartMark, ReviewVerdictV2, ReviewedScriptV2
from sms.storage import PageStorage
from sms.worker.remark_job import run_remark_job
from tests.unit.test_pipeline_v2_files import Fake

SCHEME = [{"q_id": "1a", "answer": "x=3", "marks": [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 1}], "notes": ""},
          {"q_id": "1b", "answer": "9", "marks": [{"label": "B1", "marks": 1}], "notes": ""}]
QUESTIONS = [{"q_id": "1a", "text": "Solve", "max_marks": 2}, {"q_id": "1b", "text": "Hence", "max_marks": 1}]


@pytest.fixture
def env(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0))
    tid = db.insert("INSERT INTO assignment_templates (title, subject, context, rubric_json, scheme_kind, questions_json, scheme_json) "
                    "VALUES ('W', 'math', '', '{\"criterion_defs\": []}', 'mark_scheme', :q, :s) RETURNING id", {"q": json.dumps(QUESTIONS), "s": json.dumps(SCHEME)})
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status, assignment_id, scheme_kind) "
                    "VALUES ('s', 'math', '', '{}', 'done', :t, 'mark_scheme') RETURNING id", {"t": tid})
    cid = db.insert("INSERT INTO student_corrections (submission_id, q_id, reason, text, status) VALUES (:s, '1b', 'sign', 'x^2 = 9', 'submitted') RETURNING id", {"s": sid})
    return db, store, PageStorage(tmp_path / "data"), cid


class _Pipe:
    def __init__(self, marked, reviewed):
        self.marker, self.reviewer = Fake(marked), Fake(reviewed)

    def _blind_script(self, m):
        return m


def test_remark_stores_mark_note_and_status(env):
    db, store, storage, cid = env
    marked = MarkedScriptV2(kind="mark_scheme", parts=[PartMark(q_id="1b", awarded=[AllocationMark(label="B1", marks=1, got=True)], total=1, justification="9 is right")])
    reviewed = ReviewedScriptV2(verdicts=[ReviewVerdictV2(q_id="1b", verdict=ReviewVerdict.APPROVE, reviewer_note="Agree")])
    pipe = _Pipe(marked, reviewed)
    run_remark_job(db, storage, store, cid, pipeline_factory=lambda **k: pipe)
    r = db.query("SELECT * FROM student_corrections WHERE id = :id", {"id": cid})[0]
    assert r["status"] == "remarked" and r["remark_total"] == 1 and r["remark_max"] == 1
    assert r["remark_note"] == "Marker: 9 is right\nChecker: APPROVE: Agree" and r["remark_run_id"]
    sent = pipe.marker.calls[0]
    assert [q.q_id for q in sent.questions] == ["1b"] and [s.q_id for s in sent.scheme] == ["1b"]
    assert sent.extracted.questions[0].transcribed_answer == "x^2 = 9"


def test_reviewer_adjustment_wins(env):
    db, store, storage, cid = env
    marked = MarkedScriptV2(kind="mark_scheme", parts=[PartMark(q_id="1b", awarded=[AllocationMark(label="B1", marks=1, got=True)], total=1)])
    adjusted = PartMark(q_id="1b", awarded=[AllocationMark(label="B1", marks=1, got=False)], total=0)
    reviewed = ReviewedScriptV2(verdicts=[ReviewVerdictV2(q_id="1b", verdict=ReviewVerdict.ADJUST, adjusted=adjusted, reviewer_note="Still 6")])
    run_remark_job(db, storage, store, cid, pipeline_factory=lambda **k: _Pipe(marked, reviewed))
    assert db.query("SELECT remark_total FROM student_corrections WHERE id = :id", {"id": cid})[0]["remark_total"] == 0


def test_failure_records_the_error_and_reraises(env):
    db, store, storage, cid = env

    class Boom:
        marker = type("M", (), {"run": staticmethod(lambda inp: (_ for _ in ()).throw(RuntimeError("provider down")))})()

    with pytest.raises(RuntimeError):
        run_remark_job(db, storage, store, cid, pipeline_factory=lambda **k: Boom())
    r = db.query("SELECT status, error FROM student_corrections WHERE id = :id", {"id": cid})[0]
    assert r["status"] == "submitted" and "provider down" in r["error"]


@pytest.mark.parametrize("final", ["released", "rejected"])
def test_final_corrections_are_skipped_without_error(env, final):
    db, store, storage, cid = env
    db.execute("UPDATE student_corrections SET status = :s WHERE id = :id", {"s": final, "id": cid})

    def factory(**k):
        pytest.fail("the pipeline must not be built for a final correction")

    run_remark_job(db, storage, store, cid, pipeline_factory=factory)
    r = db.query("SELECT status, remark_total, error FROM student_corrections WHERE id = :id", {"id": cid})[0]
    assert r["status"] == final and r["remark_total"] is None and r["error"] is None


def test_photo_correction_is_transcribed_first(env):
    db, store, storage, cid = env
    sid = db.query("SELECT submission_id FROM student_corrections WHERE id = :id", {"id": cid})[0]["submission_id"]
    digest, rel = storage.put_jpeg(b"img")
    pid = db.insert("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height, kind) "
                    "VALUES (:s, 1000, :d, :p, 0, 0, 'correction') RETURNING id", {"s": sid, "d": digest, "p": rel})
    db.execute("UPDATE student_corrections SET text = NULL, page_id = :p WHERE id = :id", {"p": pid, "id": cid})
    marked = MarkedScriptV2(kind="mark_scheme", parts=[PartMark(q_id="1b", awarded=[AllocationMark(label="B1", marks=1, got=True)], total=1)])
    pipe = _Pipe(marked, ReviewedScriptV2(verdicts=[]))
    seen = {}

    def _extract(images, subject, questions, notes, language="en"):
        seen["images"], seen["qs"] = images, [q.q_id for q in questions]
        return ExtractedScript(questions=[ExtractedQuestion(q_id="1b", transcribed_answer="x = 3", workings="step", confidence=0.9)])

    pipe._extract = _extract
    run_remark_job(db, storage, store, cid, pipeline_factory=lambda **k: pipe)
    assert seen["images"] == [b"img"] and seen["qs"] == ["1b"]
    assert pipe.marker.calls[0].extracted.questions[0].transcribed_answer == "x = 3\nstep"
    r = db.query("SELECT status, remark_note FROM student_corrections WHERE id = :id", {"id": cid})[0]
    assert r["status"] == "remarked" and r["remark_note"] == "Marker:"

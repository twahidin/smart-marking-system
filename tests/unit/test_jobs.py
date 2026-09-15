import pytest

from sms.memory.db import Database
from sms.worker.jobs import JobStore


@pytest.fixture
def db(tmp_path):
    return Database(path=str(tmp_path / "s.db"))


def _submission(db):
    return db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) "
                     "VALUES ('s', 'math', '', '{}', 'uploaded') RETURNING id")


def test_enqueue_claim_finish(db):
    js = JobStore(db)
    sid = _submission(db)
    jid = js.enqueue("mark", sid)
    job = js.claim()
    assert job["id"] == jid and job["status"] == "running" and job["attempts"] == 1
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "marking"
    assert js.claim() is None
    js.finish(jid)
    assert db.query("SELECT status, finished_at FROM jobs WHERE id = ?", (jid,))[0]["status"] == "done"


def test_retry_later_respects_not_before(db):
    js = JobStore(db)
    sid = _submission(db)
    jid = js.enqueue("mark", sid)
    js.claim()
    js.retry_later(jid, delay_s=3600, error="HTTP 429")
    row = db.query("SELECT status, error, not_before FROM jobs WHERE id = ?", (jid,))[0]
    assert row["status"] == "queued" and row["error"] == "HTTP 429" and row["not_before"]
    assert js.claim() is None
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "queued"
    js.retry_later(jid, delay_s=0, error="x")
    assert js.claim()["id"] == jid


def test_fail_marks_submission_failed(db):
    js = JobStore(db)
    sid = _submission(db)
    jid = js.enqueue("mark", sid)
    js.claim()
    js.fail(jid, "boom")
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "failed"
    assert js.job_for_submission(sid)["error"] == "boom"


def test_reset_running(db):
    js = JobStore(db)
    sid = _submission(db)
    js.enqueue("mark", sid)
    js.claim()
    assert js.reset_running() == 1
    assert js.claim() is not None


def test_heartbeat(db):
    js = JobStore(db)
    assert js.last_heartbeat() is None
    js.heartbeat()
    assert js.last_heartbeat()
    js.heartbeat()
    assert db.query("SELECT COUNT(*) AS c FROM worker_heartbeat")[0]["c"] == 1


def test_claim_orders_by_created(db):
    js = JobStore(db)
    a = js.enqueue("mark", _submission(db))
    b = js.enqueue("mark", _submission(db))
    assert js.claim()["id"] == a and js.claim()["id"] == b

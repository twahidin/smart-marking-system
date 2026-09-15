import threading

import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore
from sms.storage import PageStorage
from sms.worker.jobs import JobStore
from sms.worker.mark_job import run_mark_job
from sms.worker.worker import Worker


@pytest.fixture
def env(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0))
    storage = PageStorage(tmp_path / "data")
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) VALUES "
                    "('s', 'math', 'ctx', '{\"criterion_defs\": [{\"id\": \"c1\", \"description\": \"d\", \"max_score\": 2}]}', 'uploaded') RETURNING id")
    digest, rel = storage.put_jpeg(b"\xff\xd8\xffjpegbytes")
    db.execute("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height) VALUES (?, 0, ?, ?, 10, 10)",
               (sid, digest, rel))
    return db, store, storage, sid


class FakePipeline:
    def __init__(self, escalations):
        self.escalations = escalations
        self.calls = []

    def run(self, images, assignment_context, rubric, submission_id=None):
        self.calls.append((images, assignment_context, rubric, submission_id))
        from sms.pipeline.marking_pipeline import MarkingResult
        from sms.schemas.extraction import ExtractedScript
        from sms.schemas.marking import MarkedScript
        return MarkingResult(run_id="r1", extracted=ExtractedScript(questions=[]),
                             final_marks=MarkedScript(marks=[]), escalations=self.escalations)


def test_run_mark_job_done(env):
    db, store, storage, sid = env
    fp = FakePipeline(escalations=[])
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: fp)
    assert fp.calls[0][0] == [b"\xff\xd8\xffjpegbytes"] and fp.calls[0][3] == sid
    row = db.query("SELECT status, run_id FROM submissions WHERE id = ?", (sid,))[0]
    assert row["status"] == "done" and row["run_id"] == "r1"


def test_run_mark_job_needs_you(env):
    db, store, storage, sid = env
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline(["q2"]))
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "needs_you"


def test_run_mark_job_without_key_raises_non_retryable(env):
    db, store, storage, sid = env
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=0))
    db.execute("UPDATE settings SET api_key_enc = NULL")
    with pytest.raises(RuntimeError, match="API key"):
        run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline([]))


def test_worker_success_path(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("mark", sid)
    w = Worker(db, storage, store, runner=lambda *a, **k: None)
    assert w.run_once() is True
    assert db.query("SELECT status FROM jobs")[0]["status"] == "done"
    assert w.run_once() is False


def test_worker_retryable_error_requeues_with_backoff(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("mark", sid)
    import httpx, openai
    err = openai.APIStatusError("rl", response=httpx.Response(429, request=httpx.Request("POST", "https://x")), body=None)

    def runner(*a, **k):
        raise err

    w = Worker(db, storage, store, runner=runner)
    w.run_once()
    row = db.query("SELECT status, attempts, not_before, error FROM jobs")[0]
    assert row["status"] == "queued" and row["attempts"] == 1 and row["not_before"] and "429" in row["error"]


def test_worker_non_retryable_fails(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("mark", sid)

    def runner(*a, **k):
        raise ValueError("bad rubric")

    Worker(db, storage, store, runner=runner).run_once()
    assert db.query("SELECT status FROM jobs")[0]["status"] == "failed"
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "failed"


def test_worker_gives_up_after_max_attempts(env):
    db, store, storage, sid = env
    js = JobStore(db)
    jid = js.enqueue("mark", sid)
    db.execute("UPDATE jobs SET attempts = 4 WHERE id = ?", (jid,))

    def runner(*a, **k):
        raise TimeoutError()

    Worker(db, storage, store, runner=runner).run_once()
    assert db.query("SELECT status FROM jobs")[0]["status"] == "failed"


def test_worker_resets_running_on_start_and_heartbeats(env):
    db, store, storage, sid = env
    js = JobStore(db)
    js.enqueue("mark", sid)
    js.claim()
    stop = threading.Event()
    w = Worker(db, storage, store, runner=lambda *a, **k: None, poll_s=0.01)
    t = w.start_thread(stop)
    import time
    for _ in range(200):
        if db.query("SELECT status FROM jobs")[0]["status"] == "done":
            break
        time.sleep(0.01)
    stop.set(); t.join(timeout=2)
    assert db.query("SELECT status FROM jobs")[0]["status"] == "done"
    assert js.last_heartbeat()


def test_worker_retries_reset_running_on_db_outage_then_recovers(env):
    """reset_running() failing on the first attempt (e.g. a brief DB outage at startup)
    must not kill the worker thread — it should keep retrying the reset each iteration
    (inside the same try/except that logs 'worker loop error') and only claim jobs once
    the reset finally succeeds."""
    db, store, storage, sid = env
    js = JobStore(db)
    js.enqueue("mark", sid)
    js.claim()  # simulate a job left "running" by a crashed previous worker

    orig_reset_running = js.reset_running
    calls = {"n": 0}

    def flaky_reset_running():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db unreachable")
        return orig_reset_running()

    js.reset_running = flaky_reset_running

    stop = threading.Event()
    w = Worker(db, storage, store, runner=lambda *a, **k: None, poll_s=0.01)
    w.jobs = js
    t = w.start_thread(stop)
    import time
    for _ in range(300):
        if db.query("SELECT status FROM jobs")[0]["status"] == "done":
            break
        time.sleep(0.01)
    stop.set(); t.join(timeout=2)
    assert db.query("SELECT status FROM jobs")[0]["status"] == "done"
    assert calls["n"] >= 2
    assert js.last_heartbeat()


def test_worker_reuses_rate_limit_bucket_across_jobs_until_rpm_changes(env):
    db, store, storage, sid = env
    js = JobStore(db)
    js.enqueue("mark", sid)
    js.enqueue("mark", sid)

    seen_buckets = []

    def runner(*a, **k):
        seen_buckets.append(k["bucket"])

    w = Worker(db, storage, store, runner=runner)
    w.run_once()
    w.run_once()
    assert seen_buckets[0] is seen_buckets[1]
    assert seen_buckets[0].rpm == 0

    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=5))
    js.enqueue("mark", sid)
    w.run_once()
    assert seen_buckets[2] is not seen_buckets[0]
    assert seen_buckets[2].rpm == 5

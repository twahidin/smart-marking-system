import json

import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore
from sms.schemas.scheme import (
    Band, MarkPoint, MarkSchemeEntry, PaperExtract, Question, RubricCriterionBands, RubricExtract, SchemeExtract,
)
from sms.storage import PageStorage
from sms.worker.extract_jobs import run_paper_extract_job, run_scheme_extract_job
from sms.worker.jobs import JobStore
from sms.worker.worker import Worker


@pytest.fixture
def env(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0))
    storage = PageStorage(tmp_path / "data")
    tid = db.insert("INSERT INTO assignment_templates (title, subject, rubric_json, scheme_kind) "
                    "VALUES ('Paper 1', 'math', '{\"criterion_defs\": []}', 'mark_scheme') RETURNING id")
    return db, store, storage, tid


def _add_pages(db, storage, tid, kind, n=2):
    ids = []
    for i in range(n):
        digest, rel = storage.put_jpeg(f"\xff\xd8\xff{kind}{i}".encode("latin-1"))
        ids.append(db.insert("INSERT INTO pages (template_id, kind, page_index, sha256, storage_path, width, height) "
                             "VALUES (:t, :k, :i, :h, :p, 10, 10) RETURNING id", {"t": tid, "k": kind, "i": i, "h": digest, "p": rel}))
    return ids


class FakeAgent:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.inputs = []

    def run(self, user_input):
        self.inputs.append(user_input)
        if self.error:
            raise self.error
        return self.result


QUESTIONS = [Question(q_id="1a", text="Solve", max_marks=2), Question(q_id="1b", text="Hence", max_marks=1)]


def test_paper_extract_job_writes_questions_json(env):
    db, store, storage, tid = env
    _add_pages(db, storage, tid, "paper", n=2)
    _add_pages(db, storage, tid, "scheme", n=1)
    agent = FakeAgent(PaperExtract(questions=QUESTIONS))
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return agent

    assert run_paper_extract_job(db, storage, store, tid, agent_factory=factory) == 2
    assert seen["settings"].model == "gpt-5-mini" and seen["db"] is db and seen["bucket"] is not None
    # only the paper's two pages are sent, in order, as images
    assert len(agent.inputs[0].images) == 2 and "Paper 1" in agent.inputs[0].hint
    row = db.query("SELECT questions_json FROM assignment_templates WHERE id = :t", {"t": tid})[0]
    assert json.loads(row["questions_json"]) == [q.model_dump() for q in QUESTIONS]


def test_paper_extract_job_uses_the_assignments_own_provider_and_bucket(env):
    db, store, storage, tid = env
    _add_pages(db, storage, tid, "paper", n=2)
    store.save(Settings(provider="openrouter", model="z-ai/glm-5.3-flash", api_key="or-key", rpm_limit=60))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=60))
    db.execute("UPDATE assignment_templates SET provider = 'openrouter', model = 'openrouter/auto' WHERE id = :t",
               {"t": tid})
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return FakeAgent(PaperExtract(questions=QUESTIONS))

    from sms.providers.ratelimit import BucketPool
    pool = BucketPool()
    assert run_paper_extract_job(db, storage, store, tid, agent_factory=factory, bucket_pool=pool) == 2
    assert (seen["settings"].provider, seen["settings"].model, seen["settings"].api_key) == ("openrouter", "openrouter/auto", "or-key")
    assert seen["bucket"] is pool.get("openrouter", 60)


def test_paper_extract_job_requires_paper_pages_and_key(env):
    db, store, storage, tid = env
    with pytest.raises(ValueError, match="question paper"):
        run_paper_extract_job(db, storage, store, tid, agent_factory=lambda **kw: FakeAgent())
    _add_pages(db, storage, tid, "paper")
    db.execute("DELETE FROM provider_keys")
    with pytest.raises(RuntimeError, match="API key"):
        run_paper_extract_job(db, storage, store, tid, agent_factory=lambda **kw: FakeAgent())
    with pytest.raises(ValueError, match="not found"):
        run_paper_extract_job(db, storage, store, 9999, agent_factory=lambda **kw: FakeAgent())


def test_paper_extract_job_agent_errors_propagate_and_leave_questions_untouched(env):
    db, store, storage, tid = env
    _add_pages(db, storage, tid, "paper")
    db.execute("UPDATE assignment_templates SET questions_json = '[]' WHERE id = :t", {"t": tid})
    with pytest.raises(ValueError, match="model said no"):
        run_paper_extract_job(db, storage, store, tid, agent_factory=lambda **kw: FakeAgent(error=ValueError("model said no")))
    assert db.query("SELECT questions_json FROM assignment_templates WHERE id = :t", {"t": tid})[0]["questions_json"] == "[]"


def test_scheme_extract_job_writes_mark_scheme_aligned_to_questions(env):
    db, store, storage, tid = env
    db.execute("UPDATE assignment_templates SET questions_json = :q WHERE id = :t",
               {"q": json.dumps([q.model_dump() for q in QUESTIONS]), "t": tid})
    _add_pages(db, storage, tid, "paper", n=1)
    _add_pages(db, storage, tid, "scheme", n=3)
    items = [MarkSchemeEntry(q_id="1a", answer="x = 2", marks=[MarkPoint(label="M1", marks=1), MarkPoint(label="A1", marks=1)]),
             MarkSchemeEntry(q_id="1b", answer="4", marks=[MarkPoint(label="B1", marks=1)])]
    agent = FakeAgent(SchemeExtract(items=items))
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return agent

    assert run_scheme_extract_job(db, storage, store, tid, agent_factory=factory) == 2
    assert seen["kind"] == "mark_scheme" and [q.q_id for q in seen["questions"]] == ["1a", "1b"]
    assert len(agent.inputs[0].images) == 3 and [q.q_id for q in agent.inputs[0].questions] == ["1a", "1b"]
    row = db.query("SELECT scheme_json FROM assignment_templates WHERE id = :t", {"t": tid})[0]
    assert json.loads(row["scheme_json"]) == [i.model_dump() for i in items]


def test_scheme_extract_job_rubric_kind(env):
    db, store, storage, tid = env
    db.execute("UPDATE assignment_templates SET scheme_kind = 'rubric' WHERE id = :t", {"t": tid})
    _add_pages(db, storage, tid, "scheme", n=1)
    items = [RubricCriterionBands(criterion="Content", bands=[Band(band="A", marks=6, descriptor="Excellent")])]
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return FakeAgent(RubricExtract(items=items))

    assert run_scheme_extract_job(db, storage, store, tid, agent_factory=factory) == 1
    assert seen["kind"] == "rubric"
    row = db.query("SELECT scheme_json FROM assignment_templates WHERE id = :t", {"t": tid})[0]
    assert json.loads(row["scheme_json"])[0]["bands"][0]["descriptor"] == "Excellent"


def test_scheme_extract_job_requires_scheme_pages_and_a_typed_assignment(env):
    db, store, storage, tid = env
    with pytest.raises(ValueError, match="mark scheme"):
        run_scheme_extract_job(db, storage, store, tid, agent_factory=lambda **kw: FakeAgent())
    db.execute("UPDATE assignment_templates SET scheme_kind = 'criteria' WHERE id = :t", {"t": tid})
    _add_pages(db, storage, tid, "scheme", n=1)
    with pytest.raises(ValueError, match="type"):
        run_scheme_extract_job(db, storage, store, tid, agent_factory=lambda **kw: FakeAgent())


def test_worker_dispatches_extract_jobs_by_payload(env):
    db, store, storage, tid = env
    js = JobStore(db)
    calls = []

    def paper_runner(db_, storage_, store_, template_id, bucket=None, bucket_pool=None):
        calls.append(("paper", template_id, bucket_pool))
        return 1

    def scheme_runner(db_, storage_, store_, template_id, bucket=None, bucket_pool=None):
        calls.append(("scheme", template_id, bucket_pool))
        return 1

    w = Worker(db, storage, store, runner=lambda *a, **k: None, paper_runner=paper_runner, scheme_runner=scheme_runner)
    assert js.enqueue_unique("paper_extract", {"template_id": tid}, dedupe_key=f"paper:{tid}") is not None
    assert js.enqueue_unique("paper_extract", {"template_id": tid}, dedupe_key=f"paper:{tid}") is None
    js.enqueue_unique("scheme_extract", {"template_id": tid}, dedupe_key=f"scheme:{tid}")
    assert w.run_once() and w.run_once() and not w.run_once()
    assert calls == [("paper", tid, w.pool), ("scheme", tid, w.pool)]
    assert {r["status"] for r in db.query("SELECT status FROM jobs")} == {"done"}


def test_worker_records_extract_errors_on_the_job(env):
    db, store, storage, tid = env
    js = JobStore(db)
    js.enqueue_unique("paper_extract", {"template_id": tid}, dedupe_key=f"paper:{tid}")

    def boom(*a, **k):
        raise ValueError("Upload the question paper first")

    Worker(db, storage, store, runner=lambda *a, **k: None, paper_runner=boom).run_once()
    row = db.query("SELECT status, error FROM jobs")[0]
    assert row["status"] == "failed" and "question paper" in row["error"]

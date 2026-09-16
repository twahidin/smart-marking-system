import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore
from sms.schemas.reflection import ExemplarCase, ReflectionUpdate, RubricNote
from sms.worker.reflect_job import run_reflect_job


@pytest.fixture
def env(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0))
    for run_id in ("r1", "r2"):
        db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, final_status) "
                   "VALUES (?, 'complete', 'math', '{}', '{\"questions\": [{\"q_id\": \"q1\", \"transcribed_answer\": \"x=3\"}]}', 'complete')",
                   (run_id,))
        db.execute("INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason) VALUES (?, 'q1', 2, 3, 'units')",
                   (run_id,))
    return db, store


UPDATE = ReflectionUpdate(
    rubric_notes=[RubricNote(subject="math", note="Always require units.", source_run_ids=["r1", "r2"])],
    exemplar_cases=[ExemplarCase(subject="math", topic="algebra", q_id="q1", answer_text="x = 3 cm", awarded=3, max_score=3,
                                 why_it_matters="units stated")],
)


class FakeAgent:
    def __init__(self, result=UPDATE, error=None):
        self.result = result
        self.error = error
        self.inputs = []

    def run(self, user_input):
        self.inputs.append(user_input)
        if self.error:
            raise self.error
        return self.result


def test_run_reflect_job_records_run_and_writes_draft_notes(env):
    db, store = env
    agent = FakeAgent()
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return agent

    n = run_reflect_job(db, store, "math", 7, agent_factory=factory)
    assert n == 1
    assert seen["settings"].model == "gpt-5-mini" and seen["db"] is db and seen["bucket"] is not None
    assert len(agent.inputs[0].corrections) == 2
    assert db.query("SELECT note, status FROM rubric_notes")[0] == {"note": "Always require units.", "status": "draft"}
    assert db.query("SELECT COUNT(*) AS c FROM exemplar_cases WHERE status = 'draft'")[0]["c"] == 1
    run = db.query("SELECT * FROM reflection_runs")[0]
    assert run["subject"] == "math" and run["lookback_days"] == 7 and run["proposed_notes"] == 1
    assert run["started_at"] and run["finished_at"] and run["error"] is None


def test_run_reflect_job_records_error_and_reraises(env):
    db, store = env
    agent = FakeAgent(error=ValueError("model said no"))
    with pytest.raises(ValueError, match="model said no"):
        run_reflect_job(db, store, "math", 7, agent_factory=lambda **kw: agent)
    run = db.query("SELECT * FROM reflection_runs")[0]
    assert run["error"] == "model said no" and run["finished_at"] and run["proposed_notes"] == 0
    assert db.query("SELECT COUNT(*) AS c FROM rubric_notes")[0]["c"] == 0


def test_run_reflect_job_without_corrections_records_zero(env):
    db, store = env
    agent = FakeAgent()
    assert run_reflect_job(db, store, "science", 7, agent_factory=lambda **kw: agent) == 0
    assert agent.inputs == []
    assert db.query("SELECT proposed_notes, error FROM reflection_runs")[0] == {"proposed_notes": 0, "error": None}


def test_run_reflect_job_without_key_records_error_on_the_run(env):
    db, store = env
    db.execute("DELETE FROM provider_keys")
    with pytest.raises(RuntimeError, match="API key"):
        run_reflect_job(db, store, "math", 7, agent_factory=lambda **kw: FakeAgent())
    run = db.query("SELECT error, finished_at FROM reflection_runs")[0]
    assert "API key" in run["error"] and run["finished_at"]


def test_run_reflect_job_records_agent_factory_errors(env):
    db, store = env

    def factory(**kw):
        raise RuntimeError("provider down")

    with pytest.raises(RuntimeError, match="provider down"):
        run_reflect_job(db, store, "math", 7, agent_factory=factory)
    assert db.query("SELECT error FROM reflection_runs")[0]["error"] == "provider down"


def test_run_reflect_job_reuses_a_given_run_row_across_attempts(env):
    db, store = env
    with pytest.raises(ValueError):
        run_reflect_job(db, store, "math", 7, agent_factory=lambda **kw: FakeAgent(error=ValueError("first try")))
    run_id = db.query("SELECT id FROM reflection_runs")[0]["id"]
    assert run_reflect_job(db, store, "math", 7, run_id=run_id, agent_factory=lambda **kw: FakeAgent()) == 1
    rows = db.query("SELECT id, error, proposed_notes, finished_at FROM reflection_runs")
    assert len(rows) == 1 and rows[0]["error"] is None and rows[0]["proposed_notes"] == 1 and rows[0]["finished_at"]


def test_run_reflect_job_rejects_unknown_subject(env):
    db, store = env
    with pytest.raises(KeyError):
        run_reflect_job(db, store, "art", 7, agent_factory=lambda **kw: FakeAgent())

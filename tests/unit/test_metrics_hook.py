import instructor
import openai
import pytest

from sms.memory.db import Database
from sms.memory.metrics import MetricsSummary
from sms.memory.metrics_hook import MetricsHook, wire_metrics


class FakeUsage:
    prompt_tokens = 120
    completion_tokens = 80


class FakeResponse:
    usage = FakeUsage()


def test_metrics_hook_records_latency_and_tokens(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    hook = MetricsHook(db=db, agent_role="marker", stage="gpt-5-mini", run_id="r1")

    hook.on_kwargs({"model": "gpt-5-mini"})
    hook.on_response(FakeResponse())

    rows = db.query("SELECT * FROM agent_metrics")
    assert len(rows) == 1
    assert rows[0]["agent_role"] == "marker"
    assert rows[0]["run_id"] == "r1"
    assert rows[0]["latency_ms"] >= 0
    assert rows[0]["tokens_in"] == 120
    assert rows[0]["tokens_out"] == 80
    s = MetricsSummary(db).summarize(agent_role="marker")
    assert s["count"] == 1
    assert s["total_tokens_in"] == 120


def test_metrics_hook_ignores_response_without_start(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    hook = MetricsHook(db=db, agent_role="marker", stage="s")
    hook.on_response(FakeResponse())
    assert db.query("SELECT * FROM agent_metrics") == []


def test_metrics_hook_handles_missing_usage(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    hook = MetricsHook(db=db, agent_role="extractor", stage="s")
    hook.on_kwargs({})
    hook.on_response(object())
    rows = db.query("SELECT * FROM agent_metrics")
    assert rows and rows[0]["tokens_in"] == 0 and rows[0]["tokens_out"] == 0


def test_wire_metrics_registers_on_client(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    client = instructor.from_openai(openai.OpenAI(api_key="k"))
    registered = []
    client.on = lambda name, handler: registered.append(name)
    agent = type("A", (), {"client": client, "model": "gpt-5-mini"})()
    wire_metrics(db=db, agents={"marker": agent}, run_id="r9")
    assert sorted(registered) == ["completion:kwargs", "completion:response"]

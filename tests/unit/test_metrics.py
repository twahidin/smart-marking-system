from sms.memory.db import Database
from sms.memory.metrics import MetricsSummary, record_run_metric


def test_record_and_summarize(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    record_run_metric(db, run_id="r1", stage="marking", agent_role="marker",
                      latency_ms=1500, tokens_in=800, tokens_out=400)
    record_run_metric(db, run_id="r2", stage="marking", agent_role="marker",
                      latency_ms=2500, tokens_in=900, tokens_out=500)
    s = MetricsSummary(db).summarize(agent_role="marker")
    assert s["count"] == 2
    assert s["mean_latency_ms"] == 2000.0
    assert s["total_tokens_in"] == 1700
    assert s["total_tokens_out"] == 900


def test_summarize_empty(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    s = MetricsSummary(db).summarize(agent_role="marker")
    assert s["count"] == 0
    assert s["mean_latency_ms"] == 0.0

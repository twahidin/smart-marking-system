from typing import Optional

from sms.memory.db import Database


def record_run_metric(
    db: Database,
    run_id: Optional[str],
    stage: str,
    agent_role: str,
    latency_ms: int,
    tokens_in: int,
    tokens_out: int,
) -> None:
    db.execute(
        "INSERT INTO agent_metrics (run_id, stage, agent_role, latency_ms, tokens_in, tokens_out) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, stage, agent_role, latency_ms, tokens_in, tokens_out),
    )


class MetricsSummary:
    def __init__(self, db: Database):
        self.db = db

    def summarize(self, agent_role: str) -> dict:
        rows = self.db.query(
            "SELECT COUNT(*) AS count, AVG(latency_ms) AS mean_latency_ms, "
            "SUM(tokens_in) AS total_tokens_in, SUM(tokens_out) AS total_tokens_out "
            "FROM agent_metrics WHERE agent_role = ?",
            (agent_role,),
        )
        r = rows[0] if rows else {}
        # Explicit casts: Postgres returns Decimal for AVG and bigint for SUM/COUNT; callers expect plain ints/floats.
        return {
            "count": int(r.get("count") or 0),
            "mean_latency_ms": float(r.get("mean_latency_ms") or 0.0),
            "total_tokens_in": int(r.get("total_tokens_in") or 0),
            "total_tokens_out": int(r.get("total_tokens_out") or 0),
        }

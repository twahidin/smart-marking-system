from typing import Any, Optional

from sms.memory.db import Database
from sms.memory.metrics import record_run_metric


class MetricsHook:
    """Wires instructor completion hooks to agent_metrics per agent role.

    Register the returned handlers with the instructor client via
    client.on("completion:kwargs", hook.on_kwargs) and
    client.on("completion:response", hook.on_response).
    """

    def __init__(self, db: Database, agent_role: str, stage: str, run_id: Optional[str] = None):
        self.db = db
        self.agent_role = agent_role
        self.stage = stage
        self.run_id = run_id
        self._start_ns: Optional[int] = None

    def on_kwargs(self, *args: Any, **kwargs: Any) -> None:
        import time

        self._start_ns = time.monotonic_ns()

    def on_response(self, response: Any, *args: Any, **kwargs: Any) -> None:
        import time

        if self._start_ns is None:
            return
        latency_ms = int((time.monotonic_ns() - self._start_ns) / 1_000_000)
        tokens_in = 0
        tokens_out = 0
        usage = getattr(response, "usage", None)
        if usage is not None:
            tokens_in = getattr(usage, "prompt_tokens", 0) or 0
            tokens_out = getattr(usage, "completion_tokens", 0) or 0
        record_run_metric(
            db=self.db,
            run_id=self.run_id,
            stage=self.stage,
            agent_role=self.agent_role,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        self._start_ns = None

    def register(self, client: Any) -> None:
        client.on("completion:kwargs", self.on_kwargs)
        client.on("completion:response", self.on_response)


def wire_metrics(db: Database, agents: dict, run_id: Optional[str] = None) -> None:
    """Register metrics hooks for a dict of role -> (client-bearing agent).

    Each agent must expose .client (the instructor client) and .model.
    """
    for role, agent in agents.items():
        stage = getattr(agent, "model", "unknown")
        hook = MetricsHook(db=db, agent_role=role, stage=stage, run_id=run_id)
        hook.register(agent.client)

"""Stage events: what the crew (Reader, Marker, Checker) is doing and thinking while a script is marked.
The pipeline calls an optional listener; the worker records the events (sms.worker.events)."""
from dataclasses import dataclass
from typing import Callable, Optional

STAGES = ("read", "mark", "check", "feedback", "done")
KINDS = ("started", "finished", "note")
READ_DOUBT = "Hard to read — the teacher may need to look at the page"


@dataclass(frozen=True)
class StageEvent:
    stage: str
    kind: str
    q_id: Optional[str] = None
    note: Optional[str] = None


OnEvent = Callable[[StageEvent], None]

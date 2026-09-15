import threading
import time
from collections import deque
from typing import Any, Callable, Deque


class TokenBucket:
    """Sliding-window limiter: at most `rpm` acquisitions in any 60 s window. rpm<=0 disables."""

    def __init__(self, rpm: int, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.rpm = int(rpm)
        self._clock = clock
        self._sleep = sleep
        self._stamps: Deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self.rpm <= 0:
            return
        while True:
            with self._lock:
                now = self._clock()
                while self._stamps and now - self._stamps[0] >= 60.0:
                    self._stamps.popleft()
                if len(self._stamps) < self.rpm:
                    self._stamps.append(now)
                    return
                wait = 60.0 - (now - self._stamps[0])
            self._sleep(max(wait, 0.01))


class RateLimitedAgent:
    """Wraps an AtomicAgent so every .run() first takes a token. Keeps .client/.model for wire_metrics."""

    def __init__(self, agent: Any, bucket: TokenBucket):
        self._agent = agent
        self._bucket = bucket

    def run(self, user_input: Any) -> Any:
        self._bucket.acquire()
        return self._agent.run(user_input)

    @property
    def client(self) -> Any:
        return self._agent.client

    @property
    def model(self) -> Any:
        return self._agent.model

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)

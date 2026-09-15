import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from sms.web.errors import ApiError

COOKIE = "sms_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30


class SessionSigner:
    def __init__(self, secret: str):
        self._s = URLSafeTimedSerializer(secret, salt="sms-session")

    def issue(self) -> str:
        return self._s.dumps({"role": "teacher"})

    def verify(self, token: str) -> bool:
        try:
            data = self._s.loads(token, max_age=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False
        return data.get("role") == "teacher"


class LoginLimiter:
    """5 failed attempts per IP per 60 s."""

    def __init__(self, limit: int = 5, window_s: float = 60.0):
        self.limit = limit
        self.window_s = window_s
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def blocked(self, ip: str) -> bool:
        q = self._hits[ip]
        now = time.monotonic()
        while q and now - q[0] > self.window_s:
            q.popleft()
        return len(q) >= self.limit

    def record_failure(self, ip: str) -> None:
        self._hits[ip].append(time.monotonic())


def get_db(request: Request):
    return request.app.state.db


def get_settings_store(request: Request):
    return request.app.state.settings_store


def get_storage(request: Request):
    return request.app.state.storage


def get_jobs(request: Request):
    return request.app.state.jobs


def require_teacher(request: Request) -> None:
    token = request.cookies.get(COOKIE)
    if not token or not request.app.state.signer.verify(token):
        raise ApiError(401, "unauthenticated", "Sign in to continue")

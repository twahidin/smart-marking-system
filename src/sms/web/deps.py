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
    """5 failed attempts per IP per 60 s, plus a global cap of 30 failures per 60 s across all IPs.

    The global cap means spoofing X-Forwarded-For to rotate through fresh addresses still runs
    into a wall after `global_limit` failures.
    """

    def __init__(self, limit: int = 5, window_s: float = 60.0, global_limit: int = 30):
        self.limit = limit
        self.window_s = window_s
        self.global_limit = global_limit
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._all: Deque[float] = deque()

    @staticmethod
    def _expire(q: Deque[float], now: float, window_s: float) -> None:
        while q and now - q[0] > window_s:
            q.popleft()

    def blocked(self, ip: str) -> bool:
        now = time.monotonic()
        self._expire(self._all, now, self.window_s)
        if len(self._all) >= self.global_limit:
            return True
        q = self._hits[ip]
        self._expire(q, now, self.window_s)
        result = len(q) >= self.limit
        if not q:
            self._hits.pop(ip, None)
        return result

    def record_failure(self, ip: str) -> None:
        now = time.monotonic()
        self._hits[ip].append(now)
        self._all.append(now)


def client_ip(request: Request) -> str:
    """Best-effort client address for rate limiting.

    With X-Forwarded-For, use the RIGHTMOST entry: that is the address the trusted edge proxy
    (Railway) saw. Earlier entries are appended by upstream hops and can be attacker-supplied.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
    if request.client:
        return request.client.host
    return "unknown"


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

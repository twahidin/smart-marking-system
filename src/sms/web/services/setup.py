"""First-run setup: the teacher password stored on the website.

Precedence at sign-in: the TEACHER_PASSWORD variable, when set, wins (a dashboard override and the
forgot-password recovery); otherwise the scrypt hash on the settings row. With neither, the site
needs setup and the wizard is the only door."""
import base64
import hashlib
import hmac
import os
import secrets
from typing import Optional

from sms.memory.db import Database

MIN_PASSWORD = 8
_N, _R, _P, _DKLEN = 2 ** 14, 8, 1, 32


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    try:
        algo, salt, key = (stored or "").split("$")
        if algo != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=_N, r=_R, p=_P, dklen=_DKLEN)
        return hmac.compare_digest(candidate, _unb64(key))
    except (ValueError, TypeError):
        return False


def password_hash(db: Database) -> Optional[str]:
    rows = db.query("SELECT teacher_password_hash FROM settings WHERE id = 1")
    return rows[0]["teacher_password_hash"] if rows else None


def set_password(db: Database, password: str) -> None:
    db.execute("UPDATE settings SET teacher_password_hash = :h, setup_completed_at = CURRENT_TIMESTAMP WHERE id = 1",
               {"h": hash_password(password)})


def password_source(env_password: Optional[str], db: Database) -> Optional[str]:
    """'railway' when the variable is set, 'website' when a hash is stored, None when neither."""
    if env_password:
        return "railway"
    return "website" if password_hash(db) else None


def needs_setup(env_password: Optional[str], db: Database) -> bool:
    return password_source(env_password, db) is None


def check_password(env_password: Optional[str], db: Database, candidate: str) -> bool:
    if env_password:
        return secrets.compare_digest(candidate.encode(), env_password.encode())
    return verify_password(candidate, password_hash(db))


def weak(password: str) -> bool:
    return len(password or "") < MIN_PASSWORD

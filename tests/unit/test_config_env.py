import pytest

from sms.web.config import AppConfig


def test_teacher_password_is_optional(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "s" * 32); monkeypatch.delenv("TEACHER_PASSWORD", raising=False)
    assert AppConfig.from_env().teacher_password is None


def test_blank_teacher_password_counts_as_unset(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "s" * 32); monkeypatch.setenv("TEACHER_PASSWORD", "   ")
    assert AppConfig.from_env().teacher_password is None


def test_secret_key_still_required(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        AppConfig.from_env()

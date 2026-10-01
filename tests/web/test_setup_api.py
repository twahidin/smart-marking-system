"""First-run setup wizard: create the teacher password on the website, optionally the model and key."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sms.web.app import create_app
from sms.web.config import AppConfig
from sms.web.services.setup import hash_password, verify_password


def _app(tmp_path, password):
    return create_app(AppConfig(database_url=f"sqlite:///{tmp_path / 'app.db'}", secret_key="test-secret",
                                teacher_password=password, storage_dir=Path(tmp_path / "data"), embedded_worker=False, env={}))


@pytest.fixture
def fresh(tmp_path):
    with TestClient(_app(tmp_path, None)) as c:
        yield c


@pytest.fixture
def env_pw(tmp_path):
    with TestClient(_app(tmp_path, "letmein")) as c:
        yield c


def test_hash_roundtrip_and_salt():
    h1, h2 = hash_password("correct horse"), hash_password("correct horse")
    assert h1 != h2 and verify_password("correct horse", h1) and verify_password("correct horse", h2)
    assert not verify_password("wrong", h1) and not verify_password("correct horse", "garbage")


def test_fresh_deployment_needs_setup_and_wizard_signs_in(fresh):
    assert fresh.get("/api/setup/status").json() == {"needs_setup": True}
    assert fresh.get("/api/auth/me").status_code == 401
    r = fresh.post("/api/setup", json={"password": "teachers-2026"})
    assert r.status_code == 204 and "sms_session" in r.cookies
    assert fresh.get("/api/auth/me").json()["authenticated"] is True
    assert fresh.get("/api/setup/status").json() == {"needs_setup": False}


def test_setup_is_one_shot(fresh):
    assert fresh.post("/api/setup", json={"password": "teachers-2026"}).status_code == 204
    r = fresh.post("/api/setup", json={"password": "someone-else"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_set_up"


def test_setup_password_rules(fresh):
    r = fresh.post("/api/setup", json={"password": "short"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "weak_password"
    assert fresh.get("/api/setup/status").json()["needs_setup"] is True


def test_login_uses_the_website_password(fresh):
    fresh.post("/api/setup", json={"password": "teachers-2026"})
    fresh.post("/api/auth/logout")
    assert fresh.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    assert fresh.post("/api/auth/login", json={"password": "teachers-2026"}).status_code == 204


def test_login_before_setup_is_refused_with_a_pointer(fresh):
    r = fresh.post("/api/auth/login", json={"password": "anything"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "needs_setup"


def test_setup_can_connect_a_model(fresh):
    r = fresh.post("/api/setup", json={"password": "teachers-2026", "provider": "google", "api_key": "AIza-test", "model": "gemini-3.8-flash"})
    assert r.status_code == 204
    s = fresh.get("/api/settings").json()
    assert s["provider"] == "google" and s["model"] == "gemini-3.8-flash" and s["keys"].get("google")


def test_setup_rejects_unknown_provider_without_touching_password(fresh):
    r = fresh.post("/api/setup", json={"password": "teachers-2026", "provider": "nope", "api_key": "x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_provider"
    assert fresh.get("/api/setup/status").json()["needs_setup"] is True


def test_env_password_wins_and_hides_the_wizard(env_pw):
    assert env_pw.get("/api/setup/status").json() == {"needs_setup": False}
    assert env_pw.post("/api/setup", json={"password": "teachers-2026"}).status_code == 409
    assert env_pw.post("/api/auth/login", json={"password": "letmein"}).status_code == 204


def test_change_password_on_the_website(fresh):
    fresh.post("/api/setup", json={"password": "teachers-2026"})
    r = fresh.put("/api/auth/password", json={"current": "wrong", "new": "brand-new-pw"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "bad_password"
    assert fresh.put("/api/auth/password", json={"current": "teachers-2026", "new": "brand-new-pw"}).status_code == 204
    fresh.post("/api/auth/logout")
    assert fresh.post("/api/auth/login", json={"password": "teachers-2026"}).status_code == 401
    assert fresh.post("/api/auth/login", json={"password": "brand-new-pw"}).status_code == 204


def test_change_password_refused_when_set_in_railway(env_pw):
    env_pw.post("/api/auth/login", json={"password": "letmein"})
    r = env_pw.put("/api/auth/password", json={"current": "letmein", "new": "brand-new-pw"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "password_from_env"


def test_change_password_requires_sign_in(fresh):
    fresh.post("/api/setup", json={"password": "teachers-2026"}); fresh.post("/api/auth/logout")
    assert fresh.put("/api/auth/password", json={"current": "teachers-2026", "new": "brand-new-pw"}).status_code == 401


def test_me_reports_where_the_password_lives(fresh, env_pw):
    fresh.post("/api/setup", json={"password": "teachers-2026"})
    assert fresh.get("/api/auth/me").json() == {"authenticated": True, "password_source": "website"}
    env_pw.post("/api/auth/login", json={"password": "letmein"})
    assert env_pw.get("/api/auth/me").json() == {"authenticated": True, "password_source": "railway"}

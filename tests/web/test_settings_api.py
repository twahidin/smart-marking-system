import pytest

from sms.providers.probe import Check, ProbeResult


def test_requires_auth(client):
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/providers").status_code == 401


def test_providers_lists_six(auth):
    body = auth.get("/api/providers").json()
    assert {p["id"] for p in body} == {"tokenrouter", "openrouter", "openai", "anthropic", "moonshot", "qwen"}


def test_get_defaults_and_never_leaks_key(auth):
    s = auth.get("/api/settings").json()
    assert s["provider"] == "tokenrouter" and s["has_key"] is False and "api_key" not in s


def test_put_saves_and_blank_key_keeps(auth):
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-abcd1234",
                                        "rpm_limit": 60, "confidence_threshold": 0.5})
    assert r.status_code == 200 and r.json()["key_hint"] == "1234" and r.json()["has_key"]
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5.5", "api_key": "", "rpm_limit": 60,
                                        "confidence_threshold": 0.5})
    assert r.json()["model"] == "gpt-5.5" and r.json()["key_hint"] == "1234"


def test_put_unknown_provider_400(auth):
    r = auth.put("/api/settings", json={"provider": "nope", "model": "x", "rpm_limit": 1, "confidence_threshold": 0})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_provider"


def test_whitespace_only_model_is_400_validation(auth, monkeypatch):
    r = auth.put("/api/settings", json={"provider": "openai", "model": "   ", "rpm_limit": 1, "confidence_threshold": 0})
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation"
    assert "model" in r.json()["error"]["message"]
    assert auth.get("/api/settings").json()["model"] != ""

    monkeypatch.setattr("sms.web.routers.settings.probe", lambda *a, **k: pytest.fail("probe must not run"))
    r = auth.post("/api/settings/test", json={"provider": "openai", "model": " \t ", "api_key": "sk-x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation"


def test_test_connection_uses_submitted_then_stored_key(auth, monkeypatch):
    seen = []

    def fake_probe(provider, model, api_key, extractor_model=None, base_url=None, **_):
        seen.append(api_key)
        return ProbeResult(text=Check(True, 10), vision=Check(True, 20))

    monkeypatch.setattr("sms.web.routers.settings.probe", fake_probe)
    r = auth.post("/api/settings/test", json={"provider": "openai", "model": "gpt-5-mini"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_key"
    r = auth.post("/api/settings/test", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-new"})
    assert r.status_code == 200 and r.json()["vision"]["ok"] and seen == ["sk-new"]
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-stored",
                                    "rpm_limit": 60, "confidence_threshold": 0})
    auth.post("/api/settings/test", json={"provider": "openai", "model": "gpt-5-mini"})
    assert seen[-1] == "sk-stored"

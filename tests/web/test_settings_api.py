import pytest

from sms.providers.probe import Check, ProbeResult
from sms.providers.settings import Settings
from sms.web.services.telegram import TelegramClient, TelegramError

from tests.web.test_class_assignments_api import _template


def test_requires_auth(client):
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/providers").status_code == 401


def test_providers_lists_seven(auth):
    body = auth.get("/api/providers").json()
    assert {p["id"] for p in body} == {"tokenrouter", "openrouter", "openai", "anthropic", "moonshot", "qwen", "google"}


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


def test_put_saves_telegram_fields_and_never_returns_the_token(auth):
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 60,
                                        "confidence_threshold": 0.5, "telegram_bot_token": "123456:ABCDwxyz",
                                        "telegram_instant": False, "telegram_daily_time": "06:45",
                                        "timezone": "Asia/Singapore", "app_url": "https://x.example/"})
    assert r.status_code == 200
    body = r.json()
    assert "telegram_bot_token" not in body and body["telegram_bot_hint"] == "wxyz"
    assert body["telegram_daily_time"] == "06:45" and body["timezone"] == "Asia/Singapore"
    assert body["telegram_instant"] is False and body["app_url"] == "https://x.example/"
    # a blank token keeps the stored one
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 60,
                                        "confidence_threshold": 0.5, "telegram_bot_token": "",
                                        "telegram_daily_time": "06:45", "timezone": "Asia/Singapore"})
    assert r.json()["telegram_bot_hint"] == "wxyz"
    s = auth.get("/api/settings").json()
    assert "telegram_bot_token" not in s and s["telegram_bot_hint"] == "wxyz"


def test_put_rejects_bad_timezone_and_bad_time(auth):
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 60,
                                        "confidence_threshold": 0.5, "timezone": "Mars/Olympus"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_timezone"
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 60,
                                        "confidence_threshold": 0.5, "telegram_daily_time": "25:00"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_time"


def test_telegram_test_message_and_unlink(auth, monkeypatch):
    store = auth.app.state.settings_store
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-abcd1234", rpm_limit=60,
                        telegram_bot_token="123456:ABCDwxyz"))
    assert auth.post("/api/settings/telegram/test").json()["error"]["code"] == "not_linked"
    assert auth.post("/api/settings/telegram/test").status_code == 409

    sent = []
    closed = []

    class FakeClient:
        def __init__(self, token, **kw):
            self.token = token
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.closed = True
            closed.append(True)

        def send_message(self, chat_id, html):
            sent.append((self.token, chat_id, html))

    store.set_telegram(chat_id="1")
    monkeypatch.setattr("sms.web.routers.settings.TelegramClient", FakeClient)
    assert auth.post("/api/settings/telegram/test").status_code == 204
    assert sent == [("123456:ABCDwxyz", "1", "Smart Marking is connected ✓")]
    assert closed == [True]  # the http client is not leaked per request

    assert auth.delete("/api/settings/telegram").status_code == 204
    s = auth.get("/api/settings").json()
    assert s["telegram_linked"] is False and s["telegram_bot_hint"] == ""


def test_telegram_test_maps_send_failure_to_502(auth, monkeypatch):
    store = auth.app.state.settings_store
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-abcd1234", rpm_limit=60,
                        telegram_bot_token="123456:ABCDwxyz"))
    store.set_telegram(chat_id="1")

    closed = []

    class FakeClient:
        def __init__(self, token, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            closed.append(True)

        def send_message(self, chat_id, html):
            raise TelegramError("chat not found")

    monkeypatch.setattr("sms.web.routers.settings.TelegramClient", FakeClient)
    r = auth.post("/api/settings/telegram/test")
    assert r.status_code == 502 and r.json()["error"]["code"] == "telegram_error"
    assert r.json()["error"]["message"] == "chat not found"
    assert closed == [True]  # closed even when the send fails


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


def test_list_models_uses_submitted_then_stored_key(auth, monkeypatch):
    seen = []

    def fake_list(provider, api_key, base_url=None):
        seen.append((provider, api_key, base_url))
        return ["z-ai/glm-5.3-flash", "z-ai/glm-5.3-free"]

    monkeypatch.setattr("sms.web.routers.settings.list_models", fake_list)
    r = auth.post("/api/settings/models", json={"provider": "tokenrouter"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_key"
    r = auth.post("/api/settings/models", json={"provider": "tokenrouter", "api_key": "tr-new"})
    assert r.status_code == 200 and r.json() == {"models": ["z-ai/glm-5.3-flash", "z-ai/glm-5.3-free"]}
    auth.put("/api/settings", json={"provider": "tokenrouter", "model": "z-ai/glm-5.3-flash", "api_key": "tr-stored",
                                    "rpm_limit": 60, "confidence_threshold": 0})
    auth.post("/api/settings/models", json={"provider": "tokenrouter"})
    assert seen == [("tokenrouter", "tr-new", None), ("tokenrouter", "tr-stored", None)]


def test_list_models_bad_provider_and_provider_error(auth, monkeypatch):
    r = auth.post("/api/settings/models", json={"provider": "nope", "api_key": "k"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_provider"

    def boom(provider, api_key, base_url=None):
        raise RuntimeError("Error code: 401 - {'error': {'message': 'Invalid API key'}}")

    monkeypatch.setattr("sms.web.routers.settings.list_models", boom)
    r = auth.post("/api/settings/models", json={"provider": "openai", "api_key": "k"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "provider_error"
    assert r.json()["error"]["message"] == "HTTP 401: Invalid API key"


def test_delete_pages_after_marking_defaults_on_and_round_trips(auth):
    assert auth.get("/api/settings").json()["delete_pages_after_marking"] is True
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 60,
                                        "confidence_threshold": 0, "delete_pages_after_marking": False})
    assert r.status_code == 200 and r.json()["delete_pages_after_marking"] is False
    assert auth.get("/api/settings").json()["delete_pages_after_marking"] is False
    # omitted -> back to the default
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 60, "confidence_threshold": 0})
    assert r.json()["delete_pages_after_marking"] is True


def test_keys_are_per_provider_and_can_be_removed(auth):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-abcd1234", "rpm_limit": 60, "confidence_threshold": 0})
    r = auth.put("/api/settings", json={"provider": "tokenrouter", "model": "z-ai/glm-5.3-flash", "api_key": "", "rpm_limit": 60, "confidence_threshold": 0})
    assert r.json()["has_key"] is False and r.json()["keys"] == {"openai": "1234"}
    r = auth.put("/api/settings", json={"provider": "tokenrouter", "model": "z-ai/glm-5.3-flash", "api_key": "tr-9999", "rpm_limit": 60, "confidence_threshold": 0})
    assert r.json()["key_hint"] == "9999" and r.json()["keys"] == {"openai": "1234", "tokenrouter": "9999"}
    assert auth.delete("/api/settings/keys/openai").status_code == 204
    assert auth.get("/api/settings").json()["keys"] == {"tokenrouter": "9999"}
    assert auth.delete("/api/settings/keys/nope").status_code == 400


def test_removing_a_key_assignments_are_pinned_to_needs_force(auth):
    """An assignment pinned to a provider fails to mark the moment its key goes, so removing the
    key is refused with the count — the same 409 `in_use` / `?force=1` pair as deleting a template."""
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-abcd1234",
                                    "rpm_limit": 60, "confidence_threshold": 0})
    for title in ("Pinned one", "Pinned two"):
        t = _template(auth, title=title, provider="openai", model="gpt-5.5")
        assert t["provider"] == "openai"

    r = auth.delete("/api/settings/keys/openai")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "in_use" and r.json()["count"] == 2
    assert "2 assignments use this provider" in r.json()["error"]["message"]
    assert auth.get("/api/settings").json()["keys"] == {"openai": "1234"}   # nothing removed

    assert auth.delete("/api/settings/keys/openai?force=1").status_code == 204
    assert auth.get("/api/settings").json()["keys"] == {}
    # a provider nothing is pinned to needs no force
    auth.put("/api/settings", json={"provider": "tokenrouter", "model": "z-ai/glm-5.3-flash", "api_key": "tr-9999",
                                    "rpm_limit": 60, "confidence_threshold": 0})
    assert auth.delete("/api/settings/keys/tokenrouter").status_code == 204


def test_subject_models_crud(auth_with_google_key):
    c = auth_with_google_key
    assert c.get("/api/settings/subject-models").json() == {"math": None, "language": None, "science": None, "mt": None, "computing": None}
    r = c.put("/api/settings/subject-models/mt", json={"provider": "google", "model": "gemini-3.8-pro"})
    assert r.status_code == 200 and r.json()["model"] == "gemini-3.8-pro"
    assert c.put("/api/settings/subject-models/mt", json={"provider": "anthropic", "model": "x"}).json()["error"]["code"] == "no_key_for_provider"
    assert c.put("/api/settings/subject-models/art", json={"provider": "google", "model": "x"}).status_code == 400
    assert c.delete("/api/settings/subject-models/mt").status_code == 204
    assert c.get("/api/settings/subject-models").json()["mt"] is None


def test_removing_a_key_a_subject_default_uses_needs_force(auth_with_google_key):
    """Extends the same in_use guard as pinned assignments: a subject default pointed at a
    provider must not go stale the moment that provider's key is removed."""
    c = auth_with_google_key
    c.put("/api/settings/subject-models/mt", json={"provider": "google", "model": "gemini-3.8-pro"})
    r = c.delete("/api/settings/keys/google")
    assert r.status_code == 409 and r.json()["error"]["code"] == "in_use" and r.json()["count"] == 1
    assert "1 subject default uses this provider" in r.json()["error"]["message"]
    assert c.get("/api/settings/subject-models").json()["mt"] is not None   # nothing removed

    assert c.delete("/api/settings/keys/google?force=1").status_code == 204


def test_telegram_test_maps_a_transport_failure_to_502(auth, monkeypatch):
    """api.telegram.org being unreachable is the same answer as a refusal: the message did not go."""
    import httpx

    store = auth.app.state.settings_store
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-abcd1234", rpm_limit=60,
                        telegram_bot_token="123456:ABCDwxyz"))
    store.set_telegram(chat_id="1")

    def boom(_request):
        raise httpx.ConnectError("[Errno 8] nodename nor servname provided")

    monkeypatch.setattr("sms.web.routers.settings.TelegramClient",
                        lambda token, **kw: TelegramClient(token, transport=httpx.MockTransport(boom)))
    r = auth.post("/api/settings/telegram/test")
    assert r.status_code == 502 and r.json()["error"]["code"] == "telegram_error"
    assert "nodename" in r.json()["error"]["message"]


def test_custom_models_for_aggregators_appear_in_providers(auth):
    r = auth.post("/api/settings/models/openrouter", json={"model_id": "google/gemini-3.8-flash", "label": "Gemini 3.8 Flash", "vision": True})
    assert r.status_code == 201 and r.json() == {"id": "google/gemini-3.8-flash", "label": "Gemini 3.8 Flash", "vision": True, "custom": True}
    r = auth.post("/api/settings/models/openrouter", json={"model_id": "meta/llama-5-text"})   # label defaults to the id
    assert r.json()["label"] == "meta/llama-5-text"
    assert auth.post("/api/settings/models/openai", json={"model_id": "x"}).json()["error"]["code"] == "not_supported"
    assert auth.post("/api/settings/models/openrouter", json={"model_id": "  "}).json()["error"]["code"] == "bad_model"
    prov = {p["id"]: p for p in auth.get("/api/providers").json()}
    ids = [m["id"] for m in prov["openrouter"]["models"]]
    assert ids[-2:] == ["google/gemini-3.8-flash", "meta/llama-5-text"] and prov["openrouter"]["custom_models"] is True
    assert prov["openai"]["custom_models"] is False and not any(m.get("custom") for m in prov["openai"]["models"])
    assert auth.delete("/api/settings/models/openrouter/google/gemini-3.8-flash").status_code == 204
    assert "google/gemini-3.8-flash" not in [m["id"] for m in {p["id"]: p for p in auth.get("/api/providers").json()}["openrouter"]["models"]]
    # adding the same id again replaces the label instead of failing
    auth.post("/api/settings/models/openrouter", json={"model_id": "meta/llama-5-text", "label": "Llama 5", "vision": False})
    m = [m for m in {p["id"]: p for p in auth.get("/api/providers").json()}["openrouter"]["models"] if m["id"] == "meta/llama-5-text"][0]
    assert m["label"] == "Llama 5" and m["vision"] is False

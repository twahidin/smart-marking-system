import json

import httpx
import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore
from sms.storage import PageStorage
from sms.web.services.telegram import (
    TelegramClient,
    TelegramError,
    app_base_url,
    escape,
    poll_updates,
)
from sms.worker.worker import Worker


def _store(tmp_path, token="1:abc"):
    db = Database(path=str(tmp_path / "t.db"))
    store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk", rpm_limit=60,
                        telegram_bot_token=token))
    return db, store


def test_poll_links_on_start_and_advances_offset(tmp_path):
    db = Database(path=str(tmp_path / "t.db")); store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk", rpm_limit=60, telegram_bot_token="1:abc"))
    calls = []
    updates = [{"update_id": 10, "message": {"text": "hello", "chat": {"id": 5}}},
               {"update_id": 11, "message": {"text": "/start", "chat": {"id": 777}}}]

    def handler(req):
        calls.append((req.url.path, dict(req.url.params) if req.method == "GET" else json.loads(req.content or b"{}")))
        if req.url.path.endswith("/getUpdates"):
            # Telegram only returns updates from `offset` onwards — acknowledged ones are dropped.
            offset = int(req.url.params.get("offset", 0))
            return httpx.Response(200, json={"ok": True, "result": [u for u in updates if u["update_id"] >= offset]})
        return httpx.Response(200, json={"ok": True, "result": {}})

    factory = lambda token: TelegramClient(token, transport=httpx.MockTransport(handler))
    assert poll_updates(store, client_factory=factory) is True
    s = store.load(); assert s.telegram_chat_id == "777" and s.telegram_update_offset == 12
    sent = [c for c in calls if c[0].endswith("/sendMessage")]
    assert sent and sent[0][1]["chat_id"] == "777" and "Linked" in sent[0][1]["text"]
    # next poll asks from offset 12 and finds nothing
    assert poll_updates(store, client_factory=factory) is False
    assert calls[-1][0].endswith("/getUpdates") and calls[-1][1]["offset"] == "12"


def test_escape_and_send_error():
    assert escape("a < b & c") == "a &lt; b &amp; c"
    def handler(req): return httpx.Response(400, json={"ok": False, "description": "chat not found"})
    with pytest.raises(TelegramError, match="chat not found"):
        TelegramClient("1:abc", transport=httpx.MockTransport(handler)).send_message("1", "x")


def test_start_from_second_chat_replaces_the_link(tmp_path):
    _db, store = _store(tmp_path)
    chats = iter([111, 222])

    def handler(req):
        if req.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [
                {"update_id": int(req.url.params["offset"]), "message": {"text": "/start", "chat": {"id": next(chats)}}}]})
        return httpx.Response(200, json={"ok": True, "result": {}})

    factory = lambda token: TelegramClient(token, transport=httpx.MockTransport(handler))
    assert poll_updates(store, client_factory=factory) is True
    assert store.load().telegram_chat_id == "111"
    assert poll_updates(store, client_factory=factory) is True
    assert store.load().telegram_chat_id == "222"


def test_poll_without_token_does_nothing(tmp_path):
    db = Database(path=str(tmp_path / "t.db"))
    store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk", rpm_limit=60))

    def factory(token):
        pytest.fail("no token stored, so no client should be built")

    assert poll_updates(store, client_factory=factory) is False


def test_get_me_and_send_message_ok():
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path, json.loads(req.content) if req.content else {}))
        if req.url.path.endswith("/getMe"):
            return httpx.Response(200, json={"ok": True, "result": {"username": "marking_bot"}})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 3}})

    client = TelegramClient("1:abc", transport=httpx.MockTransport(handler))
    assert client.get_me()["username"] == "marking_bot"
    assert client.send_message("9", "<b>hi</b>") is None
    method, path, body = seen[-1]
    assert method == "POST" and path.endswith("/sendMessage")
    assert body["parse_mode"] == "HTML" and body["text"] == "<b>hi</b>" and body["disable_web_page_preview"] is True


def test_get_updates_raises_on_not_ok():
    def handler(req): return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    with pytest.raises(TelegramError, match="Unauthorized"):
        TelegramClient("1:abc", transport=httpx.MockTransport(handler)).get_updates(0)


def test_app_base_url_prefers_settings_then_railway(monkeypatch):
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)
    assert app_base_url(Settings(provider="openai", model="m", app_url="https://x.example/")) == "https://x.example"
    assert app_base_url(Settings(provider="openai", model="m")) is None
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "sms.up.railway.app")
    assert app_base_url(Settings(provider="openai", model="m")) == "https://sms.up.railway.app"


def test_worker_polls_telegram_and_survives_errors(tmp_path, monkeypatch):
    db, store = _store(tmp_path)
    worker = Worker(db, PageStorage(tmp_path / "data"), store)
    calls = []

    def boom(settings_store):
        calls.append(settings_store)
        raise RuntimeError("telegram down")

    monkeypatch.setattr("sms.worker.worker.poll_updates", boom)
    worker._maybe_poll_telegram()  # the error is logged, never raised
    assert len(calls) == 1
    worker._maybe_poll_telegram()  # inside the 10 s gate: no second call
    assert len(calls) == 1

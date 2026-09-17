"""Telegram Bot API client and the `/start` linking poll.

The teacher pastes a bot token into Settings; the bot then has to learn *which* chat to
talk to. Telegram will not tell us — the chat has to message the bot first. So the worker
long-polls `getUpdates` every few seconds and treats the first `/start` it sees as the
link. Polling (rather than a webhook) keeps the app deployable behind any URL, including
one that is not publicly reachable yet.
"""

import html
import logging
import os
from typing import Any, Callable, List, Optional

import httpx

log = logging.getLogger("sms.telegram")

LINKED_MESSAGE = "Linked to Smart Marking ✓ — you'll get marking updates here."


class TelegramError(RuntimeError):
    """A Telegram API call that did not come back `ok` — the description is the useful part."""


class TelegramClient:
    def __init__(self, token: str, *, transport: Optional[httpx.BaseTransport] = None, timeout: float = 15.0):
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = httpx.Client(timeout=timeout, transport=transport)

    @staticmethod
    def _result(r: httpx.Response) -> Any:
        body = r.json() if r.content else {}
        if not isinstance(body, dict):
            body = {}
        if r.status_code != 200 or not body.get("ok"):
            raise TelegramError(body.get("description") or f"HTTP {r.status_code}")
        return body.get("result")

    def _call(self, method: str, **params: Any) -> Any:
        r = self._http.post(f"{self._base}/{method}", json=params) if params else self._http.get(f"{self._base}/{method}")
        return self._result(r)

    def get_updates(self, offset: int) -> List[dict]:
        # timeout=0 keeps this a plain short poll: the worker loop already paces the calls.
        r = self._http.get(f"{self._base}/getUpdates",
                           params={"offset": str(offset), "timeout": "0", "allowed_updates": '["message"]'})
        return list(self._result(r) or [])

    def send_message(self, chat_id: str, html_text: str) -> None:
        self._call("sendMessage", chat_id=str(chat_id), text=html_text, parse_mode="HTML",
                   disable_web_page_preview=True)

    def get_me(self) -> dict:
        return self._call("getMe") or {}


def escape(text: Any) -> str:
    """Escape for Telegram's HTML parse mode (quotes are fine inside text nodes)."""
    return html.escape(str(text), quote=False)


def app_base_url(settings) -> Optional[str]:
    """The base URL to put behind links in messages: the configured one, else the Railway
    domain the app is deployed at, else None (the message simply carries no link)."""
    if settings.app_url:
        return settings.app_url.rstrip("/")
    dom = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    return f"https://{dom}" if dom else None


def poll_updates(settings_store, client_factory: Callable[[str], TelegramClient] = TelegramClient) -> bool:
    """Fetch pending updates once: link the chat of any `/start`, then acknowledge everything
    seen by advancing the stored offset. Returns True when a chat was linked this pass.

    A `/start` from a second chat replaces the link — that is how a teacher moves the bot to
    a different chat without clearing anything first.
    """
    s = settings_store.load()
    if not s.telegram_bot_token:
        return False
    client = client_factory(s.telegram_bot_token)
    updates = client.get_updates(s.telegram_update_offset)
    linked = False
    last = None
    for u in updates:
        last = u["update_id"]
        msg = u.get("message") or {}
        if (msg.get("text") or "").strip().startswith("/start"):
            chat_id = str(msg["chat"]["id"])
            settings_store.set_telegram(chat_id=chat_id)
            client.send_message(chat_id, LINKED_MESSAGE)
            log.info("telegram linked to chat %s", chat_id)
            linked = True
    if last is not None:
        settings_store.set_telegram(offset=last + 1)
    return linked

"""Telegram Bot API client and the `/start` linking poll.

The teacher pastes a bot token into Settings; the bot then has to learn *which* chat to
talk to. Telegram will not tell us — the chat has to message the bot first. So the worker
polls `getUpdates` every few seconds and treats the first `/start` it sees as the link.
Polling (rather than a webhook) keeps the app deployable behind any URL, including one that
is not publicly reachable yet.
"""

import html
import logging
import os
from typing import Any, Callable, List, Optional

import httpx

log = logging.getLogger("sms.telegram")

# httpx logs every request line at INFO, and ours carry the bot token in the path
# (`/bot<TOKEN>/getUpdates`). Keep those loggers at WARNING so enabling root INFO logging
# never publishes the token to stdout or a log aggregator.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

LINKED_MESSAGE = "Linked to Smart Marking ✓ — you'll get marking updates here."


class TelegramError(RuntimeError):
    """A Telegram API call that did not come back `ok` — the description is the useful part."""


class TelegramClient:
    """One short-lived connection to the Bot API. Use it as a context manager (or call
    `close()`): the worker builds one every tick, so a leaked pool would accumulate sockets."""

    def __init__(self, token: str, *, transport: Optional[httpx.BaseTransport] = None, timeout: float = 5.0):
        # The worker polls inline, before claiming a job, so a slow Telegram must not stall
        # marking for long: 5 s is generous for an API that answers in milliseconds.
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TelegramClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

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
    fetched by advancing the stored offset. Returns True when a chat was linked this pass.

    A `/start` from a second chat replaces the link — that is how a teacher moves the bot to a
    different chat without clearing anything first.

    Everything fetched is acknowledged even when handling it fails, and the confirmation reply
    is best-effort: a bot the teacher has since blocked would otherwise make the same `/start`
    come back, re-link and fail again on every tick, forever.
    """
    s = settings_store.load()
    if not s.telegram_bot_token:
        return False
    linked = False
    with client_factory(s.telegram_bot_token) as client:
        updates = client.get_updates(s.telegram_update_offset)
        ids = [int(u["update_id"]) for u in updates if isinstance(u.get("update_id"), int)]
        if not ids:
            return False
        last = max(ids)
        try:
            for u in updates:
                msg = u.get("message") or {}
                if not (msg.get("text") or "").strip().startswith("/start"):
                    continue
                raw_chat_id = (msg.get("chat") or {}).get("id")
                if raw_chat_id is None:
                    continue
                chat_id = str(raw_chat_id)
                settings_store.set_telegram(chat_id=chat_id)
                linked = True
                log.info("telegram linked to chat %s", chat_id)
                try:
                    client.send_message(chat_id, LINKED_MESSAGE)
                except (TelegramError, httpx.HTTPError) as e:
                    # The link itself is saved; only the "you're linked" reply was lost.
                    log.warning("telegram link confirmation not delivered: %s", e)
        finally:
            settings_store.set_telegram(offset=last + 1)
    return linked

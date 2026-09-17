import logging
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Mapping, Optional

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.registry import DEFAULT_PROVIDER, get_provider

logger = logging.getLogger("sms.settings")

_UNSET = object()


@dataclass
class Settings:
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extractor_model: Optional[str] = None
    rpm_limit: int = 8
    confidence_threshold: float = 0.0
    auto_reflect: bool = True
    delete_pages_after_marking: bool = True
    # provider id -> last 4 characters of the key saved for it (every provider with a key, not just the active one)
    keys: Dict[str, str] = field(default_factory=dict)
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_instant: bool = True
    telegram_daily_time: str = "07:00"
    timezone: str = "Asia/Singapore"
    app_url: Optional[str] = None
    telegram_daily_last_sent: Optional[str] = None
    telegram_update_offset: int = 0

    @property
    def telegram_linked(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def telegram_bot_hint(self) -> str:
        return self.telegram_bot_token[-4:] if self.telegram_bot_token else ""

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    @property
    def key_hint(self) -> str:
        return self.api_key[-4:] if self.api_key else ""

    @property
    def effective_extractor_model(self) -> str:
        return self.extractor_model or self.model

    @property
    def effective_base_url(self) -> Optional[str]:
        return self.base_url or get_provider(self.provider).base_url

    def public_dict(self) -> dict:
        d = asdict(self)
        d.pop("api_key")
        d.pop("telegram_bot_token")
        d["has_key"] = self.has_key
        d["key_hint"] = self.key_hint
        d["telegram_linked"] = self.telegram_linked
        d["telegram_bot_hint"] = self.telegram_bot_hint
        return d


def default_settings() -> Settings:
    spec = get_provider(DEFAULT_PROVIDER)
    return Settings(provider=spec.id, model=spec.default_model, rpm_limit=spec.default_rpm)


class SettingsStore:
    def __init__(self, db: Database, cipher: KeyCipher):
        self.db = db
        self.cipher = cipher

    def _decrypt(self, enc: Optional[str]) -> Optional[str]:
        if not enc:
            return None
        try:
            return self.cipher.decrypt(enc)
        except ValueError:
            logger.warning("A stored API key cannot be decrypted with this SECRET_KEY — enter it again under Settings")
            return None

    def _key_rows(self) -> Dict[str, str]:
        return {r["provider"]: r["api_key_enc"] for r in self.db.query("SELECT provider, api_key_enc FROM provider_keys")}

    @staticmethod
    def has_key_for(db: Database, provider: str) -> bool:
        """Whether a key is saved for `provider` — the check the API makes before letting an
        assignment pick it. No cipher needed, so it works anywhere a Database does."""
        return bool(db.query("SELECT 1 FROM provider_keys WHERE provider = :p", {"p": provider}))

    def key_for(self, provider: str) -> Optional[str]:
        """The key saved for `provider` (any provider, not just the active one), or None."""
        return self._decrypt(self._key_rows().get(provider))

    def key_hints(self) -> Dict[str, str]:
        """provider -> last 4 characters, for every provider whose key decrypts."""
        out: Dict[str, str] = {}
        for provider, enc in self._key_rows().items():
            key = self._decrypt(enc)
            if key:
                out[provider] = key[-4:]
        return out

    def delete_key(self, provider: str) -> None:
        get_provider(provider)  # raises KeyError for unknown providers
        self.db.execute("DELETE FROM provider_keys WHERE provider = :p", {"p": provider})

    def load(self) -> Settings:
        rows = self.db.query("SELECT * FROM settings WHERE id = 1")
        hints = self.key_hints()
        if not rows:
            s = default_settings()
            s.keys = hints
            return s
        r = rows[0]
        return Settings(
            provider=r["provider"], model=r["model"], api_key=self.key_for(r["provider"]), base_url=r["base_url"],
            extractor_model=r["extractor_model"] or None, rpm_limit=int(r["rpm_limit"]),
            confidence_threshold=float(r["confidence_threshold"]), auto_reflect=bool(r["auto_reflect"]),
            delete_pages_after_marking=bool(r["delete_pages_after_marking"]), keys=hints,
            telegram_bot_token=self._decrypt(r.get("telegram_bot_token_enc")),
            telegram_chat_id=r.get("telegram_chat_id"),
            telegram_instant=bool(r.get("telegram_instant", True)),
            telegram_daily_time=r.get("telegram_daily_time") or "07:00",
            timezone=r.get("timezone") or "Asia/Singapore",
            app_url=r.get("app_url"),
            telegram_daily_last_sent=r.get("telegram_daily_last_sent"),
            telegram_update_offset=int(r.get("telegram_update_offset") or 0),
        )

    def save(self, settings: Settings) -> Settings:
        """Save the settings; a non-blank `api_key` is stored for `settings.provider` only (other
        providers' keys are untouched), a blank one keeps whatever that provider already has."""
        get_provider(settings.provider)  # raises KeyError for unknown providers
        stripped_key = (settings.api_key or "").strip()
        params = {
            "provider": settings.provider, "model": settings.model, "base_url": settings.base_url or None,
            "extractor_model": settings.extractor_model or None,
            "rpm": int(settings.rpm_limit), "thr": float(settings.confidence_threshold),
            "auto_reflect": bool(settings.auto_reflect),
            "delete_pages": bool(settings.delete_pages_after_marking),
            "tg_instant": bool(settings.telegram_instant),
            "tg_time": settings.telegram_daily_time or "07:00",
            "tz": settings.timezone or "Asia/Singapore",
            "app_url": (settings.app_url or "").strip() or None,
        }
        with self.db.transaction() as tx:
            if tx.query("SELECT id FROM settings WHERE id = 1"):
                tx.execute(
                    "UPDATE settings SET provider = :provider, model = :model, base_url = :base_url, "
                    "extractor_model = :extractor_model, rpm_limit = :rpm, "
                    "confidence_threshold = :thr, auto_reflect = :auto_reflect, delete_pages_after_marking = :delete_pages, "
                    "telegram_instant = :tg_instant, telegram_daily_time = :tg_time, timezone = :tz, app_url = :app_url, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                    params,
                )
            else:
                tx.execute(
                    "INSERT INTO settings (id, provider, model, base_url, extractor_model, "
                    "rpm_limit, confidence_threshold, auto_reflect, delete_pages_after_marking, "
                    "telegram_instant, telegram_daily_time, timezone, app_url) VALUES (1, :provider, :model, "
                    ":base_url, :extractor_model, :rpm, :thr, :auto_reflect, :delete_pages, "
                    ":tg_instant, :tg_time, :tz, :app_url)",
                    params,
                )
            if stripped_key:
                enc = self.cipher.encrypt(stripped_key)
                if tx.execute("UPDATE provider_keys SET api_key_enc = :k, updated_at = CURRENT_TIMESTAMP WHERE provider = :p",
                              {"k": enc, "p": settings.provider}) == 0:
                    tx.execute("INSERT INTO provider_keys (provider, api_key_enc) VALUES (:p, :k)",
                               {"p": settings.provider, "k": enc})
            stripped_token = (settings.telegram_bot_token or "").strip()
            if stripped_token:
                tx.execute("UPDATE settings SET telegram_bot_token_enc = :t WHERE id = 1",
                           {"t": self.cipher.encrypt(stripped_token)})
        return self.load()

    def set_telegram(self, *, chat_id: Any = _UNSET, offset: Any = _UNSET, daily_last_sent: Any = _UNSET) -> None:
        sets, params = [], {}
        if chat_id is not _UNSET: sets.append("telegram_chat_id = :c"); params["c"] = chat_id
        if offset is not _UNSET: sets.append("telegram_update_offset = :o"); params["o"] = int(offset)
        if daily_last_sent is not _UNSET: sets.append("telegram_daily_last_sent = :d"); params["d"] = daily_last_sent
        if sets:
            self.db.execute(f"UPDATE settings SET {', '.join(sets)} WHERE id = 1", params)

    def clear_telegram(self) -> None:
        """Forget the bot: the token, the linked chat, the update cursor — and the day the last
        digest went out, so a chat relinked the same day still gets that day's digest."""
        self.db.execute("UPDATE settings SET telegram_bot_token_enc = NULL, telegram_chat_id = NULL, "
                        "telegram_update_offset = 0, telegram_daily_last_sent = NULL WHERE id = 1")

    def for_template(self, tpl: Optional[dict]) -> Settings:
        """The settings a job for this assignment runs with: the global ones, or the template's own
        provider/model (with that provider's saved key and default rpm) when it sets one.

        The saved `base_url` belongs to the global provider, so it only survives when the template
        pins that same provider — pointing another provider at it would send the call to the wrong
        host."""
        s = self.load()
        if not tpl or not tpl.get("provider"):
            return s
        provider = tpl["provider"]
        spec = get_provider(provider)
        s.model = tpl.get("model") or spec.default_model
        s.extractor_model = tpl.get("extractor_model") or None
        s.api_key = self.key_for(provider)
        s.base_url = None if provider != s.provider else s.base_url
        if provider != s.provider:
            s.rpm_limit = spec.default_rpm
        s.provider = provider
        return s

    def ensure_seeded(self, env: Mapping[str, str]) -> None:
        if self.db.query("SELECT id FROM settings WHERE id = 1"):
            return
        provider_id = env.get("LLM_PROVIDER") or DEFAULT_PROVIDER
        spec = get_provider(provider_id)
        self.save(Settings(
            provider=spec.id,
            model=env.get("LLM_MODEL") or spec.default_model,
            api_key=env.get("LLM_API_KEY") or None,
            rpm_limit=spec.default_rpm,
        ))

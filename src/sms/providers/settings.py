import logging
from dataclasses import dataclass, asdict
from typing import Mapping, Optional

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.registry import DEFAULT_PROVIDER, get_provider

logger = logging.getLogger("sms.settings")


@dataclass
class Settings:
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extractor_model: Optional[str] = None
    rpm_limit: int = 8
    confidence_threshold: float = 0.0

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
        d["has_key"] = self.has_key
        d["key_hint"] = self.key_hint
        return d


def default_settings() -> Settings:
    spec = get_provider(DEFAULT_PROVIDER)
    return Settings(provider=spec.id, model=spec.default_model, rpm_limit=spec.default_rpm)


class SettingsStore:
    def __init__(self, db: Database, cipher: KeyCipher):
        self.db = db
        self.cipher = cipher

    def load(self) -> Settings:
        rows = self.db.query("SELECT * FROM settings WHERE id = 1")
        if not rows:
            return default_settings()
        r = rows[0]
        key = None
        if r["api_key_enc"]:
            try:
                key = self.cipher.decrypt(r["api_key_enc"])
            except ValueError:
                logger.warning(
                    "Stored API key cannot be decrypted with this SECRET_KEY — "
                    "enter it again under Settings"
                )
                key = None
        return Settings(
            provider=r["provider"], model=r["model"], api_key=key, base_url=r["base_url"],
            extractor_model=r["extractor_model"] or None, rpm_limit=int(r["rpm_limit"]),
            confidence_threshold=float(r["confidence_threshold"]),
        )

    def save(self, settings: Settings) -> Settings:
        get_provider(settings.provider)  # raises KeyError for unknown providers
        existing = self.db.query("SELECT api_key_enc FROM settings WHERE id = 1")
        stripped_key = (settings.api_key or "").strip()
        if stripped_key:
            key_enc = self.cipher.encrypt(stripped_key)
        else:
            key_enc = existing[0]["api_key_enc"] if existing else None
        params = {
            "provider": settings.provider, "model": settings.model, "base_url": settings.base_url or None,
            "extractor_model": settings.extractor_model or None, "key": key_enc,
            "rpm": int(settings.rpm_limit), "thr": float(settings.confidence_threshold),
        }
        if existing:
            self.db.execute(
                "UPDATE settings SET provider = :provider, model = :model, base_url = :base_url, "
                "extractor_model = :extractor_model, api_key_enc = :key, rpm_limit = :rpm, "
                "confidence_threshold = :thr, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                params,
            )
        else:
            self.db.execute(
                "INSERT INTO settings (id, provider, model, base_url, extractor_model, api_key_enc, "
                "rpm_limit, confidence_threshold) VALUES (1, :provider, :model, :base_url, "
                ":extractor_model, :key, :rpm, :thr)",
                params,
            )
        return self.load()

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

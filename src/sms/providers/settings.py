import logging
from dataclasses import dataclass, asdict, field
from typing import Dict, Mapping, Optional

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
    auto_reflect: bool = True
    delete_pages_after_marking: bool = True
    # provider id -> last 4 characters of the key saved for it (every provider with a key, not just the active one)
    keys: Dict[str, str] = field(default_factory=dict)

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
        }
        with self.db.transaction() as tx:
            if tx.query("SELECT id FROM settings WHERE id = 1"):
                tx.execute(
                    "UPDATE settings SET provider = :provider, model = :model, base_url = :base_url, "
                    "extractor_model = :extractor_model, rpm_limit = :rpm, "
                    "confidence_threshold = :thr, auto_reflect = :auto_reflect, delete_pages_after_marking = :delete_pages, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                    params,
                )
            else:
                tx.execute(
                    "INSERT INTO settings (id, provider, model, base_url, extractor_model, "
                    "rpm_limit, confidence_threshold, auto_reflect, delete_pages_after_marking) VALUES (1, :provider, :model, "
                    ":base_url, :extractor_model, :rpm, :thr, :auto_reflect, :delete_pages)",
                    params,
                )
            if stripped_key:
                enc = self.cipher.encrypt(stripped_key)
                if tx.execute("UPDATE provider_keys SET api_key_enc = :k, updated_at = CURRENT_TIMESTAMP WHERE provider = :p",
                              {"k": enc, "p": settings.provider}) == 0:
                    tx.execute("INSERT INTO provider_keys (provider, api_key_enc) VALUES (:p, :k)",
                               {"p": settings.provider, "k": enc})
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

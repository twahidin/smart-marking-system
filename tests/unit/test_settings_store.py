import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore


@pytest.fixture
def store(tmp_path):
    return SettingsStore(Database(path=str(tmp_path / "s.db")), KeyCipher("secret"))


def test_load_without_row_returns_defaults(store):
    s = store.load()
    assert s.provider == "tokenrouter" and s.model == "z-ai/glm-5.3-free"
    assert s.rpm_limit == 8 and s.api_key is None and not s.has_key


def test_save_encrypts_and_load_decrypts(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-12345678", rpm_limit=60))
    raw = store.db.query("SELECT api_key_enc FROM settings")[0]["api_key_enc"]
    assert "sk-12345678" not in raw
    s = store.load()
    assert s.api_key == "sk-12345678" and s.key_hint == "5678" and s.provider == "openai"


def test_save_without_key_keeps_existing(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-keepme", rpm_limit=60))
    store.save(Settings(provider="openai", model="gpt-5.5", api_key=None, rpm_limit=60))
    assert store.load().api_key == "sk-keepme" and store.load().model == "gpt-5.5"


def test_save_rejects_unknown_provider(store):
    with pytest.raises(KeyError):
        store.save(Settings(provider="nope", model="x", api_key=None, rpm_limit=1))


def test_ensure_seeded_from_env_only_once(store):
    store.ensure_seeded({"LLM_PROVIDER": "openrouter", "LLM_MODEL": "z-ai/glm-5.3-flash", "LLM_API_KEY": "or-key"})
    s = store.load()
    assert s.provider == "openrouter" and s.api_key == "or-key" and s.rpm_limit == 60
    store.ensure_seeded({"LLM_PROVIDER": "openai", "LLM_API_KEY": "other"})
    assert store.load().provider == "openrouter"


def test_ensure_seeded_defaults_when_env_empty(store):
    store.ensure_seeded({})
    s = store.load()
    assert s.provider == "tokenrouter" and s.model == "z-ai/glm-5.3-free" and not s.has_key


def test_public_dict_never_contains_key(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-secret99", rpm_limit=60))
    d = store.load().public_dict()
    assert "api_key" not in d and d["has_key"] is True and d["key_hint"] == "et99"

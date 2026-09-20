import logging

import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore


@pytest.fixture
def store(tmp_path):
    return SettingsStore(Database(path=str(tmp_path / "s.db")), KeyCipher("secret"))


def test_load_without_row_returns_defaults(store):
    s = store.load()
    assert s.provider == "tokenrouter" and s.model == "z-ai/glm-5.3-flash"
    assert s.rpm_limit == 60 and s.api_key is None and not s.has_key


def test_save_encrypts_and_load_decrypts(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-12345678", rpm_limit=60))
    raw = store.db.query("SELECT api_key_enc FROM provider_keys WHERE provider = 'openai'")[0]["api_key_enc"]
    assert "sk-12345678" not in raw
    assert store.db.query("SELECT api_key_enc FROM settings")[0]["api_key_enc"] is None
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
    assert s.provider == "tokenrouter" and s.model == "z-ai/glm-5.3-flash" and not s.has_key


def test_public_dict_never_contains_key(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-secret99", rpm_limit=60))
    d = store.load().public_dict()
    assert "api_key" not in d and d["has_key"] is True and d["key_hint"] == "et99"


def test_save_with_whitespace_key_keeps_existing(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-real-key", rpm_limit=60))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="   ", rpm_limit=60))
    assert store.load().api_key == "sk-real-key"


def test_load_survives_undecryptable_key(tmp_path):
    db_path = str(tmp_path / "s.db")
    store_one = SettingsStore(Database(path=db_path), KeyCipher("one"))
    store_one.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-original", rpm_limit=60))

    store_two = SettingsStore(Database(path=db_path), KeyCipher("two"))
    s = store_two.load()
    assert s.api_key is None and not s.has_key
    assert s.provider == "openai" and s.model == "gpt-5-mini" and s.rpm_limit == 60


def test_delete_pages_after_marking_round_trips_and_defaults_on(store):
    assert store.load().delete_pages_after_marking is True
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=60))
    assert store.load().delete_pages_after_marking is True
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=60, delete_pages_after_marking=False))
    s = store.load()
    assert s.delete_pages_after_marking is False and s.public_dict()["delete_pages_after_marking"] is False


# --- one key per provider -----------------------------------------------------------------------

def test_each_provider_keeps_its_own_key(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-openai-f217", rpm_limit=60))
    store.save(Settings(provider="tokenrouter", model="z-ai/glm-5.3-flash", api_key="tr-key-9999", rpm_limit=60))
    s = store.load()
    assert s.provider == "tokenrouter" and s.api_key == "tr-key-9999"
    # switching back without pasting uses the key saved for that provider
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=60))
    assert store.load().api_key == "sk-openai-f217"
    assert store.key_for("tokenrouter") == "tr-key-9999" and store.key_for("google") is None
    assert store.load().keys == {"openai": "f217", "tokenrouter": "9999"}


def test_switching_to_a_provider_without_a_key_has_no_key(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-openai-f217", rpm_limit=60))
    store.save(Settings(provider="google", model="gemini-3.8-flash", api_key=None, rpm_limit=60))
    s = store.load()
    assert s.provider == "google" and not s.has_key and s.keys == {"openai": "f217"}


def test_delete_key(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-openai-f217", rpm_limit=60))
    store.delete_key("openai")
    assert not store.load().has_key and store.load().keys == {}
    store.delete_key("openai")  # idempotent


def test_migration_copies_the_legacy_single_key_to_its_provider(tmp_path):
    from sms.memory.migrate import upgrade
    path = tmp_path / "legacy.db"
    db = Database(path=str(path), migrate=False)
    upgrade(db.engine, revision="0007")  # the actual pre-0008 schema: no provider_keys, no telegram/insights columns
    cipher = KeyCipher("secret")
    db.execute("INSERT INTO settings (id, provider, model, api_key_enc, rpm_limit, confidence_threshold) "
               "VALUES (1, 'openai', 'gpt-5-mini', :k, 60, 0)", {"k": cipher.encrypt("sk-legacy-1234")})
    db.dispose()
    store = SettingsStore(Database(path=str(path)), cipher)  # re-runs 0008, 0009, ... to head
    assert store.load().api_key == "sk-legacy-1234" and store.load().keys == {"openai": "1234"}
    assert store.db.query("SELECT api_key_enc FROM settings")[0]["api_key_enc"] is None


def test_telegram_and_timezone_fields_round_trip_and_token_is_hidden(store):
    s = store.load()
    assert s.telegram_daily_time == "07:00" and s.timezone == "Asia/Singapore" and s.telegram_instant is True
    assert not s.telegram_linked
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=60,
                        telegram_bot_token="123456:ABCDEF", telegram_daily_time="18:30", timezone="Europe/London",
                        telegram_instant=False, app_url="https://marking.example.sg"))
    s = store.load()
    assert s.telegram_bot_token == "123456:ABCDEF" and s.telegram_bot_hint == "CDEF" and s.telegram_daily_time == "18:30"
    assert s.timezone == "Europe/London" and s.telegram_instant is False and s.app_url == "https://marking.example.sg"
    raw = store.db.query("SELECT telegram_bot_token_enc FROM settings")[0]["telegram_bot_token_enc"]
    assert "ABCDEF" not in raw
    d = s.public_dict()
    assert "telegram_bot_token" not in d and d["telegram_bot_hint"] == "CDEF" and d["telegram_linked"] is False
    # blank token keeps the saved one; linking sets the chat id
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=60, telegram_bot_token=""))
    assert store.load().telegram_bot_token == "123456:ABCDEF"
    store.set_telegram(chat_id="99887", offset=42)
    s = store.load(); assert s.telegram_linked and s.telegram_chat_id == "99887" and s.telegram_update_offset == 42
    store.set_telegram(daily_last_sent="2026-09-17")
    assert store.load().telegram_daily_last_sent == "2026-09-17"
    store.clear_telegram()
    s = store.load(); assert s.telegram_bot_token is None and s.telegram_chat_id is None and not s.telegram_linked
    # unlinking forgets the day the last digest went out, so a same-day relink still gets one
    assert s.telegram_daily_last_sent is None


def test_for_template_overlays_provider_model_and_key(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-openai", rpm_limit=30))
    store.save(Settings(provider="openrouter", model="z-ai/glm-5.3-flash", api_key="or-key", rpm_limit=30))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=30))
    assert store.for_template(None).provider == "openai"
    assert store.for_template({"provider": None, "model": None, "extractor_model": None}).model == "gpt-5-mini"
    s = store.for_template({"provider": "openrouter", "model": "openrouter/auto", "extractor_model": "qwen/qwen3-vl-plus"})
    assert (s.provider, s.model, s.extractor_model, s.api_key) == ("openrouter", "openrouter/auto", "qwen/qwen3-vl-plus", "or-key")
    assert s.rpm_limit == 60 and s.base_url is None          # openrouter's default_rpm, not the global 30
    s = store.for_template({"provider": "openai", "model": "gpt-5.5", "extractor_model": None})
    assert s.api_key == "sk-openai" and s.rpm_limit == 30      # same provider as global keeps the global rpm


def test_for_template_keeps_the_base_url_only_for_the_global_provider(store):
    """A workspace-specific Qwen URL is the global provider's: a template pinned to Qwen keeps it,
    one pinned elsewhere must not be pointed at Alibaba's host."""
    custom = "https://ws-123.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-openai", rpm_limit=30))
    store.save(Settings(provider="qwen", model="qwen3-vl-plus", api_key="qw-key", base_url=custom, rpm_limit=30))
    assert store.load().base_url == custom

    same = store.for_template({"provider": "qwen", "model": "qvq-max", "extractor_model": None})
    assert same.base_url == custom and same.provider == "qwen" and same.api_key == "qw-key"

    other = store.for_template({"provider": "openai", "model": "gpt-5.5", "extractor_model": None})
    assert other.base_url is None and other.api_key == "sk-openai"


@pytest.fixture
def store_with_keys(tmp_path):
    """A store with a global provider (openrouter, with its own saved key) and a saved key for
    google — the provider a subject default will point at in these tests."""
    db = Database(path=str(tmp_path / "s.db"))
    cipher = KeyCipher("secret")
    store = SettingsStore(db, cipher)
    store.save(Settings(provider="openrouter", model="z-ai/glm-5.3-flash", api_key="or-key-1234", rpm_limit=60))
    db.execute("INSERT INTO provider_keys (provider, api_key_enc) VALUES (:p, :k)",
               {"p": "google", "k": cipher.encrypt("g-key-5678")})
    return store, db


def test_for_template_uses_subject_default_when_no_pin(store_with_keys):
    store, db = store_with_keys
    db.execute("INSERT INTO subject_models (subject, provider, model) VALUES ('mt', 'google', 'gemini-3.8-pro')")
    s = store.for_template({"subject": "mt", "provider": None, "model": None})
    assert (s.provider, s.model) == ("google", "gemini-3.8-pro") and s.api_key == store.key_for("google")


def test_pin_beats_subject_default(store_with_keys):
    store, db = store_with_keys
    db.execute("INSERT INTO subject_models (subject, provider, model) VALUES ('computing', 'google', 'g')")
    s = store.for_template({"subject": "computing", "provider": "openrouter", "model": "openai/gpt-5.5"})
    assert (s.provider, s.model) == ("openrouter", "openai/gpt-5.5")


def test_keyless_subject_default_is_ignored(store_with_keys, caplog):
    """No key *row at all* for the subject default's provider: falls back to Settings, logged."""
    store, db = store_with_keys
    db.execute("INSERT INTO subject_models (subject, provider, model) VALUES ('mt', 'anthropic', 'claude-x')")
    with caplog.at_level(logging.INFO, logger="sms.settings"):
        s = store.for_template({"subject": "mt", "provider": None})
    assert s.provider == "openrouter" and "no saved key" in caplog.text


def test_subject_default_with_undecryptable_key_still_overlays_with_no_key(store_with_keys):
    """A key row exists for the subject default's provider but this store's cipher cannot decrypt
    it (wrong SECRET_KEY) — `has_key_for` (row presence, no decryption) is what both the template
    list and this resolution check, so they must agree: the provider is still overlaid, not
    silently swapped for Settings. `api_key` comes back None, so the job then fails the same way a
    pin whose key won't decrypt would — never a silent fallback."""
    store, db = store_with_keys
    db.execute("INSERT INTO subject_models (subject, provider, model) VALUES ('mt', 'google', 'gemini-3.8-pro')")
    wrong_cipher_store = SettingsStore(db, KeyCipher("a-different-secret"))
    s = wrong_cipher_store.for_template({"subject": "mt", "provider": None})
    assert s.provider == "google" and s.model == "gemini-3.8-pro" and s.api_key is None


def test_subject_default_for_the_global_provider_keeps_base_url_and_rpm(tmp_path):
    """A subject default pointed at the same provider as global Settings only overrides the model
    — base_url and rpm_limit belong to the provider connection, not to any one model, so they carry
    over exactly like a same-provider pin does in `_overlay`."""
    db = Database(path=str(tmp_path / "s.db"))
    store = SettingsStore(db, KeyCipher("secret"))
    custom_url = "https://ws-123.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    store.save(Settings(provider="qwen", model="qwen3-vl-plus", api_key="qw-key", base_url=custom_url, rpm_limit=30))
    db.execute("INSERT INTO subject_models (subject, provider, model) VALUES ('science', 'qwen', 'qvq-max')")
    s = store.for_template({"subject": "science", "provider": None})
    assert (s.provider, s.model) == ("qwen", "qvq-max")
    assert s.base_url == custom_url and s.rpm_limit == 30 and s.api_key == "qw-key"

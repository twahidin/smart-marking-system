import re
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from sms.memory.db import Database
from sms.providers.errors import error_message
from sms.providers.models import list_models
from sms.providers.probe import probe
from sms.providers.registry import providers_with_custom
from sms.providers.settings import Settings, SettingsStore
from sms.web.deps import get_db, get_settings_store, require_teacher
from sms.web.errors import ApiError
from sms.web.services.custom_models import add_custom_model, list_custom_models, remove_custom_model
from sms.web.services.telegram import TelegramClient, TelegramError

router = APIRouter(prefix="/api", tags=["settings"], dependencies=[Depends(require_teacher)])


class SettingsBody(BaseModel):
    provider: str
    model: str = Field(min_length=1)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extractor_model: Optional[str] = None
    rpm_limit: int = Field(ge=0, le=10000)
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    auto_reflect: bool = True
    delete_pages_after_marking: bool = True
    telegram_bot_token: Optional[str] = None  # blank keeps whatever is stored
    telegram_instant: bool = True
    telegram_daily_time: str = "07:00"
    timezone: str = "Asia/Singapore"
    app_url: Optional[str] = None


class ModelsBody(BaseModel):
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class TestBody(BaseModel):
    provider: str
    model: str = Field(min_length=1)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extractor_model: Optional[str] = None


class CustomModelBody(BaseModel):
    model_id: str
    label: str = ""
    vision: bool = True


@router.get("/providers")
def providers(db: Database = Depends(get_db)):
    return providers_with_custom(list_custom_models(db))


@router.get("/settings")
def get_settings(store: SettingsStore = Depends(get_settings_store)):
    return store.load().public_dict()


def _model_name(raw: str) -> str:
    model = raw.strip()
    if not model:
        raise ApiError(400, "validation", "model: must not be blank")
    return model


_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def _daily_time(raw: str) -> str:
    value = (raw or "").strip()
    if not _HHMM.fullmatch(value):
        raise ApiError(400, "bad_time", f"telegram_daily_time: {raw!r} is not a HH:MM time")
    return value


def _timezone(raw: str) -> str:
    value = (raw or "").strip()
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ApiError(400, "bad_timezone", f"timezone: {raw!r} is not a known time zone") from None
    return value


@router.put("/settings")
def put_settings(body: SettingsBody, store: SettingsStore = Depends(get_settings_store)):
    model = _model_name(body.model)
    daily_time = _daily_time(body.telegram_daily_time)
    tz = _timezone(body.timezone)
    try:
        saved = store.save(Settings(
            provider=body.provider, model=model, api_key=(body.api_key or "").strip() or None,
            base_url=(body.base_url or "").strip() or None,
            extractor_model=(body.extractor_model or "").strip() or None,
            rpm_limit=body.rpm_limit, confidence_threshold=body.confidence_threshold,
            auto_reflect=body.auto_reflect, delete_pages_after_marking=body.delete_pages_after_marking,
            # A blank token keeps the stored one, exactly like api_key.
            telegram_bot_token=(body.telegram_bot_token or "").strip() or None,
            telegram_instant=body.telegram_instant, telegram_daily_time=daily_time,
            timezone=tz, app_url=(body.app_url or "").strip() or None,
        ))
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))
    return saved.public_dict()


def _saved_key(store: SettingsStore, provider: str) -> Optional[str]:
    """The key saved for the provider being tested/listed — not necessarily the active provider's."""
    try:
        return store.key_for(provider)
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))


@router.delete("/settings/keys/{provider}", status_code=204)
def delete_key(provider: str, store: SettingsStore = Depends(get_settings_store)):
    try:
        store.delete_key(provider)
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))
    return Response(status_code=204)


@router.post("/settings/telegram/test", status_code=204)
def test_telegram(store: SettingsStore = Depends(get_settings_store)):
    s = store.load()
    if not s.telegram_linked:
        raise ApiError(409, "not_linked", "Send /start to the bot from your chat first")
    try:
        with TelegramClient(s.telegram_bot_token) as client:
            client.send_message(s.telegram_chat_id, "Smart Marking is connected ✓")
    except TelegramError as e:
        raise ApiError(502, "telegram_error", str(e)) from None
    return Response(status_code=204)


@router.delete("/settings/telegram", status_code=204)
def unlink_telegram(store: SettingsStore = Depends(get_settings_store)):
    store.clear_telegram()
    return Response(status_code=204)


@router.post("/settings/test")
def test_connection(body: TestBody, store: SettingsStore = Depends(get_settings_store)):
    model = _model_name(body.model)
    key = (body.api_key or "").strip() or _saved_key(store, body.provider)
    if not key:
        raise ApiError(400, "no_key", "Enter an API key first")
    try:
        result = probe(body.provider, model, key,
                       extractor_model=(body.extractor_model or "").strip() or None,
                       base_url=(body.base_url or "").strip() or None)
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))
    return result.to_dict()


@router.post("/settings/models")
def models_for_provider(body: ModelsBody, store: SettingsStore = Depends(get_settings_store)):
    key = (body.api_key or "").strip() or _saved_key(store, body.provider)
    if not key:
        raise ApiError(400, "no_key", "Enter an API key first")
    try:
        ids = list_models(body.provider, key, base_url=(body.base_url or "").strip() or None)
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))
    except Exception as e:  # noqa: BLE001 - the provider's own message is the useful part
        raise ApiError(502, "provider_error", error_message(e))
    return {"models": ids}


@router.post("/settings/models/{provider}", status_code=201)
def add_model(provider: str, body: CustomModelBody, db: Database = Depends(get_db)):
    return add_custom_model(db, provider, body.model_id, body.label, body.vision)


@router.delete("/settings/models/{provider}/{model_id:path}", status_code=204)
def delete_model(provider: str, model_id: str, db: Database = Depends(get_db)):
    remove_custom_model(db, provider, model_id)
    return Response(status_code=204)

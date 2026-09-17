from typing import Optional

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


@router.put("/settings")
def put_settings(body: SettingsBody, store: SettingsStore = Depends(get_settings_store)):
    model = _model_name(body.model)
    current = store.load()
    try:
        saved = store.save(Settings(
            provider=body.provider, model=model, api_key=(body.api_key or "").strip() or None,
            base_url=(body.base_url or "").strip() or None,
            extractor_model=(body.extractor_model or "").strip() or None,
            rpm_limit=body.rpm_limit, confidence_threshold=body.confidence_threshold,
            auto_reflect=body.auto_reflect, delete_pages_after_marking=body.delete_pages_after_marking,
            # SettingsBody has no telegram/timezone/app_url fields yet (Task 6 adds them) — carry
            # the stored values over so an ordinary settings save doesn't reset them to defaults.
            telegram_instant=current.telegram_instant, telegram_daily_time=current.telegram_daily_time,
            timezone=current.timezone, app_url=current.app_url,
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

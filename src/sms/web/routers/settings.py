from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from sms.providers.probe import probe
from sms.providers.registry import registry_as_dicts
from sms.providers.settings import Settings, SettingsStore
from sms.web.deps import get_settings_store, require_teacher
from sms.web.errors import ApiError

router = APIRouter(prefix="/api", tags=["settings"], dependencies=[Depends(require_teacher)])


class SettingsBody(BaseModel):
    provider: str
    model: str = Field(min_length=1)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extractor_model: Optional[str] = None
    rpm_limit: int = Field(ge=0, le=10000)
    confidence_threshold: float = Field(ge=0.0, le=1.0)


class TestBody(BaseModel):
    provider: str
    model: str = Field(min_length=1)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extractor_model: Optional[str] = None


@router.get("/providers")
def providers():
    return registry_as_dicts()


@router.get("/settings")
def get_settings(store: SettingsStore = Depends(get_settings_store)):
    return store.load().public_dict()


@router.put("/settings")
def put_settings(body: SettingsBody, store: SettingsStore = Depends(get_settings_store)):
    try:
        saved = store.save(Settings(
            provider=body.provider, model=body.model.strip(), api_key=(body.api_key or "").strip() or None,
            base_url=(body.base_url or "").strip() or None,
            extractor_model=(body.extractor_model or "").strip() or None,
            rpm_limit=body.rpm_limit, confidence_threshold=body.confidence_threshold,
        ))
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))
    return saved.public_dict()


@router.post("/settings/test")
def test_connection(body: TestBody, store: SettingsStore = Depends(get_settings_store)):
    key = (body.api_key or "").strip() or store.load().api_key
    if not key:
        raise ApiError(400, "no_key", "Enter an API key first")
    try:
        result = probe(body.provider, body.model.strip(), key,
                       extractor_model=(body.extractor_model or "").strip() or None,
                       base_url=(body.base_url or "").strip() or None)
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))
    return result.to_dict()

from typing import Dict, Optional

from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.providers.registry import get_provider
from sms.providers.settings import SettingsStore
from sms.web.errors import ApiError


def list_subject_models(db: Database) -> Dict[str, Optional[dict]]:
    """Every known subject mapped to its saved default (`None` = Auto, follows Settings)."""
    rows = {r["subject"]: r for r in db.query("SELECT subject, provider, model, extractor_model FROM subject_models")}
    return {s: ({"provider": rows[s]["provider"], "model": rows[s]["model"], "extractor_model": rows[s]["extractor_model"]}
                if s in rows else None) for s in SubjectRouter.KNOWN_SUBJECTS}


def set_subject_model(db: Database, subject: str, provider: str, model: str, extractor_model: Optional[str] = None) -> dict:
    try:
        subject = SubjectRouter().resolve(subject)
    except KeyError:
        raise ApiError(400, "bad_subject", "Unknown subject")
    try:
        get_provider(provider)
    except KeyError:
        raise ApiError(400, "bad_provider", "Unknown provider")
    if not SettingsStore.has_key_for(db, provider):
        raise ApiError(400, "no_key_for_provider", f"Save a {get_provider(provider).label} key under Settings first")
    model = (model or "").strip()
    if not model:
        raise ApiError(400, "bad_model", "Choose a model")
    extractor_model = (extractor_model or "").strip() or None
    with db.transaction() as tx:
        tx.execute("DELETE FROM subject_models WHERE subject = :s", {"s": subject})
        tx.execute("INSERT INTO subject_models (subject, provider, model, extractor_model) VALUES (:s, :p, :m, :e)",
                   {"s": subject, "p": provider, "m": model, "e": extractor_model})
    return {"provider": provider, "model": model, "extractor_model": extractor_model}


def clear_subject_model(db: Database, subject: str) -> None:
    db.execute("DELETE FROM subject_models WHERE subject = :s", {"s": subject})

from typing import Dict, List

from sms.memory.db import Database
from sms.providers.registry import get_provider
from sms.web.errors import ApiError


def list_custom_models(db: Database) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for r in db.query("SELECT provider, model_id, label, vision FROM custom_models ORDER BY created_at, model_id"):
        out.setdefault(r["provider"], []).append({"id": r["model_id"], "label": r["label"], "vision": bool(r["vision"]), "custom": True})
    return out


def add_custom_model(db: Database, provider: str, model_id: str, label: str = "", vision: bool = True) -> dict:
    try:
        spec = get_provider(provider)
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))
    if not spec.custom_models:
        raise ApiError(400, "not_supported", f"{spec.label} uses its curated list — type a custom model id instead")
    model_id = (model_id or "").strip(); label = (label or "").strip() or model_id
    if not model_id:
        raise ApiError(400, "bad_model", "Enter the model id")
    with db.transaction() as tx:
        if tx.execute("UPDATE custom_models SET label = :l, vision = :v WHERE provider = :p AND model_id = :m",
                      {"l": label, "v": bool(vision), "p": provider, "m": model_id}) == 0:
            tx.execute("INSERT INTO custom_models (provider, model_id, label, vision) VALUES (:p, :m, :l, :v)",
                       {"p": provider, "m": model_id, "l": label, "v": bool(vision)})
    return {"id": model_id, "label": label, "vision": bool(vision), "custom": True}


def remove_custom_model(db: Database, provider: str, model_id: str) -> None:
    db.execute("DELETE FROM custom_models WHERE provider = :p AND model_id = :m", {"p": provider, "m": model_id})

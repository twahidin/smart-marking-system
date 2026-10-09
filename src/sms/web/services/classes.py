"""Classes: a name, a 4-character code students type, and a classlist (see classlist.py)."""
import secrets
from typing import Any, Dict, List, Optional

from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.timeutil import iso_utc
from sms.web.errors import ApiError

# No 0/O, 1/I/L — the code is read off a projector and typed on a phone.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 4


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalise_code(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def unique_code(db: Database) -> str:
    for _ in range(50):
        code = new_code()
        if not db.query("SELECT 1 FROM classes WHERE code = :c", {"c": code}):
            return code
    raise RuntimeError("could not find an unused class code")


_SELECT = (
    "SELECT c.*, "
    "(SELECT COUNT(*) FROM students s WHERE s.class_id = c.id) AS student_count, "
    "(SELECT COUNT(*) FROM class_assignments a WHERE a.class_id = c.id AND a.status = 'open') AS open_assignments, "
    "COALESCE(c.subject, (SELECT t.subject FROM class_assignments a JOIN assignment_templates t ON t.id = a.template_id "
    "                     WHERE a.class_id = c.id ORDER BY a.id DESC LIMIT 1)) AS shown_subject, "
    "(SELECT COUNT(*) FROM submissions s JOIN class_assignments a ON a.id = s.class_assignment_id "
    " WHERE a.class_id = c.id AND s.status IN ('uploaded', 'queued', 'marking')) AS marking, "
    "(SELECT COUNT(*) FROM submissions s JOIN class_assignments a ON a.id = s.class_assignment_id "
    " WHERE a.class_id = c.id AND s.status = 'needs_you') AS needs_you "
    "FROM classes c")


def _row(r: dict) -> Dict[str, Any]:
    return {
        "id": r["id"], "name": r["name"], "code": r["code"],
        "student_count": int(r["student_count"] or 0), "open_assignments": int(r["open_assignments"] or 0),
        "subject": r["shown_subject"], "marking": int(r["marking"] or 0), "needs_you": int(r["needs_you"] or 0),
        "archived_at": iso_utc(r["archived_at"]),
        "created_at": iso_utc(r["created_at"]), "updated_at": iso_utc(r["updated_at"]),
    }


def clean_subject(value: Optional[str]) -> Optional[str]:
    """None or '' clears the saved subject (the tile then follows the latest class assignment)."""
    if value is None or value == "":
        return None
    if value not in SubjectRouter.KNOWN_SUBJECTS:
        raise ApiError(400, "bad_subject", f"Unknown subject: {value}")
    return value


def list_classes(db: Database) -> List[Dict[str, Any]]:
    rows = db.query(_SELECT + " ORDER BY (c.archived_at IS NOT NULL), c.name, c.id")
    return [_row(r) for r in rows]


def get_class(db: Database, class_id: int) -> Optional[Dict[str, Any]]:
    rows = db.query(_SELECT + " WHERE c.id = :id", {"id": class_id})
    return _row(rows[0]) if rows else None


def _require(db: Database, class_id: int) -> Dict[str, Any]:
    c = get_class(db, class_id)
    if c is None:
        raise ApiError(404, "not_found", "No such class")
    return c


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ApiError(400, "bad_name", "Give the class a name")
    return name[:120]


def create_class(db: Database, name: str, subject: Optional[str] = None) -> Dict[str, Any]:
    cid = db.insert("INSERT INTO classes (name, code, subject) VALUES (:n, :c, :s) RETURNING id",
                    {"n": _clean_name(name), "c": unique_code(db), "s": clean_subject(subject)})
    return get_class(db, cid)  # type: ignore[return-value]


_KEEP: Any = object()


def update_class(db: Database, class_id: int, *, name: str, subject: Any = _KEEP) -> Dict[str, Any]:
    """Rename, and set or clear the subject when the caller sent one (absent = keep)."""
    _require(db, class_id)
    if subject is _KEEP:
        db.execute("UPDATE classes SET name = :n, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                   {"n": _clean_name(name), "id": class_id})
    else:
        db.execute("UPDATE classes SET name = :n, subject = :s, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                   {"n": _clean_name(name), "s": clean_subject(subject), "id": class_id})
    return get_class(db, class_id)  # type: ignore[return-value]


rename_class = update_class   # older callers and tests


def set_archived(db: Database, class_id: int, archived: bool) -> Dict[str, Any]:
    _require(db, class_id)
    if archived:
        db.execute("UPDATE classes SET archived_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                   {"id": class_id})
    else:
        db.execute("UPDATE classes SET archived_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = :id", {"id": class_id})
    return get_class(db, class_id)  # type: ignore[return-value]


def regenerate_code(db: Database, class_id: int) -> Dict[str, Any]:
    """New code: the old link stops working; student sessions (which hold ids) keep working."""
    _require(db, class_id)
    db.execute("UPDATE classes SET code = :c, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
               {"c": unique_code(db), "id": class_id})
    return get_class(db, class_id)  # type: ignore[return-value]

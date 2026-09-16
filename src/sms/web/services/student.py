"""What a student can see: their class, their assignments, their own hand-in and released feedback."""
from typing import Any, Dict

from sms.memory.db import Database
from sms.web.errors import ApiError
from sms.web.services.classes import normalise_code

NO_CLASS = "That class code is not right — check the link your teacher shared"


def lookup_student(db: Database, code: str, reg_no: int) -> Dict[str, Any]:
    code = normalise_code(code)
    rows = db.query("SELECT id, name, code FROM classes WHERE code = :c AND archived_at IS NULL", {"c": code})
    if not rows:
        raise ApiError(404, "no_such_class", NO_CLASS)
    cls = rows[0]
    st = db.query("SELECT id, name, reg_no FROM students WHERE class_id = :c AND reg_no = :r", {"c": cls["id"], "r": reg_no})
    if not st:
        raise ApiError(404, "no_such_student", f"No student #{reg_no} in this class — check the number on your class list")
    return {"class_id": cls["id"], "class_name": cls["name"], "code": cls["code"],
            "student_id": st[0]["id"], "student_name": st[0]["name"], "reg_no": int(st[0]["reg_no"])}


def touch_last_seen(db: Database, student_id: int) -> None:
    db.execute("UPDATE students SET last_seen_at = CURRENT_TIMESTAMP WHERE id = :s", {"s": student_id})


def public(found: Dict[str, Any]) -> Dict[str, Any]:
    return {"class_name": found["class_name"], "code": found["code"], "student_name": found["student_name"], "reg_no": found["reg_no"]}

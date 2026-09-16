"""The classlist CSV: two columns, name and reg_no, in any order; header names are matched loosely."""
import csv
import io
import re
from typing import Any, Dict, List, Optional, Tuple

from sms.memory.db import Database
from sms.timeutil import iso_utc
from sms.web.errors import ApiError

_HEADERS = {
    "name": "name", "studentname": "name", "fullname": "name",
    "regno": "reg_no", "registerno": "reg_no", "registernumber": "reg_no", "regnumber": "reg_no",
    "indexno": "reg_no", "id": "reg_no",
}
HEADER_ERROR = "The first row must have the columns name and reg_no"


def _norm_header(h: str) -> Optional[str]:
    return _HEADERS.get(re.sub(r"[^a-z]", "", (h or "").lower()))


def parse_classlist(data: bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Rows with per-row `issues` (missing_name, bad_reg_no, duplicate_reg_no), plus file-level errors."""
    text = data.decode("utf-8-sig", errors="replace")
    lines = [r for r in csv.reader(io.StringIO(text))]
    if not any(any(c.strip() for c in r) for r in lines):
        return [], ["The file is empty"]
    header = [_norm_header(h) for h in lines[0]]
    if "name" not in header or "reg_no" not in header:
        return [], [HEADER_ERROR]
    ni, ri = header.index("name"), header.index("reg_no")
    rows: List[Dict[str, Any]] = []
    for line in lines[1:]:
        if not any(c.strip() for c in line):
            continue
        name = line[ni].strip() if ni < len(line) else ""
        raw = line[ri].strip() if ri < len(line) else ""
        reg = int(raw) if raw.isdigit() and int(raw) > 0 else None
        issues = []
        if reg is None:
            issues.append("bad_reg_no")
        if not name:
            issues.append("missing_name")
        rows.append({"reg_no": reg, "raw_reg_no": raw, "name": name, "issues": issues})
    seen: Dict[int, int] = {}
    for r in rows:
        if r["reg_no"] is not None:
            seen[r["reg_no"]] = seen.get(r["reg_no"], 0) + 1
    for r in rows:
        if r["reg_no"] is not None and seen[r["reg_no"]] > 1:
            r["issues"].append("duplicate_reg_no")
    return rows, []


def list_students(db: Database, class_id: int) -> List[Dict[str, Any]]:
    rows = db.query("SELECT s.*, (SELECT COUNT(*) FROM submissions x WHERE x.student_id = s.id) AS submissions "
                    "FROM students s WHERE s.class_id = :c ORDER BY s.reg_no", {"c": class_id})
    return [{"id": r["id"], "reg_no": int(r["reg_no"]), "name": r["name"], "submissions": int(r["submissions"] or 0),
             "last_seen_at": iso_utc(r["last_seen_at"])} for r in rows]


def replace_classlist(db: Database, class_id: int, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Upsert by reg_no; students missing from the new list are removed unless they have submissions
    (those are kept and reported in `kept`)."""
    if not db.query("SELECT 1 FROM classes WHERE id = :c", {"c": class_id}):
        raise ApiError(404, "not_found", "No such class")
    clean: Dict[int, str] = {}
    for r in rows or []:
        reg, name = r.get("reg_no"), (r.get("name") or "").strip()
        if not isinstance(reg, int) or isinstance(reg, bool) or reg <= 0 or not name or reg in clean:
            raise ApiError(400, "bad_rows", "Every row needs a name and a unique positive register number")
        clean[reg] = name[:120]
    if not clean:
        raise ApiError(400, "bad_rows", "The classlist is empty")
    kept: List[int] = []
    with db.transaction() as tx:
        existing = {int(r["reg_no"]): r for r in tx.query(
            "SELECT s.id, s.reg_no, (SELECT COUNT(*) FROM submissions x WHERE x.student_id = s.id) AS n "
            "FROM students s WHERE s.class_id = :c", {"c": class_id})}
        for reg, name in clean.items():
            if reg in existing:
                tx.execute("UPDATE students SET name = :n WHERE id = :id", {"n": name, "id": existing[reg]["id"]})
            else:
                tx.execute("INSERT INTO students (class_id, reg_no, name) VALUES (:c, :r, :n)", {"c": class_id, "r": reg, "n": name})
        for reg, r in existing.items():
            if reg in clean:
                continue
            if int(r["n"] or 0) > 0:
                kept.append(reg)
            else:
                tx.execute("DELETE FROM students WHERE id = :id", {"id": r["id"]})
        tx.execute("UPDATE classes SET updated_at = CURRENT_TIMESTAMP WHERE id = :c", {"c": class_id})
    return {"students": list_students(db, class_id), "kept": sorted(kept)}

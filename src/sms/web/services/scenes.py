"""Numbers the painted scenes need that no existing route carries: the Review desk's trays and the desk pinboard."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sms.memory.db import Database
from sms.timeutil import iso_utc

_UNSETTLED = "('uploaded', 'queued', 'marking', 'needs_you', 'failed')"


def review_summary(db: Database) -> Dict[str, Any]:
    needs_you = db.query("SELECT COUNT(*) AS n FROM teacher_queue WHERE status = 'pending'")[0]["n"]
    remarked = db.query("SELECT COUNT(*) AS n FROM student_corrections WHERE status = 'remarked'")[0]["n"]
    ready = db.query(
        "SELECT a.id, a.class_id, a.title, c.name AS class_name FROM class_assignments a JOIN classes c ON c.id = a.class_id "
        "WHERE a.status = 'open' "
        "AND EXISTS (SELECT 1 FROM submissions s WHERE s.class_assignment_id = a.id) "
        f"AND NOT EXISTS (SELECT 1 FROM submissions s WHERE s.class_assignment_id = a.id AND s.status IN {_UNSETTLED}) "
        "ORDER BY a.created_at, a.id")
    return {"needs_you": int(needs_you or 0), "remarked": int(remarked or 0), "ready_to_release": len(ready),
            "ready_sets": [{"id": r["id"], "class_id": r["class_id"], "class_name": r["class_name"], "title": r["title"]} for r in ready[:5]]}


def _as_utc(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(value).replace(" ", "T").replace("Z", "+00:00"))
    # stored text is naive UTC (sms.timeutil convention); astimezone() on a naive value would assume the host's zone
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def due_class_assignments(db: Database, days: int) -> List[Dict[str, Any]]:
    """Open class sets due between now and `days` from now, soonest first. Dates are compared in Python so the
    same code runs on SQLite (text) and Postgres (timestamp)."""
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=max(0, days))
    rows = db.query("SELECT a.id, a.class_id, a.title, a.due_at, a.status, c.name AS class_name FROM class_assignments a "
                    "JOIN classes c ON c.id = a.class_id WHERE a.status = 'open' AND a.due_at IS NOT NULL")
    due = [r for r in rows if now <= _as_utc(r["due_at"]) <= until]
    due.sort(key=lambda r: (_as_utc(r["due_at"]), r["id"]))
    return [{"id": r["id"], "class_id": r["class_id"], "class_name": r["class_name"], "title": r["title"],
             "due_at": iso_utc(r["due_at"]), "status": r["status"]} for r in due]

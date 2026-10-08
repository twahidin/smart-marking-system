"""The Marking Room: who is on which desk, how far the class set has got, and (teachers only) what
each crew member noted. Reader = the read stage, Marker = mark, Checker = check plus the done notes."""
import json
from typing import Any, Dict, List, Optional

from sms.memory.db import Database
from sms.timeutil import iso_utc
from sms.web.errors import ApiError

DESK_STAGES = ("read", "mark", "check", "feedback")
CREW_OF_STAGE = {"read": "reader", "mark": "marker", "check": "checker", "done": "checker"}


def _scope(class_assignment_id: Optional[int]) -> tuple:
    if class_assignment_id is None:
        return "", {}
    return " AND s.class_assignment_id = :ca", {"ca": class_assignment_id}


def room_snapshot(db: Database, class_assignment_id: Optional[int] = None) -> Dict[str, Any]:
    where, params = _scope(class_assignment_id)
    rows = db.query("SELECT s.id, s.label, s.status, s.stage, s.updated_at, s.created_at, st.reg_no AS reg_no "
                    "FROM submissions s LEFT JOIN students st ON st.id = s.student_id WHERE 1 = 1" + where +
                    " ORDER BY s.id", params)
    began = {r["submission_id"]: r["t"] for r in db.query(
        "SELECT e.submission_id, MAX(e.created_at) AS t FROM marking_events e JOIN submissions s ON s.id = e.submission_id "
        "WHERE e.kind = 'started'" + where + " GROUP BY e.submission_id", params)}
    counts = {k: 0 for k in ("queued", *DESK_STAGES, "done", "needs_you", "failed")}
    desks: List[dict] = []
    for r in rows:
        if r["status"] in ("done", "needs_you", "failed"):
            counts[r["status"]] += 1
        elif r["stage"] in DESK_STAGES:
            counts[r["stage"]] += 1
            desks.append({"stage": r["stage"], "submission_id": r["id"], "label": r["label"], "reg_no": r["reg_no"],
                          "since": iso_utc(began.get(r["id"]) or r["updated_at"])})
        else:
            counts["queued"] += 1
    started = db.query("SELECT MIN(s.created_at) AS t FROM submissions s WHERE s.status NOT IN ('done', 'needs_you', 'failed')"
                       + where, params)
    last = db.query("SELECT COALESCE(MAX(e.id), 0) AS i FROM marking_events e JOIN submissions s ON s.id = e.submission_id "
                    "WHERE 1 = 1" + where, params)
    return {"counts": counts, "started_at": iso_utc(started[0]["t"]) if started and started[0]["t"] else None,
            "desks": desks, "last_event_id": int(last[0]["i"] or 0)}


def events_after(db: Database, after_id: int, class_assignment_id: Optional[int] = None, limit: int = 200) -> List[dict]:
    where, params = _scope(class_assignment_id)
    params = {**params, "a": after_id, "lim": limit}
    rows = db.query("SELECT e.id, e.submission_id, e.stage, e.kind, e.created_at FROM marking_events e "
                    "JOIN submissions s ON s.id = e.submission_id WHERE e.id > :a AND e.kind != 'note'" + where +
                    " ORDER BY e.id LIMIT :lim", params)
    return [{"id": r["id"], "submission_id": r["submission_id"], "stage": r["stage"], "kind": r["kind"],
             "created_at": iso_utc(r["created_at"])} for r in rows]


def thoughts(db: Database, submission_id: int) -> Dict[str, List[dict]]:
    if not db.query("SELECT 1 FROM submissions WHERE id = :s", {"s": submission_id}):
        raise ApiError(404, "not_found", "No such script")
    rows = db.query("SELECT stage, q_id, note, created_at FROM marking_events WHERE submission_id = :s AND kind = 'note' "
                    "ORDER BY id", {"s": submission_id})
    out: Dict[str, List[dict]] = {"reader": [], "marker": [], "checker": []}
    for r in rows:
        crew = CREW_OF_STAGE.get(r["stage"])
        if crew:
            out[crew].append({"at": iso_utc(r["created_at"]), "q_id": r["q_id"], "note": r["note"] or ""})
    return out


def sse_line(event: dict) -> str:
    return f"id: {event['id']}\nevent: stage\ndata: {json.dumps(event)}\n\n"

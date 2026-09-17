"""The notification outbox: a row per thing worth telling the teacher about, flushed to Telegram.

Writing the row is a single insert on the path of whatever just happened (a hand-in, a drain of
marking) — it never talks to the network, so a slow or blocked bot can neither delay an upload nor
fail a marking job. The worker flushes the unsent rows every few seconds, batching same-kind rows
for one assignment into one message: 30 hand-ins in a lesson are one "30 new hand-ins", not 30
buzzes. A refused send leaves the row unsent with the reason on it and comes back after a growing
delay (10 s doubling to an hour), and is abandoned after twenty refusals rather than retried for
ever; sent rows are deleted thirty days later.

Everything a person typed (names, titles, class names) goes through `escape` — messages are sent
with Telegram's HTML parse mode, where a student called "Tan <b>" would otherwise break the message.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sms.memory.db import Database
from sms.web.services.telegram import TelegramClient, app_base_url, escape

log = logging.getLogger("sms.notify")

HAND_IN = "hand_in"
MARKING_DONE = "marking_done"
# A script whose marks are not settled yet — the drain is still running.
IN_FLIGHT = ("uploaded", "queued", "marking")
SETTLED = ("done", "needs_you")
NAMES_SHOWN = 10        # hand-ins listed by name in one message before the rest become "…"
DIGEST_WINDOW_H = 24
DEFAULT_DAILY_TIME = (7, 0)
GROUPS_PER_TICK = 10    # messages one flush will try, so a backlog drains over ticks
BACKOFF_BASE_S = 10     # first retry delay; it doubles per attempt...
BACKOFF_MAX_S = 3600    # ...up to an hour
MAX_ATTEMPTS = 20       # after this many refusals the row is abandoned rather than retried forever
RETENTION_DAYS = 30     # sent rows older than this are deleted on the daily tick
SQL_TIME = "%Y-%m-%d %H:%M:%S"


def _stamp(when: datetime) -> str:
    """UTC in the same 'YYYY-MM-DD HH:MM:SS' shape SQL's CURRENT_TIMESTAMP writes, so the stored
    text sorts and compares correctly against it."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime(SQL_TIME)


# --- settings helpers -------------------------------------------------------------------------

def _instant(db: Database) -> bool:
    """`telegram_instant` straight off the settings row: the writers run where there is a Database
    but not necessarily a SettingsStore, and this flag needs no cipher."""
    rows = db.query("SELECT telegram_instant FROM settings WHERE id = 1")
    return bool(rows[0]["telegram_instant"]) if rows else True


def _zone(name: Optional[str]):
    try:
        return ZoneInfo(name) if name else timezone.utc
    except Exception:  # noqa: BLE001 - an unknown tz name must not stop the digest
        log.warning("unknown timezone %r — using UTC", name)
        return timezone.utc


def _daily_time(value: Optional[str]) -> Tuple[int, int]:
    try:
        h, m = (value or "").split(":")
        return int(h), int(m)
    except (ValueError, AttributeError):
        return DEFAULT_DAILY_TIME


# --- links ------------------------------------------------------------------------------------

def assignment_url(base: Optional[str], class_id: int, caid: int) -> Optional[str]:
    return f"{base}/classes/{class_id}/assignments/{caid}" if base else None


def review_url(base: Optional[str]) -> Optional[str]:
    return f"{base}/review" if base else None


# --- writing rows -----------------------------------------------------------------------------

def _insert(db: Database, kind: str, caid: Optional[int], payload: Dict[str, Any]) -> int:
    return db.insert(
        "INSERT INTO notifications (kind, class_assignment_id, payload_json) VALUES (:k, :a, :p) RETURNING id",
        {"k": kind, "a": caid, "p": json.dumps(payload, sort_keys=True)},
    )


def _student(db: Database, student_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """A snapshot of who handed in, so the message still reads right if the class list changes.
    None when there is nobody to name — no student id, no row, or a register number that is
    somehow NULL — and then the hand-in is simply not announced rather than crashing the flush."""
    if student_id is None:
        return None
    rows = db.query("SELECT id, reg_no, name FROM students WHERE id = :s", {"s": student_id})
    if not rows or rows[0]["reg_no"] is None:
        return None
    return {"student_id": student_id, "reg_no": int(rows[0]["reg_no"]), "name": rows[0]["name"]}


def record_hand_in(db: Database, submission_row: Dict[str, Any]) -> Optional[int]:
    """Note a hand-in against a class assignment. Returns the notification id, or None when there
    is nothing to announce (not a class hand-in, a teacher upload, or instant messages are off).

    Either way a hand-in re-arms `last_done_notified_at`: the class is marking again, so the next
    time everything settles is worth announcing even though the last drain already was.
    """
    caid = submission_row.get("class_assignment_id")
    if caid is None:
        return None
    db.execute("UPDATE class_assignments SET last_done_notified_at = NULL WHERE id = :a", {"a": caid})
    if submission_row.get("source") != "student" or not _instant(db):
        return None
    who = _student(db, submission_row.get("student_id"))
    if who is None:
        log.warning("hand-in on assignment %s has no nameable student — not announcing it", caid)
        return None
    return _insert(db, HAND_IN, int(caid), who)


def _drain_counts(db: Database, caid: int) -> Dict[str, int]:
    """How far this assignment's marking has got: scripts still in flight, scripts with marks, and
    scripts waiting in the review queue."""
    row = db.query(
        "SELECT SUM(CASE WHEN status IN ('uploaded', 'queued', 'marking') THEN 1 ELSE 0 END) AS in_flight, "
        "SUM(CASE WHEN status IN ('done', 'needs_you') THEN 1 ELSE 0 END) AS marked "
        "FROM submissions WHERE class_assignment_id = :a", {"a": caid})[0]
    needs = db.query(
        "SELECT COUNT(DISTINCT q.submission_id) AS c FROM teacher_queue q "
        "JOIN submissions s ON s.id = q.submission_id "
        "WHERE s.class_assignment_id = :a AND q.status = 'pending'", {"a": caid})[0]["c"]
    return {"in_flight": int(row["in_flight"] or 0), "marked": int(row["marked"] or 0),
            "needs_you": int(needs or 0)}


def on_mark_settled(db: Database, jobs, submission_id: int) -> None:
    """Called after a mark job finishes (however it finished). When the assignment this script
    belongs to has nothing left in flight, generate its insights and — once per drain — note that
    marking is finished.

    `last_done_notified_at` is the once-per-drain guard: it is stamped the first time a drain
    settles and cleared by the next hand-in, so a class that trickles in over a morning gets one
    message when the last script lands, not one per script.
    """
    rows = db.query("SELECT class_assignment_id FROM submissions WHERE id = :s", {"s": submission_id})
    if not rows or rows[0]["class_assignment_id"] is None:
        return
    caid = int(rows[0]["class_assignment_id"])
    guard = db.query("SELECT last_done_notified_at FROM class_assignments WHERE id = :a", {"a": caid})
    if not guard:  # the assignment was deleted out from under its scripts
        return
    counts = _drain_counts(db, caid)
    if counts["in_flight"] or not counts["marked"]:
        return
    # local import: insights_job -> insights -> submissions -> this module
    from sms.worker.insights_job import enqueue_insights
    enqueue_insights(jobs, caid)
    # Claiming the drain and announcing it are one step. Two mark jobs settling the last two scripts
    # within the same moment both see an empty in-flight count, so the read-then-write version wrote
    # two messages; only the caller whose conditional UPDATE actually stamped the row — rowcount 1 —
    # gets to announce.
    if db.execute("UPDATE class_assignments SET last_done_notified_at = CURRENT_TIMESTAMP "
                  "WHERE id = :a AND last_done_notified_at IS NULL", {"a": caid}) != 1:
        return
    if not _instant(db):
        return
    _insert(db, MARKING_DONE, caid, {"marked": counts["marked"], "needs_you": counts["needs_you"],
                                     "insights": True})


# --- formatting -------------------------------------------------------------------------------

def _who(row: Dict[str, Any]) -> str:
    name = (row.get("name") or "").strip()
    reg_no = row.get("reg_no")
    if reg_no is None:
        return name or "a student"
    return f"#{reg_no} {name}".strip()


def format_hand_ins(ca_title: str, class_name: str, rows: List[dict], url: Optional[str]) -> str:
    names = [_who(r) for r in rows]
    shown = ", ".join(escape(n) for n in names[:NAMES_SHOWN])
    if len(names) > NAMES_SHOWN:
        shown += ", …"
    head = (f"📥 <b>{escape(class_name)} · {escape(ca_title)}</b> — "
            f"{len(names)} new hand-in{'' if len(names) == 1 else 's'}: {shown}")
    return head if not url else f'{head}\n<a href="{url}">Open the roster</a>'


def format_marking_done(ca_title: str, class_name: str, rows: List[dict], url: Optional[str],
                        review: Optional[str] = None) -> str:
    """The counts come from the newest row of the batch — two drains that were never flushed in
    between are one message about where the assignment now stands."""
    last = rows[-1] if rows else {}
    marked, needs = int(last.get("marked") or 0), int(last.get("needs_you") or 0)
    head = (f"✅ <b>{escape(class_name)} · {escape(ca_title)}</b> — marking finished: "
            f"{marked} marked, {needs} need you")
    links = []
    if review:
        links.append(f'<a href="{review}">Review</a>')
    if url and last.get("insights"):
        links.append(f'<a href="{url}?tab=insights">Insights</a>')
    return head if not links else head + "\n" + " · ".join(links)


# --- the flush --------------------------------------------------------------------------------

def _assignment(db: Database, caid: int) -> Optional[dict]:
    rows = db.query("SELECT a.id, a.class_id, a.title, cl.name AS class_name FROM class_assignments a "
                    "JOIN classes cl ON cl.id = a.class_id WHERE a.id = :a", {"a": caid})
    return rows[0] if rows else None


def _ids(items: List[dict]) -> Tuple[str, Dict[str, Any]]:
    params = {f"i{n}": r["id"] for n, r in enumerate(items)}
    return ", ".join(f":{k}" for k in params), params


def _mark_sent(db: Database, items: List[dict]) -> None:
    clause, params = _ids(items)
    db.execute(f"UPDATE notifications SET sent_at = CURRENT_TIMESTAMP, error = NULL WHERE id IN ({clause})", params)


def _backoff_s(attempts: int) -> int:
    """How long to wait after `attempts` failures: 10 s doubling per attempt, capped at an hour."""
    return min(BACKOFF_BASE_S * 2 ** attempts, BACKOFF_MAX_S)


def _mark_error(db: Database, items: List[dict], error: str, now: datetime) -> None:
    """Record the refusal and schedule the retry. Rows in one group can be on different attempt
    counts (a hand-in that arrived after the group first failed), so each count is stamped with its
    own delay; a row that has been refused MAX_ATTEMPTS times is stamped sent — the error stays on
    it — so an unreachable chat cannot keep the outbox spinning forever."""
    by_attempts: Dict[int, List[dict]] = {}
    for r in items:
        by_attempts.setdefault(int(r.get("attempts") or 0) + 1, []).append(r)
    for attempts, rows in by_attempts.items():
        clause, params = _ids(rows)
        params = {**params, "e": error[:500], "n": attempts}
        if attempts >= MAX_ATTEMPTS:
            log.warning("abandoned %d notification(s) after %d attempts: %s", len(rows), attempts, error[:200])
            db.execute(f"UPDATE notifications SET attempts = :n, error = :e, sent_at = CURRENT_TIMESTAMP "
                       f"WHERE id IN ({clause})", params)
            continue
        params["nx"] = _stamp(now + timedelta(seconds=_backoff_s(attempts)))
        db.execute(f"UPDATE notifications SET attempts = :n, error = :e, next_attempt_at = :nx "
                   f"WHERE id IN ({clause})", params)


def _format_group(db: Database, kind: str, caid: Optional[int], items: List[dict],
                  base: Optional[str]) -> Optional[str]:
    ca = _assignment(db, int(caid)) if caid is not None else None
    if ca is None:
        return None
    url = assignment_url(base, ca["class_id"], ca["id"])
    payloads = [json.loads(r["payload_json"] or "{}") for r in items]
    if kind == HAND_IN:
        return format_hand_ins(ca["title"], ca["class_name"], payloads, url)
    if kind == MARKING_DONE:
        return format_marking_done(ca["title"], ca["class_name"], payloads, url, review_url(base))
    log.warning("no formatter for notification kind %r", kind)
    return None


def flush_notifications(settings_store, db: Database,
                        client_factory: Callable[[str], TelegramClient] = TelegramClient,
                        now: Optional[datetime] = None) -> int:
    """Send the notifications that are due, batched by (kind, class assignment). Returns the number
    of messages sent. A no-op until the teacher has linked a chat — the rows simply wait.

    A row whose assignment has gone (or whose kind nothing formats) is marked sent rather than left
    to be retried forever; a row the Bot API refused keeps the reason and comes back after a growing
    delay, and is abandoned once it has been refused MAX_ATTEMPTS times. At most GROUPS_PER_TICK
    messages go out per call, so a morning's backlog drains over several ticks instead of hammering
    the Bot API in one burst.

    Every failure a group can raise is caught, not just the ones Telegram is supposed to raise: a
    gateway that answers an HTML 502 makes the JSON decode blow up, and one such group must not take
    the rest of the flush down with it.
    """
    now = now or datetime.now(timezone.utc)
    settings = settings_store.load()
    if not settings.telegram_linked:
        return 0
    rows = db.query("SELECT * FROM notifications WHERE sent_at IS NULL "
                    "AND (next_attempt_at IS NULL OR next_attempt_at <= :now) ORDER BY created_at, id",
                    {"now": _stamp(now)})
    if not rows:
        return 0
    groups: Dict[Tuple[str, Any], List[dict]] = {}
    for r in rows:
        groups.setdefault((r["kind"], r["class_assignment_id"]), []).append(r)
    base = app_base_url(settings)
    sent = 0
    with client_factory(settings.telegram_bot_token) as client:
        for (kind, caid), items in list(groups.items())[:GROUPS_PER_TICK]:
            text = _format_group(db, kind, caid, items, base)
            if text is None:
                _mark_sent(db, items)
                continue
            try:
                client.send_message(settings.telegram_chat_id, text)
            except Exception as e:  # noqa: BLE001 - recorded on the rows; the other groups still go
                log.warning("telegram send failed for %s: %s", kind, e)
                _mark_error(db, items, str(e) or type(e).__name__, now)
                continue
            _mark_sent(db, items)
            sent += 1
    return sent


def purge_sent_notifications(db: Database, now: datetime, days: int = RETENTION_DAYS) -> int:
    """Delete sent rows older than `days`. The outbox is a queue, not a log: once a message has gone
    (or been abandoned) the row is only taking up space. Returns the number deleted."""
    cutoff = _stamp(now - timedelta(days=days))
    return db.execute("DELETE FROM notifications WHERE sent_at IS NOT NULL AND sent_at < :cutoff",
                      {"cutoff": cutoff})


# --- the daily digest -------------------------------------------------------------------------

_DIGEST_SQL = (
    "SELECT a.id, a.class_id, a.title, cl.name AS class_name, "
    "(SELECT COUNT(*) FROM submissions s WHERE s.class_assignment_id = a.id AND s.source = 'student' "
    " AND s.handed_in_at >= :cutoff) AS handed_in, "
    "(SELECT COUNT(DISTINCT s.id) FROM submissions s JOIN marking_runs mr ON mr.run_id = s.run_id "
    " WHERE s.class_assignment_id = a.id AND mr.created_at >= :cutoff) AS marked, "
    "(SELECT COUNT(DISTINCT q.submission_id) FROM teacher_queue q JOIN submissions s ON s.id = q.submission_id "
    " WHERE s.class_assignment_id = a.id AND q.status = 'pending') AS needs_you, "
    "(SELECT COUNT(*) FROM assignment_insights i WHERE i.class_assignment_id = a.id "
    " AND i.report_json IS NOT NULL) AS has_report, "
    "CASE WHEN a.released_at >= :cutoff THEN 1 ELSE 0 END AS released "
    "FROM class_assignments a JOIN classes cl ON cl.id = a.class_id "
    "WHERE cl.archived_at IS NULL ORDER BY cl.name, cl.id, a.id"
)


def _digest_line(r: dict, base: Optional[str]) -> str:
    bits = []
    if r["handed_in"]:
        bits.append(f"{int(r['handed_in'])} handed in")
    if r["marked"]:
        bits.append(f"{int(r['marked'])} marked")
    if r["needs_you"]:
        bits.append(f"{int(r['needs_you'])} need you")
    if r["released"]:
        bits.append("feedback released")
    line = f"• {escape(r['title'])} — {', '.join(bits)}"
    url = assignment_url(base, r["class_id"], r["id"])
    if not url:
        return line
    links = [f'<a href="{url}">open</a>']
    if r["has_report"]:
        links.append(f'<a href="{url}?tab=insights">insights</a>')
    return f"{line} → " + " · ".join(links)


def build_daily_digest(db: Database, settings, now: Optional[datetime] = None) -> Optional[str]:
    """One morning message covering the last 24 h, grouped class by class. None when nothing
    happened — a quiet day sends no message at all rather than a message saying nothing happened.

    `now` (default: the real clock) fixes both the window and the date in the heading.
    """
    now = (now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = (now.astimezone(timezone.utc) - timedelta(hours=DIGEST_WINDOW_H)).strftime("%Y-%m-%d %H:%M:%S")
    rows = [r for r in db.query(_DIGEST_SQL, {"cutoff": cutoff})
            if r["handed_in"] or r["marked"] or r["released"]]
    if not rows:
        return None
    base = app_base_url(settings)
    local = now.astimezone(_zone(settings.timezone))
    lines = [f"☀️ <b>Smart Marking — {local:%a} {local.day} {local:%b}</b>"]
    by_class: Dict[Tuple[Any, str], List[dict]] = {}
    for r in rows:
        by_class.setdefault((r["class_id"], r["class_name"]), []).append(r)
    for (_class_id, name), items in by_class.items():
        lines.append(f"<b>{escape(name)}</b>")
        lines.extend(_digest_line(r, base) for r in items)
    return "\n".join(lines)


def maybe_send_daily(settings_store, db: Database, now: datetime,
                     client_factory: Callable[[str], TelegramClient] = TelegramClient) -> bool:
    """Send the digest if it is past the teacher's send time in their timezone and today's has not
    gone out. Returns True only when a message was actually sent.

    A quiet day still records the date, so an empty digest is not rebuilt on every 10 s tick; a
    failed send does not, so the next tick tries again.
    """
    s = settings_store.load()
    if not s.telegram_linked:
        return False
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(_zone(s.timezone))
    today = local.date().isoformat()
    if s.telegram_daily_last_sent == today:
        return False
    if (local.hour, local.minute) < _daily_time(s.telegram_daily_time):
        return False
    # Past the send time and today's digest still owed: the once-a-day housekeeping slot.
    purged = purge_sent_notifications(db, now)
    if purged:
        log.info("deleted %d notification(s) sent more than %d days ago", purged, RETENTION_DAYS)
    text = build_daily_digest(db, s, now=now)
    if text is None:
        settings_store.set_telegram(daily_last_sent=today)
        return False
    try:
        with client_factory(s.telegram_bot_token) as client:
            client.send_message(s.telegram_chat_id, text)
    except Exception as e:  # noqa: BLE001 - a bad gateway's HTML body fails to decode, too
        log.warning("daily digest not delivered: %s", e)
        return False
    settings_store.set_telegram(daily_last_sent=today)
    return True

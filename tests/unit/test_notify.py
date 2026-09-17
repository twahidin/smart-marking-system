"""The notification outbox: hand-in and marking-finished rows, the batched Telegram flush and the
daily digest. Web fixtures because the seeding goes through the API (`app` builds the schema)."""
import json
from datetime import datetime, timedelta, timezone

import httpx

from sms.web.services.class_assignments import remove_hand_in
from sms.web.services.insights import dedupe_key
from sms.web.services.notify import (
    MAX_ATTEMPTS,
    _student,
    flush_notifications,
    maybe_send_daily,
    on_mark_settled,
    purge_sent_notifications,
    record_hand_in,
)
from sms.web.services.telegram import TelegramClient

from tests.web.conftest import app, auth, client, config  # noqa: F401 - fixtures
from tests.web.seed_v2 import seed_v2
from tests.web.test_class_assignments_api import _class_with_students, _link, _template
from tests.web.test_student_api import _png, _setup

APP_URL = "https://sms.example"


def _settings(app, *, instant=True, daily_time="07:00", tz="Asia/Singapore", link=True):
    """Store a bot token (and optionally the linked chat) plus the app URL behind the links."""
    store = app.state.settings_store
    s = store.load()
    s.telegram_bot_token = "1:abc"
    s.telegram_instant = instant
    s.telegram_daily_time = daily_time
    s.timezone = tz
    s.app_url = APP_URL
    store.save(s)
    if link:
        store.set_telegram(chat_id="7")
    return store


def _factory(sent, status=200):
    """A TelegramClient factory whose transport records every sendMessage body."""
    def handler(req):
        body = json.loads(req.content or b"{}")
        sent.append(body)
        if status != 200:
            return httpx.Response(status, json={"ok": False, "description": "chat not found"})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent)}})

    return lambda token: TelegramClient(token, transport=httpx.MockTransport(handler))


def _notifications(app, kind=None):
    sql = "SELECT * FROM notifications"
    params = {}
    if kind is not None:
        sql += " WHERE kind = :k"
        params["k"] = kind
    return app.state.db.query(sql + " ORDER BY id", params)


def _open_assignment(auth, app, names=("Tan Wei Ling", "Muhammad Danish")):
    """A template, a class with students and one open class assignment."""
    t = _template(auth)
    c = _class_with_students(auth, names=names)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
             json={"title": ca["title"], "due_at": None, "allow_student_uploads": True, "status": "open"})
    return t, c, ca


def test_hand_in_rows_are_batched_into_one_message(auth, client, app):
    t, c, ca, _draft = _setup(auth)
    _settings(app)
    for reg_no in (1, 2):
        client.cookies.clear()
        client.post("/api/student/session", json={"code": c["code"], "reg_no": reg_no})
        r = client.post(f"/api/student/assignments/{ca['id']}/hand-in",
                        files=[("files", ("p1.png", _png(), "image/png"))])
        assert r.status_code == 202
    rows = _notifications(app, "hand_in")
    assert len(rows) == 2 and all(r["class_assignment_id"] == ca["id"] and r["sent_at"] is None for r in rows)

    sent = []
    assert flush_notifications(app.state.settings_store, app.state.db, client_factory=_factory(sent)) == 1
    assert len(sent) == 1
    text = sent[0]["text"]
    assert sent[0]["chat_id"] == "7"
    assert "2 new hand-ins" in text
    assert "Tan Wei Ling" in text and "Muhammad Danish" in text
    assert f"{APP_URL}/classes/{c['id']}/assignments/{ca['id']}" in text
    assert all(r["sent_at"] is not None and r["error"] is None for r in _notifications(app, "hand_in"))
    # nothing left to send
    assert flush_notifications(app.state.settings_store, app.state.db, client_factory=_factory(sent)) == 0


def test_removing_a_hand_in_drops_its_unsent_announcement(auth, client, app):
    """Undoing a hand-in before the flush ran should not still buzz the teacher about a script that
    no longer exists — but only that student's row goes, and only while it is unsent."""
    t, c, ca, _draft = _setup(auth)
    _settings(app)
    for reg_no in (1, 2):
        client.cookies.clear()
        client.post("/api/student/session", json={"code": c["code"], "reg_no": reg_no})
        assert client.post(f"/api/student/assignments/{ca['id']}/hand-in",
                           files=[("files", ("p1.png", _png(), "image/png"))]).status_code == 202
    tan, danish = c["students"]
    assert len(_notifications(app, "hand_in")) == 2

    remove_hand_in(app.state.db, app.state.storage, ca["id"], tan["id"])
    left = _notifications(app, "hand_in")
    assert [json.loads(r["payload_json"])["student_id"] for r in left] == [danish["id"]]

    # a row that has already gone out is history, not a pending buzz: it stays
    sent = []
    assert flush_notifications(app.state.settings_store, app.state.db, client_factory=_factory(sent)) == 1
    remove_hand_in(app.state.db, app.state.storage, ca["id"], danish["id"])
    assert [r["id"] for r in _notifications(app, "hand_in")] == [left[0]["id"]]


def test_marking_done_fires_once_per_drain(auth, app):
    t, c, ca = _open_assignment(auth, app)
    _settings(app)
    tan, danish = c["students"]
    sid, _ = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    _link(app, sid, ca["id"], tan["id"])
    db, jobs = app.state.db, app.state.jobs

    on_mark_settled(db, jobs, sid)
    on_mark_settled(db, jobs, sid)
    rows = _notifications(app, "marking_done")
    assert len(rows) == 1 and rows[0]["class_assignment_id"] == ca["id"]
    payload = json.loads(rows[0]["payload_json"])
    assert payload["marked"] == 1 and payload["needs_you"] == 0 and payload["insights"] is True
    insights_jobs = db.query("SELECT * FROM jobs WHERE kind = 'insights'")
    assert len(insights_jobs) == 1 and insights_jobs[0]["dedupe_key"] == dedupe_key(ca["id"])
    assert db.query("SELECT last_done_notified_at FROM class_assignments WHERE id = :a",
                    {"a": ca["id"]})[0]["last_done_notified_at"] is not None

    # a new hand-in re-arms the guard, so the next drain notifies again
    record_hand_in(db, {"class_assignment_id": ca["id"], "student_id": danish["id"], "source": "student"})
    assert db.query("SELECT last_done_notified_at FROM class_assignments WHERE id = :a",
                    {"a": ca["id"]})[0]["last_done_notified_at"] is None
    on_mark_settled(db, jobs, sid)
    assert len(_notifications(app, "marking_done")) == 2


def test_the_drain_guard_is_claimed_atomically(auth, app):
    """Both of the last two scripts settle with nothing in flight, so both callers get past the
    counts and race for the guard. Claiming it is the same statement that stamps it, so only the
    caller whose UPDATE matched — rowcount 1 — writes the message."""
    t, c, ca = _open_assignment(auth, app)
    _settings(app)
    tan, danish = c["students"]
    first, _ = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    second, _ = seed_v2(app, label="#2 Muhammad Danish", assignment_id=t["id"], run_id="r-dan", queue={})
    _link(app, first, ca["id"], tan["id"])
    _link(app, second, ca["id"], danish["id"])
    db, jobs = app.state.db, app.state.jobs

    on_mark_settled(db, jobs, first)
    on_mark_settled(db, jobs, second)
    assert len(_notifications(app, "marking_done")) == 1


def test_a_hand_in_with_no_nameable_student_is_skipped(auth, app):
    """`reg_no` is NOT NULL in the schema, so this cannot normally happen — but a row that slipped
    through must skip the announcement, not blow up the hand-in with a TypeError."""
    t, c, ca = _open_assignment(auth, app)
    _settings(app)
    tan = c["students"][0]
    db = app.state.db
    assert record_hand_in(db, {"class_assignment_id": ca["id"], "student_id": None, "source": "student"}) is None
    assert record_hand_in(db, {"class_assignment_id": ca["id"], "student_id": 9999, "source": "student"}) is None
    assert _notifications(app, "hand_in") == []

    # the column is NOT NULL, so a NULL register number can only be forced from outside the schema
    class NullRegNo:
        def query(self, *_a, **_k):
            return [{"id": tan["id"], "reg_no": None, "name": "Tan Wei Ling"}]

    assert _student(NullRegNo(), tan["id"]) is None


def test_marking_done_waits_for_in_flight_siblings(auth, app):
    t, c, ca = _open_assignment(auth, app)
    _settings(app)
    tan, danish = c["students"]
    sid, _ = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    other, _ = seed_v2(app, label="#2 Muhammad Danish", assignment_id=t["id"], run_id="r-dan",
                       queue={}, status="marking")
    _link(app, sid, ca["id"], tan["id"])
    _link(app, other, ca["id"], danish["id"])

    on_mark_settled(app.state.db, app.state.jobs, sid)
    assert _notifications(app, "marking_done") == []
    assert app.state.db.query("SELECT * FROM jobs WHERE kind = 'insights'") == []


def test_instant_off_suppresses_events(auth, app):
    t, c, ca = _open_assignment(auth, app)
    _settings(app, instant=False)
    tan, danish = c["students"]
    sid, _ = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    _link(app, sid, ca["id"], tan["id"])
    db, jobs = app.state.db, app.state.jobs

    record_hand_in(db, {"class_assignment_id": ca["id"], "student_id": danish["id"], "source": "student"})
    on_mark_settled(db, jobs, sid)
    assert _notifications(app) == []
    # the report is not a notification: it is still generated
    assert len(db.query("SELECT * FROM jobs WHERE kind = 'insights'")) == 1


def test_daily_digest_once_per_day_and_skips_quiet_days(auth, app):
    t, c, ca = _open_assignment(auth, app)
    store = _settings(app)
    tan, danish = c["students"]
    db = app.state.db
    sid, _ = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    other, _ = seed_v2(app, label="#2 Muhammad Danish", assignment_id=t["id"], run_id="r-dan", queue={"2": "unsure"})
    for s in (sid, other):
        _link(app, s, ca["id"], tan["id"] if s == sid else danish["id"], handed_in="2026-09-16 10:00:00")
    db.execute("UPDATE marking_runs SET created_at = '2026-09-16 10:05:00'")

    sent = []
    # 06:59 local (Asia/Singapore is UTC+8, no DST) — before the 07:00 send time
    assert maybe_send_daily(store, db, now=datetime(2026, 9, 16, 22, 59, tzinfo=timezone.utc),
                            client_factory=_factory(sent)) is False
    assert sent == [] and store.load().telegram_daily_last_sent is None

    # 07:01 local, with the day's activity in the window
    assert maybe_send_daily(store, db, now=datetime(2026, 9, 16, 23, 1, tzinfo=timezone.utc),
                            client_factory=_factory(sent)) is True
    assert len(sent) == 1
    text = sent[0]["text"]
    assert "4E2" in text and ca["title"] in text
    assert "2 handed in" in text and "2 marked" in text and "1 need you" in text
    assert store.load().telegram_daily_last_sent == "2026-09-17"

    # once a day
    assert maybe_send_daily(store, db, now=datetime(2026, 9, 16, 23, 30, tzinfo=timezone.utc),
                            client_factory=_factory(sent)) is False
    assert len(sent) == 1

    # the next day, with the activity now outside the 24 h window: nothing is sent
    assert maybe_send_daily(store, db, now=datetime(2026, 9, 17, 23, 1, tzinfo=timezone.utc),
                            client_factory=_factory(sent)) is False
    assert len(sent) == 1
    assert store.load().telegram_daily_last_sent == "2026-09-18"


def test_failed_send_keeps_row_with_error_and_backs_off(auth, app):
    t, c, ca = _open_assignment(auth, app)
    _settings(app)
    tan = c["students"][0]
    db = app.state.db
    record_hand_in(db, {"class_assignment_id": ca["id"], "student_id": tan["id"], "source": "student"})

    failed = []
    t0 = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)
    assert flush_notifications(app.state.settings_store, db, client_factory=_factory(failed, status=400),
                               now=t0) == 0
    row = _notifications(app, "hand_in")[0]
    assert row["sent_at"] is None and "chat not found" in row["error"]
    assert row["attempts"] == 1 and row["next_attempt_at"] == "2026-09-17 09:00:20"

    # the row is not even looked at before its next-attempt time
    def no_client(token):
        raise AssertionError("nothing is due, so no client should be built")

    assert flush_notifications(app.state.settings_store, db, client_factory=no_client,
                               now=t0 + timedelta(seconds=10)) == 0

    sent = []
    assert flush_notifications(app.state.settings_store, db, client_factory=_factory(sent),
                               now=t0 + timedelta(seconds=20)) == 1
    row = _notifications(app, "hand_in")[0]
    assert row["sent_at"] is not None and row["error"] is None


def test_backoff_doubles_to_an_hour_then_the_row_is_abandoned(auth, app, caplog):
    """10 s doubling per attempt, capped at an hour; after MAX_ATTEMPTS refusals the row is stamped
    sent — the error kept — so an unreachable chat stops costing a request every tick."""
    t, c, ca = _open_assignment(auth, app)
    _settings(app)
    tan = c["students"][0]
    db = app.state.db
    record_hand_in(db, {"class_assignment_id": ca["id"], "student_id": tan["id"], "source": "student"})

    now = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)
    delays = []
    for _ in range(MAX_ATTEMPTS - 1):
        assert flush_notifications(app.state.settings_store, db, client_factory=_factory([], status=400),
                                   now=now) == 0
        row = _notifications(app, "hand_in")[0]
        nxt = datetime.strptime(row["next_attempt_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        delays.append(int((nxt - now).total_seconds()))
        now = nxt
    assert delays[:4] == [20, 40, 80, 160]
    assert delays[-1] == 3600 and max(delays) == 3600      # capped, never longer than an hour
    row = _notifications(app, "hand_in")[0]
    assert row["attempts"] == MAX_ATTEMPTS - 1 and row["sent_at"] is None

    with caplog.at_level("WARNING", logger="sms.notify"):
        assert flush_notifications(app.state.settings_store, db, client_factory=_factory([], status=400),
                                   now=now) == 0
    row = _notifications(app, "hand_in")[0]
    assert row["attempts"] == MAX_ATTEMPTS
    assert row["sent_at"] is not None and "chat not found" in row["error"]   # stopped, reason kept
    assert any("abandoned" in r.getMessage() for r in caplog.records)


def test_a_non_json_gateway_body_is_recorded_and_the_other_groups_still_go(auth, app):
    """A 502 from a proxy answers HTML, so decoding the body raises where Telegram's own errors do
    not — the group must record it and the flush must carry on with the rest."""
    t, c, ca = _open_assignment(auth, app)
    other = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    _settings(app)
    tan, danish = c["students"]
    db = app.state.db
    record_hand_in(db, {"class_assignment_id": ca["id"], "student_id": tan["id"], "source": "student"})
    record_hand_in(db, {"class_assignment_id": other["id"], "student_id": danish["id"], "source": "student"})

    ok = []

    # Both assignments carry the same title, so the gateway failure is routed on the link.
    def handler(req):
        body = json.loads(req.content or b"{}")
        if f"/assignments/{ca['id']}" in body["text"]:
            return httpx.Response(502, headers={"content-type": "text/html"},
                                  text="<html><body>502 Bad Gateway</body></html>")
        ok.append(body)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    sent = flush_notifications(app.state.settings_store, db,
                               client_factory=lambda token: TelegramClient(token, transport=httpx.MockTransport(handler)),
                               now=datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc))
    assert sent == 1 and len(ok) == 1                      # the healthy group still went out
    rows = {r["class_assignment_id"]: r for r in _notifications(app, "hand_in")}
    bad = rows[ca["id"]]
    assert bad["sent_at"] is None and bad["error"] and bad["attempts"] == 1
    assert bad["next_attempt_at"] == "2026-09-17 09:00:20"
    assert rows[other["id"]]["sent_at"] is not None


def test_a_flush_sends_at_most_ten_messages(auth, app):
    """A backlog drains over ticks rather than firing every message at the Bot API at once."""
    t, c, ca = _open_assignment(auth, app)
    _settings(app)
    tan = c["students"][0]
    db = app.state.db
    cas = [ca] + [auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
                  for _ in range(11)]
    for one in cas:
        record_hand_in(db, {"class_assignment_id": one["id"], "student_id": tan["id"], "source": "student"})
    assert len(_notifications(app, "hand_in")) == 12

    sent = []
    assert flush_notifications(app.state.settings_store, db, client_factory=_factory(sent)) == 10
    assert len(_notifications(app, "hand_in")) == 12
    assert sum(1 for r in _notifications(app, "hand_in") if r["sent_at"] is None) == 2
    assert flush_notifications(app.state.settings_store, db, client_factory=_factory(sent)) == 2
    assert all(r["sent_at"] is not None for r in _notifications(app, "hand_in"))


def test_the_daily_tick_deletes_sent_rows_older_than_a_month(auth, app):
    t, c, ca = _open_assignment(auth, app)
    store = _settings(app)
    tan = c["students"][0]
    db = app.state.db
    for _ in range(3):
        record_hand_in(db, {"class_assignment_id": ca["id"], "student_id": tan["id"], "source": "student"})
    ids = [r["id"] for r in _notifications(app, "hand_in")]
    db.execute("UPDATE notifications SET sent_at = '2026-08-01 09:00:00' WHERE id = :i", {"i": ids[0]})
    db.execute("UPDATE notifications SET sent_at = '2026-09-16 09:00:00' WHERE id = :i", {"i": ids[1]})
    # ids[2] is still unsent, however old it is
    db.execute("UPDATE notifications SET created_at = '2026-01-01 09:00:00' WHERE id = :i", {"i": ids[2]})

    now = datetime(2026, 9, 17, 23, 1, tzinfo=timezone.utc)   # 07:01 local, past the send time
    assert purge_sent_notifications(db, now) == 1
    assert [r["id"] for r in _notifications(app, "hand_in")] == ids[1:]

    # and the daily tick does it for us
    db.execute("UPDATE notifications SET sent_at = '2026-08-02 09:00:00' WHERE id = :i", {"i": ids[1]})
    maybe_send_daily(store, db, now=now, client_factory=_factory([]))
    assert [r["id"] for r in _notifications(app, "hand_in")] == [ids[2]]


def test_the_daily_digest_survives_a_non_json_gateway_body(auth, app):
    t, c, ca = _open_assignment(auth, app)
    store = _settings(app)
    tan, danish = c["students"]
    db = app.state.db
    sid, _ = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    _link(app, sid, ca["id"], tan["id"], handed_in="2026-09-16 10:00:00")
    db.execute("UPDATE marking_runs SET created_at = '2026-09-16 10:05:00'")

    def handler(_req):
        return httpx.Response(502, headers={"content-type": "text/html"}, text="<html>502</html>")

    now = datetime(2026, 9, 16, 23, 1, tzinfo=timezone.utc)
    assert maybe_send_daily(store, db, now=now,
                            client_factory=lambda tok: TelegramClient(tok, transport=httpx.MockTransport(handler))) is False
    assert store.load().telegram_daily_last_sent is None      # not recorded, so the next tick retries

    sent = []
    assert maybe_send_daily(store, db, now=now, client_factory=_factory(sent)) is True
    assert len(sent) == 1


def test_flush_is_a_no_op_until_the_chat_is_linked(auth, app):
    t, c, ca = _open_assignment(auth, app)
    _settings(app, link=False)
    tan = c["students"][0]
    record_hand_in(app.state.db, {"class_assignment_id": ca["id"], "student_id": tan["id"], "source": "student"})

    def factory(token):
        raise AssertionError("no chat linked, so no client should be built")

    assert flush_notifications(app.state.settings_store, app.state.db, client_factory=factory) == 0
    assert _notifications(app, "hand_in")[0]["sent_at"] is None


def test_messages_escape_names_and_omit_links_without_an_app_url(auth, app, monkeypatch):
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)
    t, c, ca = _open_assignment(auth, app, names=("Tan <b>Wei</b> Ling", "Danish & Co"))
    store = _settings(app)
    s = store.load()
    s.app_url = ""
    store.save(s)
    tan, danish = c["students"]
    db = app.state.db
    for st in (tan, danish):
        record_hand_in(db, {"class_assignment_id": ca["id"], "student_id": st["id"], "source": "student"})

    sent = []
    assert flush_notifications(store, db, client_factory=_factory(sent)) == 1
    text = sent[0]["text"]
    assert "Tan &lt;b&gt;Wei&lt;/b&gt; Ling" in text and "Danish &amp; Co" in text
    assert "<a href=" not in text


def test_teacher_uploads_make_no_hand_in_row_but_re_arm_the_guard(auth, app):
    t, c, ca = _open_assignment(auth, app)
    _settings(app)
    tan = c["students"][0]
    db = app.state.db
    db.execute("UPDATE class_assignments SET last_done_notified_at = CURRENT_TIMESTAMP WHERE id = :a", {"a": ca["id"]})
    record_hand_in(db, {"class_assignment_id": ca["id"], "student_id": tan["id"], "source": "teacher"})
    assert _notifications(app, "hand_in") == []
    assert db.query("SELECT last_done_notified_at FROM class_assignments WHERE id = :a",
                    {"a": ca["id"]})[0]["last_done_notified_at"] is None

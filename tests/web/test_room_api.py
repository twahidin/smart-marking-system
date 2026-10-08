from tests.web.seed_v2 import seed_v2


def _event(app, sid, stage, kind, q_id=None, note=None):
    app.state.db.execute("INSERT INTO marking_events (submission_id, stage, kind, q_id, note) VALUES (:s, :st, :k, :q, :n)",
                         {"s": sid, "st": stage, "k": kind, "q": q_id, "n": note})
    if kind == "started":
        app.state.db.execute("UPDATE submissions SET stage = :st, status = 'marking' WHERE id = :s", {"st": stage, "s": sid})


def test_snapshot_counts_and_desks(auth, app):
    a, _ = seed_v2(app, label="Done one", run_id="r-a", queue={})
    b, _ = seed_v2(app, label="On the marker", run_id="r-b", queue={})
    _event(app, b, "read", "started"); _event(app, b, "read", "finished"); _event(app, b, "mark", "started")
    snap = auth.get("/api/room").json()
    assert snap["counts"]["done"] == 1 and snap["counts"]["mark"] == 1
    assert [d["submission_id"] for d in snap["desks"]] == [b]
    assert snap["desks"][0]["stage"] == "mark" and snap["desks"][0]["label"] == "On the marker"
    assert snap["last_event_id"] >= 3


def test_events_stream_once_returns_new_events_then_closes(auth, app):
    sid, _ = seed_v2(app, run_id="r-c", queue={})
    _event(app, sid, "read", "started")
    with auth.stream("GET", "/api/room/events?after=0&once=1") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert "event: stage" in body and '"stage": "read"' in body and "id: " in body


def test_thoughts_are_grouped_by_crew_and_teacher_only(auth, client, app):
    sid, _ = seed_v2(app, run_id="r-d", queue={})
    _event(app, sid, "read", "note", "1b", "Hard to read")
    _event(app, sid, "mark", "note", "1a", "M1 for the method")
    _event(app, sid, "check", "note", "1a", "APPROVE: Agree")
    _event(app, sid, "done", "note", "1b", "illegible transcription")
    t = auth.get(f"/api/submissions/{sid}/thoughts").json()
    assert [x["note"] for x in t["reader"]] == ["Hard to read"]
    assert [x["note"] for x in t["marker"]] == ["M1 for the method"]
    assert [x["note"] for x in t["checker"]] == ["APPROVE: Agree", "illegible transcription"]
    assert auth.get("/api/submissions/999999/thoughts").status_code == 404
    client.cookies.clear()  # `auth` and `client` are the same session, so sign out last
    assert client.get(f"/api/submissions/{sid}/thoughts").status_code in (401, 404)


def test_snapshot_failed_is_never_a_desk_and_events_exclude_notes(auth, app):
    f, _ = seed_v2(app, label="Broke", run_id="r-f", queue={}, status="failed")
    _event(app, f, "mark", "started")
    app.state.db.execute("UPDATE submissions SET status = 'failed' WHERE id = :s", {"s": f})
    _event(app, f, "mark", "note", "1a", "thinking")
    snap = auth.get("/api/room").json()
    assert snap["counts"]["failed"] == 1 and snap["counts"]["mark"] == 0 and snap["desks"] == []
    with auth.stream("GET", "/api/room/events?after=0&once=1") as r:
        body = "".join(r.iter_text())
    assert "thinking" not in body and body.count("event: stage") == 1


def test_events_once_with_no_events_returns_empty(auth):
    with auth.stream("GET", "/api/room/events?once=1") as r:
        assert r.status_code == 200 and "".join(r.iter_text()) == ""


def test_events_resume_from_last_event_id_header(auth, app):
    sid, _ = seed_v2(app, run_id="r-g", queue={})
    _event(app, sid, "read", "started"); _event(app, sid, "read", "finished")
    first = app.state.db.query("SELECT MIN(id) AS i FROM marking_events")[0]["i"]
    with auth.stream("GET", "/api/room/events?once=1", headers={"Last-Event-ID": str(first)}) as r:
        body = "".join(r.iter_text())
    assert body.count("event: stage") == 1 and '"kind": "finished"' in body


def test_desk_since_is_the_latest_started_event(auth, app):
    sid, _ = seed_v2(app, label="Slow", run_id="r-h", queue={})
    _event(app, sid, "read", "started"); _event(app, sid, "read", "finished"); _event(app, sid, "mark", "started")
    first, second = [r["id"] for r in app.state.db.query(
        "SELECT id FROM marking_events WHERE kind = 'started' ORDER BY id")]
    app.state.db.execute("UPDATE marking_events SET created_at = '2026-03-01 09:00:00' WHERE id = :i", {"i": first})
    app.state.db.execute("UPDATE marking_events SET created_at = '2026-03-01 09:05:00' WHERE id = :i", {"i": second})
    app.state.db.execute("UPDATE submissions SET updated_at = '2026-03-01 08:00:00' WHERE id = :s", {"s": sid})
    desk = auth.get("/api/room").json()["desks"][0]
    assert desk["since"] == "2026-03-01T09:05:00Z"


def test_desk_since_falls_back_to_updated_at_without_a_started_event(auth, app):
    sid, _ = seed_v2(app, label="Odd", run_id="r-i", queue={}, status="marking")
    app.state.db.execute("UPDATE submissions SET stage = 'check', updated_at = '2026-03-02 10:00:00' WHERE id = :s", {"s": sid})
    desk = auth.get("/api/room").json()["desks"][0]
    assert desk["stage"] == "check" and desk["since"] == "2026-03-02T10:00:00Z"


def test_started_at_is_the_oldest_live_script_not_the_oldest_ever(auth, app):
    old, _ = seed_v2(app, label="Old done", run_id="r-j", queue={})
    live, _ = seed_v2(app, label="Live", run_id="r-k", queue={}, status="marking")
    app.state.db.execute("UPDATE submissions SET created_at = '2026-01-01 08:00:00' WHERE id = :s", {"s": old})
    app.state.db.execute("UPDATE submissions SET created_at = '2026-03-05 08:30:00' WHERE id = :s", {"s": live})
    assert auth.get("/api/room").json()["started_at"] == "2026-03-05T08:30:00Z"
    app.state.db.execute("UPDATE submissions SET status = 'done' WHERE id = :s", {"s": live})
    assert auth.get("/api/room").json()["started_at"] is None

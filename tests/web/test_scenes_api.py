from datetime import datetime, timedelta, timezone

from tests.web.seed_v2 import seed_v2


def _template(auth):
    return auth.post("/api/assignments", json={
        "title": "Paper", "subject": "math", "context": "",
        "rubric": {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]},
        "scheme_kind": "mark_scheme", "questions": [{"q_id": "1a", "text": "Solve 3x = 9", "max_marks": 2}],
        "scheme": [{"q_id": "1a", "answer": "x = 3", "marks": [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 1}], "notes": ""}]}).json()


def _open_set(auth, cid, tid, due=None):
    ca = auth.post(f"/api/classes/{cid}/assignments", json={"template_id": tid, "due_at": due}).json()
    auth.put(f"/api/classes/{cid}/assignments/{ca['id']}", json={"title": ca["title"], "due_at": due, "allow_student_uploads": True, "status": "open"})
    return ca


def test_requires_auth(client):
    assert client.get("/api/review/summary").status_code == 401
    assert client.get("/api/class-assignments/due").status_code == 401


def test_review_summary_counts_queue_remarked_and_ready_sets(auth, app):
    t = _template(auth)
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    ready = _open_set(auth, c["id"], t["id"]); busy = _open_set(auth, c["id"], t["id"]); empty = _open_set(auth, c["id"], t["id"])
    done, _ = seed_v2(app, run_id="r-d", queue={})
    flagged, _ = seed_v2(app, run_id="r-f", queue={"1a": "low_confidence"})
    db = app.state.db
    db.execute("UPDATE submissions SET class_assignment_id = :ca WHERE id = :i", {"ca": ready["id"], "i": done})
    db.execute("UPDATE submissions SET class_assignment_id = :ca, status = 'needs_you' WHERE id = :i", {"ca": busy["id"], "i": flagged})
    db.execute("INSERT INTO student_corrections (submission_id, q_id, reason, text, status) VALUES (:s, '1b', 'sign', 'x', 'remarked')", {"s": done})
    db.execute("INSERT INTO student_corrections (submission_id, q_id, reason, text, status) VALUES (:s, '2', 'sign', 'y', 'released')", {"s": done})
    s = auth.get("/api/review/summary").json()
    assert s["needs_you"] == 1 and s["remarked"] == 1 and s["ready_to_release"] == 1
    assert [x["id"] for x in s["ready_sets"]] == [ready["id"]] and s["ready_sets"][0]["class_name"] == "4E2"
    assert empty["id"] not in [x["id"] for x in s["ready_sets"]]   # nothing handed in yet


def test_due_list_is_open_sets_inside_the_window_soonest_first(auth):
    t = _template(auth)
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    soon = _open_set(auth, c["id"], t["id"], iso(now + timedelta(days=2)))
    later = _open_set(auth, c["id"], t["id"], iso(now + timedelta(days=1)))
    far = _open_set(auth, c["id"], t["id"], iso(now + timedelta(days=20)))
    past = _open_set(auth, c["id"], t["id"], iso(now - timedelta(days=1)))
    nodue = _open_set(auth, c["id"], t["id"])
    draft = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "due_at": iso(now + timedelta(days=1))}).json()
    rows = auth.get("/api/class-assignments/due?days=7").json()
    assert [r["id"] for r in rows] == [later["id"], soon["id"]]
    assert rows[0]["class_name"] == "4E2" and rows[0]["status"] == "open" and rows[0]["due_at"].endswith("Z")
    assert auth.get("/api/class-assignments/due?days=30").json()[-1]["id"] == far["id"]
    assert {past["id"], nodue["id"], draft["id"]}.isdisjoint({r["id"] for r in rows})


def test_due_window_reads_stored_utc_text_on_a_non_utc_host(auth, monkeypatch):
    import time
    monkeypatch.setenv("TZ", "Asia/Singapore")
    time.tzset()
    try:
        t = _template(auth)
        c = auth.post("/api/classes", json={"name": "4E2"}).json()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
        ahead = _open_set(auth, c["id"], t["id"], iso(now + timedelta(hours=2)))
        behind = _open_set(auth, c["id"], t["id"], iso(now - timedelta(hours=2)))
        ids = [r["id"] for r in auth.get("/api/class-assignments/due?days=1").json()]
        assert ids == [ahead["id"]] and behind["id"] not in ids
    finally:
        monkeypatch.undo()
        time.tzset()

import io

from PIL import Image

from tests.web.seed_v2 import QUESTIONS, SCHEME, seed_v2

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]}


def _class(auth, names=("Tan Wei Ling", "Muhammad Danish")):
    c = auth.post("/api/classes", json={"name": "4E2 Mathematics"}).json()
    auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": i + 1, "name": n} for i, n in enumerate(names)]})
    c["students"] = auth.get(f"/api/classes/{c['id']}/students").json()
    return c


def test_lookup_and_session(auth, client):
    c = _class(auth)
    client.cookies.clear()      # no teacher cookie from here on
    r = client.post("/api/student/lookup", json={"code": c["code"].lower(), "reg_no": 1})
    assert r.status_code == 200 and r.json() == {"class_name": "4E2 Mathematics", "code": c["code"], "student_name": "Tan Wei Ling", "reg_no": 1}
    r = client.post("/api/student/lookup", json={"code": c["code"], "reg_no": 37})
    assert r.status_code == 404 and r.json()["error"] == {"code": "no_such_student", "message": "No student #37 in this class — check the number on your class list"}
    r = client.post("/api/student/lookup", json={"code": "ZZZZ", "reg_no": 1})
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_such_class"
    assert client.get("/api/student/me").status_code == 401
    assert client.post("/api/student/session", json={"code": c["code"], "reg_no": 1}).status_code == 204
    assert "sms_student" in client.cookies
    assert client.get("/api/student/me").json() == {"class_name": "4E2 Mathematics", "code": c["code"], "student_name": "Tan Wei Ling", "reg_no": 1}
    # the student cookie opens nothing teacher-only
    assert client.get("/api/classes").status_code == 401
    assert client.delete("/api/student/session").status_code == 204
    assert client.get("/api/student/me").status_code == 401


def test_teacher_cookie_is_not_a_student_session(auth):
    assert auth.get("/api/student/me").status_code == 401


def test_archived_class_is_invisible_and_kills_sessions(auth, client):
    c = _class(auth)
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    auth.post(f"/api/classes/{c['id']}/archive")
    assert client.post("/api/student/lookup", json={"code": c["code"], "reg_no": 1}).json()["error"]["code"] == "no_such_class"
    assert client.get("/api/student/me").status_code == 401


def test_lookup_failures_are_rate_limited(auth, client):
    c = _class(auth)
    client.cookies.clear()
    for _ in range(5):
        client.post("/api/student/lookup", json={"code": c["code"], "reg_no": 99})
    assert client.post("/api/student/lookup", json={"code": c["code"], "reg_no": 1}).status_code == 429


def test_session_updates_last_seen(auth, client):
    c = _class(auth)
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 2})
    client.cookies.clear()
    r = auth.post("/api/auth/login", json={"password": "letmein"})
    assert auth.get(f"/api/classes/{c['id']}/students").json()[1]["last_seen_at"] is not None


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def _setup(auth):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x", "rpm_limit": 60, "confidence_threshold": 0})
    t = auth.post("/api/assignments", json={"title": "Worksheet 3", "subject": "math", "context": "", "rubric": RUBRIC,
                                            "scheme_kind": "mark_scheme", "questions": QUESTIONS, "scheme": SCHEME}).json()
    c = _class(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "due_at": "2026-09-30T08:00:00Z"}).json()
    draft = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "title": "Hidden draft"}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={"title": ca["title"], "due_at": ca["due_at"], "allow_student_uploads": True, "status": "open"})
    return t, c, ca, draft


def test_student_sees_open_assignments_and_hands_in_once(auth, client, app):
    t, c, ca, draft = _setup(auth)
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    lst = client.get("/api/student/assignments").json()
    assert [(a["id"], a["title"], a["status"]) for a in lst] == [(ca["id"], "Worksheet 3", "to_hand_in")]
    assert client.get(f"/api/student/assignments/{draft['id']}").status_code == 404
    r = client.post(f"/api/student/assignments/{ca['id']}/hand-in", files=[("files", ("p1.png", _png(), "image/png")), ("files", ("p2.png", _png(), "image/png"))])
    assert r.status_code == 202
    sid = r.json()["id"]
    row = app.state.db.query("SELECT * FROM submissions WHERE id = :s", {"s": sid})[0]
    assert row["source"] == "student" and row["student_id"] == c["students"][0]["id"] and row["label"] == "#1 Tan Wei Ling"
    assert client.post(f"/api/student/assignments/{ca['id']}/hand-in", files=[("files", ("p1.png", _png(), "image/png"))]).json()["error"]["code"] == "already_handed_in"
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["status"] == "handed_in" and got["handed_in_at"] is not None and got["pages"] == 2 and got["feedback"] is None
    # the teacher's roster shows the same
    auth.post("/api/auth/login", json={"password": "letmein"})
    roster = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["roster"]
    assert roster["rows"][0]["status"] == "handed_in" and roster["rows"][0]["source"] == "student"


def test_hand_in_refused_when_closed_or_not_open(auth, client):
    t, c, ca, draft = _setup(auth)
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={"title": "W", "due_at": None, "allow_student_uploads": False, "status": "open"})
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    r = client.post(f"/api/student/assignments/{ca['id']}/hand-in", files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 403 and r.json()["error"]["code"] == "uploads_closed"
    assert client.get("/api/student/assignments").json()[0]["allow_student_uploads"] is False


def test_feedback_hidden_until_release_then_complete_and_scoped(auth, client, app):
    t, c, ca, draft = _setup(auth)
    tan, danish = c["students"]
    sid, qids = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :a, student_id = :s, handed_in_at = CURRENT_TIMESTAMP, source = 'student' WHERE id = :id",
                         {"a": ca["id"], "s": tan["id"], "id": sid})
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["status"] == "checking" and got["feedback"] is None
    auth.post("/api/auth/login", json={"password": "letmein"})
    assert auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release").status_code == 200
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["status"] == "feedback_ready"
    fb = got["feedback"]
    assert fb["total"] == 3 and fb["max"] == 6 and fb["summary"] == "Good effort." and fb["strengths"] == ["method"]
    assert [(q["label"], q["mark"], q["max"]) for q in fb["questions"]] == [("1(a)", 2, 2), ("1(b)", 0, 1), ("2", 1, 3)]
    assert fb["questions"][0]["transcription"] == "x = 3" and fb["questions"][0]["comment"] == ""
    page_id = app.state.db.query("SELECT id FROM pages WHERE submission_id = :s", {"s": sid})[0]["id"]
    assert fb["pages"] == [page_id]
    text = str(got)
    for word in ("escalat", "confidence", "reviewer"):
        assert word not in text.lower()
    # another student cannot see Tan's page
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 2})
    assert client.get(f"/api/student/pages/{page_id}").status_code == 404
    assert client.get("/api/student/assignments").json()[0]["status"] == "to_hand_in"


def test_student_can_fetch_own_page_until_it_is_deleted(auth, client, app):
    t, c, ca, draft = _setup(auth)
    tan = c["students"][0]
    sid, _ = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :a, student_id = :s, handed_in_at = CURRENT_TIMESTAMP, source = 'student' WHERE id = :id",
                         {"a": ca["id"], "s": tan["id"], "id": sid})
    page = app.state.db.query("SELECT id, storage_path FROM pages WHERE submission_id = :s", {"s": sid})[0]
    app.state.storage.abs(page["storage_path"]).write_bytes(b"\xff\xd8jpeg-bytes")
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    r = client.get(f"/api/student/pages/{page['id']}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == b"\xff\xd8jpeg-bytes"
    assert client.get("/api/student/pages/999999").status_code == 404
    app.state.db.execute("UPDATE pages SET deleted_at = CURRENT_TIMESTAMP WHERE id = :p", {"p": page["id"]})
    assert client.get(f"/api/student/pages/{page['id']}").json()["error"]["code"] == "gone"

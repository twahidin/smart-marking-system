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

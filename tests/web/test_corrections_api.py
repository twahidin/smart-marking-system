from tests.web.seed_v2 import seed_v2
from tests.web.test_student_api import _setup


def _released_student(auth, client, app):
    t, c, ca, _ = _setup(auth)
    tan = c["students"][0]
    sid, _ = seed_v2(app, label="#1 Tan", assignment_id=t["id"], run_id="r-tan", queue={})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :a, student_id = :s, handed_in_at = CURRENT_TIMESTAMP, source = 'student' WHERE id = :id",
                         {"a": ca["id"], "s": tan["id"], "id": sid})
    assert auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release").status_code == 200
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    return c, ca, sid


def test_student_sees_reflection_and_sends_one_correction(auth, client, app):
    c, ca, sid = _released_student(auth, client, app)
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["reflection"]["days_left"] >= 6
    assert got["reflection"]["parts"]["1b"] == {"can_correct": True, "status": None, "new_mark": None}
    assert "1a" not in got["reflection"]["parts"]
    assert {q["q_id"] for q in got["feedback"]["questions"]} == {"1a", "1b", "2"}
    r = client.post(f"/api/student/assignments/{ca['id']}/corrections", data={"q_id": "1b", "reason": "sign", "text": "9"})
    assert r.status_code == 201 and r.json()["status"] == "submitted"
    r = client.post(f"/api/student/assignments/{ca['id']}/corrections", data={"q_id": "1b", "reason": "sign", "text": "again"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_corrected"
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["reflection"]["parts"]["1b"] == {"can_correct": False, "status": "sent", "new_mark": None}
    assert "remark_note" not in str(got) and "justification" not in str(got)


def test_teacher_reviews_and_releases(auth, client, app):
    c, ca, sid = _released_student(auth, client, app)
    cid = client.post(f"/api/student/assignments/{ca['id']}/corrections", data={"q_id": "1b", "reason": "sign", "text": "9"}).json()["id"]
    auth.post("/api/auth/login", json={"password": "letmein"})
    app.state.db.execute("UPDATE student_corrections SET status = 'remarked', remark_total = 1, remark_max = 1, remark_note = 'Marker: B1 earned' WHERE id = :id", {"id": cid})
    rows = auth.get(f"/api/review/corrections?class_assignment_id={ca['id']}").json()
    assert rows[0]["id"] == cid and rows[0]["reg_no"] == 1 and rows[0]["remark_note"] == "Marker: B1 earned"
    assert auth.post(f"/api/corrections/{cid}/override", json={"total": 0.5}).json()["teacher_total"] == 0.5
    assert auth.post(f"/api/class-assignments/{ca['id']}/release-corrections").json() == {"released": 1}
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["reflection"]["parts"]["1b"] == {"can_correct": False, "status": "released", "new_mark": 0.5}


def test_correction_routes_are_scoped(auth, client, app):
    c, ca, sid = _released_student(auth, client, app)
    assert client.get("/api/review/corrections?class_assignment_id=1").status_code in (401, 404)
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 2})
    r = client.post(f"/api/student/assignments/{ca['id']}/corrections", data={"q_id": "1b", "reason": "sign", "text": "9"})
    assert r.status_code == 404


def test_student_crop_is_only_the_students_own(auth, client, app):
    c, ca, sid = _released_student(auth, client, app)
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert all(q["crop_id"] is None or isinstance(q["crop_id"], int) for q in got["feedback"]["questions"])
    app.state.storage.root.mkdir(parents=True, exist_ok=True)
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buf, format="JPEG")
    digest, rel = app.state.storage.put_jpeg(buf.getvalue())
    cid = app.state.db.insert("INSERT INTO part_crops (submission_id, q_id, page_index, box_json, whole_page, storage_path, sha256, width, height) "
                              "VALUES (:s, '1b', 0, '[]', 1, :p, :d, 10, 10) RETURNING id", {"s": sid, "p": rel, "d": digest})
    r = client.get(f"/api/student/crops/{cid}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    app.state.db.execute("UPDATE part_crops SET deleted_at = CURRENT_TIMESTAMP WHERE id = :id", {"id": cid})
    assert client.get(f"/api/student/crops/{cid}").status_code == 404
    app.state.db.execute("UPDATE part_crops SET deleted_at = NULL WHERE id = :id", {"id": cid})
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 2})
    assert client.get(f"/api/student/crops/{cid}").status_code == 404

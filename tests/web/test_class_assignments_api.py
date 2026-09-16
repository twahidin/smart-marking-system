import io

from PIL import Image

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]}
SCHEME = [{"q_id": "1a", "answer": "x = 3", "marks": [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 1}], "notes": ""}]
QUESTIONS = [{"q_id": "1a", "text": "Solve 3x = 9", "max_marks": 2}]


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def _with_key(auth):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x", "rpm_limit": 60,
                                    "confidence_threshold": 0})


def _template(auth, **over):
    body = {"title": "Quadratics — Worksheet 3", "subject": "math", "context": "", "rubric": RUBRIC,
            "scheme_kind": "mark_scheme", "questions": QUESTIONS, "scheme": SCHEME}
    body.update(over)
    return auth.post("/api/assignments", json=body).json()


def _class_with_students(auth, names=("Tan Wei Ling", "Muhammad Danish")):
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": i + 1, "name": n} for i, n in enumerate(names)]})
    c["students"] = auth.get(f"/api/classes/{c['id']}/students").json()
    return c


def test_set_edit_open_and_delete_a_class_assignment(auth):
    t = _template(auth)
    c = _class_with_students(auth)
    r = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "due_at": "2026-09-30T08:00:00Z"})
    assert r.status_code == 201
    ca = r.json()
    assert ca["title"] == "Quadratics — Worksheet 3" and ca["status"] == "draft" and ca["derived_status"] == "draft"
    assert ca["due_at"] == "2026-09-30T08:00:00Z" and ca["allow_student_uploads"] is True and ca["template_deleted"] is False
    assert ca["subject"] == "math" and ca["scheme_kind"] == "mark_scheme" and ca["submission_count"] == 0
    assert auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": 999}).status_code == 404
    got = auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
                   json={"title": "Worksheet 3", "due_at": None, "allow_student_uploads": False, "status": "open"}).json()
    assert (got["title"], got["due_at"], got["allow_student_uploads"], got["status"]) == ("Worksheet 3", None, False, "open")
    assert auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
                    json={"title": "W", "due_at": None, "allow_student_uploads": True, "status": "bogus"}).json()["error"]["code"] == "bad_status"
    assert [a["id"] for a in auth.get(f"/api/classes/{c['id']}/assignments").json()] == [ca["id"]]
    assert auth.get(f"/api/classes/{c['id']}").json()["open_assignments"] == 1
    assert auth.delete(f"/api/classes/{c['id']}/assignments/{ca['id']}").status_code == 204
    assert auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").status_code == 404


def test_teacher_upload_for_a_student_creates_a_linked_submission(auth, app):
    _with_key(auth)
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    tan = c["students"][0]
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/upload",
                  files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 202
    sid = r.json()["id"]
    row = app.state.db.query("SELECT * FROM submissions WHERE id = :s", {"s": sid})[0]
    assert row["class_assignment_id"] == ca["id"] and row["student_id"] == tan["id"] and row["source"] == "teacher"
    assert row["assignment_id"] == t["id"] and row["label"] == "#1 Tan Wei Ling" and row["handed_in_at"] is not None
    assert row["scheme_kind"] == "mark_scheme"
    # once per student
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/upload",
                  files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_handed_in"
    assert auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["submission_count"] == 1
    assert auth.get("/api/submissions").json()[0]["class_label"] == "4E2 · #1"
    # cannot delete the class assignment while it has submissions
    assert auth.delete(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["error"]["code"] == "in_use"
    # remove the hand-in: submission, pages and job are gone; the student can hand in again
    assert auth.delete(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/submission").status_code == 204
    assert app.state.db.query("SELECT 1 FROM submissions WHERE id = :s", {"s": sid}) == []
    assert app.state.db.query("SELECT 1 FROM pages WHERE submission_id = :s", {"s": sid}) == []
    assert app.state.db.query("SELECT 1 FROM jobs WHERE submission_id = :s", {"s": sid}) == []
    assert auth.delete(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/submission").status_code == 404
    assert auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/upload",
                     files=[("files", ("p1.png", _png(), "image/png"))]).status_code == 202


def test_upload_for_unknown_student_or_deleted_template(auth):
    _with_key(auth)
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    assert auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/999/upload",
                     files=[("files", ("p1.png", _png(), "image/png"))]).status_code == 404
    # deleting the template is refused because it is set in a class; forced, later hand-ins fail clearly
    r = auth.delete(f"/api/assignments/{t['id']}")
    assert r.status_code == 409 and "set in 1 class" in r.json()["error"]["message"]
    assert auth.get(f"/api/assignments/{t['id']}").json()["class_assignment_count"] == 1
    assert auth.delete(f"/api/assignments/{t['id']}?force=true").status_code == 204
    assert auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["template_deleted"] is True
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{c['students'][0]['id']}/upload",
                  files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 409 and r.json()["error"]["code"] == "template_deleted"

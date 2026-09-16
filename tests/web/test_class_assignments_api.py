import io

from PIL import Image

from tests.web.seed_v2 import QUESTIONS as V2_QUESTIONS, SCHEME as V2_SCHEME, seed_v2

RUBRIC ={"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]}
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


def _link(app, sid, ca_id, student_id, handed_in="2026-09-09 13:02:00"):
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :a, student_id = :s, handed_in_at = :h, source = 'student' WHERE id = :id",
                         {"a": ca_id, "s": student_id, "h": handed_in, "id": sid})


def test_roster_counts_release_gate_and_marks_csv(auth, app):
    # The template's scheme must match the seeded runs' (1a, 1b, 2) so the CSV columns and max line up.
    t = _template(auth, questions=V2_QUESTIONS, scheme=V2_SCHEME)
    c = _class_with_students(auth, names=("Tan Wei Ling", "Muhammad Danish", "Priya Nair"))
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "due_at": "2026-09-10T00:00:00Z"}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={"title": ca["title"], "due_at": ca["due_at"], "allow_student_uploads": True, "status": "open"})
    tan, danish, priya = c["students"]
    sid_tan, qids = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan")          # needs_you (part 2)
    sid_dan, _ = seed_v2(app, label="#2 Muhammad Danish", assignment_id=t["id"], run_id="r-dan", queue={})  # done
    _link(app, sid_tan, ca["id"], tan["id"])
    _link(app, sid_dan, ca["id"], danish["id"], handed_in="2026-09-11 01:00:00")                         # late
    got = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()
    rows = got["roster"]["rows"]
    assert [r["status"] for r in rows] == ["needs_you", "ready", "not_handed_in"]
    assert rows[0]["needs_you_parts"] == ["2"] and rows[0]["late"] is False and rows[0]["total"] == 3 and rows[0]["total_upper"] == 5
    assert rows[1]["late"] is True and rows[1]["pages"] == 1 and rows[1]["source"] == "student"
    assert rows[2]["submission_id"] is None and rows[2]["total"] is None
    assert got["roster"]["counts"] == {"not_handed_in": 1, "handed_in": 0, "marking": 0, "needs_you": 1, "ready": 1}
    assert got["derived_status"] == "open"
    # release is refused while a part needs the teacher
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release")
    assert r.status_code == 409 and r.json()["error"]["code"] == "needs_you" and "1 part" in r.json()["error"]["message"]
    auth.post(f"/api/queue/{qids['2']}/resolve", json={"allocations": [{"label": "M1", "got": True}, {"label": "A1", "got": False}], "reason": "ok"})
    released = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release").json()
    assert released["status"] == "released" and released["released_at"] is not None
    rows = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["roster"]["rows"]
    assert [r["status"] for r in rows] == ["released", "released", "not_handed_in"]
    # marks csv: one column per part in scheme order, teacher's mark wins, blanks for not handed in
    r = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/marks.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="quadratics-worksheet-3-marks.csv"' in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0] == "reg_no,name,1(a),1(b),2,total,max,status"
    assert lines[1] == "1,Tan Wei Ling,2,0,1,3,6,released"
    assert lines[3] == "3,Priya Nair,,,,,6,not_handed_in"


def test_release_needs_at_least_one_marked_script(auth):
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release")
    assert r.status_code == 409 and r.json()["error"]["code"] == "nothing_marked"


def test_status_transitions_no_unrelease_and_no_draft_with_hand_ins(auth, app):
    t = _template(auth, questions=V2_QUESTIONS, scheme=V2_SCHEME)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    body = {"title": ca["title"], "due_at": None, "allow_student_uploads": True}
    assert auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={**body, "status": "open"}).json()["status"] == "open"
    sid, _ = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    _link(app, sid, ca["id"], c["students"][0]["id"])
    # open -> draft is refused while hand-ins exist
    r = auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={**body, "status": "draft"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_status"
    assert "Remove the hand-ins" in r.json()["error"]["message"]
    # the other fields can still be edited while open
    assert auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={**body, "title": "WS3", "status": "open"}).json()["title"] == "WS3"
    assert auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release").json()["status"] == "released"
    # released cannot be reopened (to open or draft); editing the title while released is fine
    for st in ("open", "draft"):
        r = auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={**body, "status": st})
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_status"
        assert "cannot be reopened" in r.json()["error"]["message"]
    got = auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={**body, "title": "Final", "status": "released"}).json()
    assert got["title"] == "Final" and got["status"] == "released"

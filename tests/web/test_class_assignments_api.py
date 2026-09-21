import io
import json
import zipfile

from PIL import Image

from sms.web.errors import ApiError
from sms.web.services import class_assignments
from tests.web.seed_v2 import QUESTIONS as V2_QUESTIONS, SCHEME as V2_SCHEME, seed_v2

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
    # removing a marked hand-in also drops its marking run and queue items, not just pages and jobs
    danish = c["students"][1]
    sid_dan, qids = seed_v2(app, label="#2 Muhammad Danish", assignment_id=t["id"], run_id="r-dan-remove")
    _link(app, sid_dan, ca["id"], danish["id"])
    assert app.state.db.query("SELECT 1 FROM marking_runs WHERE submission_id = :s", {"s": sid_dan}) != []
    assert auth.delete(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{danish['id']}/submission").status_code == 204
    assert app.state.db.query("SELECT 1 FROM submissions WHERE id = :s", {"s": sid_dan}) == []
    assert app.state.db.query("SELECT 1 FROM marking_runs WHERE submission_id = :s", {"s": sid_dan}) == []
    assert app.state.db.query("SELECT 1 FROM marking_runs WHERE run_id = 'r-dan-remove'", {}) == []
    assert app.state.db.query("SELECT 1 FROM teacher_queue WHERE submission_id = :s", {"s": sid_dan}) == []


def test_removing_a_file_hand_in_deletes_its_stored_files(auth, app):
    _with_key(auth)
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    tan = c["students"][0]
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/upload",
                  files=[("files", ("prog.py", b"print(1)\n", "text/x-python"))])
    assert r.status_code == 202
    sid = r.json()["id"]
    assert app.state.db.query("SELECT input_kind FROM submissions WHERE id = :s", {"s": sid})[0]["input_kind"] == "files"
    rel = app.state.db.query("SELECT stored_path FROM submission_files WHERE submission_id = :s", {"s": sid})[0]["stored_path"]
    assert app.state.storage.abs(rel).exists()
    assert auth.delete(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/submission").status_code == 204
    assert app.state.db.query("SELECT 1 FROM submission_files WHERE submission_id = :s", {"s": sid}) == []
    assert not app.state.storage.abs(rel).exists()


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
    # releasing again is refused and released_at is not re-stamped
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_released"
    assert auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["released_at"] == released["released_at"]
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


def test_release_needs_an_open_assignment_and_at_least_one_marked_script(auth):
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    # a draft cannot be released, whatever its scripts look like
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_open"
    assert "Open the assignment" in r.json()["error"]["message"]
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
             json={"title": ca["title"], "due_at": None, "allow_student_uploads": True, "status": "open"})
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release")
    assert r.status_code == 409 and r.json()["error"]["code"] == "nothing_marked"
    assert auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["status"] == "open"


def _seed_v1(app, *, label, assignment_id, run_id, marks, status="done"):
    """A submission marked by criteria (a v1 run): `marks` are final_marks_json rows {q_id, criterion_scores, total, ...}."""
    db = app.state.db
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status, run_id, assignment_id) "
                    "VALUES (:l, 'math', '', :r, :st, :run, :aid) RETURNING id",
                    {"l": label, "r": json.dumps(RUBRIC), "st": status, "run": run_id, "aid": assignment_id})
    db.execute("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height) VALUES (:s, 0, :h, :p, 1, 1)",
               {"s": sid, "h": f"h{sid}", "p": f"pages/h{sid}.jpg"})
    final = json.dumps({"marks": marks})
    db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, marks_json, final_marks_json, submission_id, final_status) "
               "VALUES (:r, 'complete', 'math', :rubric, :m, :m, :s, 'complete')",
               {"r": run_id, "rubric": json.dumps(RUBRIC), "m": final, "s": sid})
    return sid


def _v1_mark(q_id, score, total=None):
    return {"q_id": q_id, "criterion_scores": [score], "total": score if total is None else total,
            "confidence": 0.9, "evidence": "", "rationale": ""}


def test_marks_csv_for_a_criteria_template_uses_the_marked_questions(auth, app):
    t = _template(auth, scheme_kind="criteria", questions=[], scheme=[])  # RUBRIC: one criterion, max 2
    c = _class_with_students(auth, names=("Tan Wei Ling", "Muhammad Danish", "Priya Nair"))
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
             json={"title": ca["title"], "due_at": None, "allow_student_uploads": True, "status": "open"})
    tan, danish, priya = c["students"]
    # columns are the marked questions in first-seen order across the roster: Tan answered q1, q2; Danish q2, q3
    sid_tan = _seed_v1(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="v1-tan", marks=[_v1_mark("q1", 2), _v1_mark("q2", 1)])
    sid_dan = _seed_v1(app, label="#2 Muhammad Danish", assignment_id=t["id"], run_id="v1-dan", marks=[_v1_mark("q2", 0), _v1_mark("q3", 2)])
    _link(app, sid_tan, ca["id"], tan["id"])
    _link(app, sid_dan, ca["id"], danish["id"])
    # the teacher corrected Tan's q2 to full marks
    app.state.db.execute("INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason, criterion_scores_json) "
                         "VALUES ('v1-tan', 'q2', 1, 2, 'generous', '[2]')")
    r = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/marks.csv")
    assert r.status_code == 200
    lines = r.text.strip().splitlines()
    assert lines[0] == "reg_no,name,Q1,Q2,Q3,total,max,status"
    assert lines[1] == "1,Tan Wei Ling,2,2,,4,4,ready"      # max = 2 per question x 2 questions marked
    assert lines[2] == "2,Muhammad Danish,,0,2,2,4,ready"
    assert lines[3] == "3,Priya Nair,,,,,6,not_handed_in"   # max = 2 per question x 3 columns
    # the roster totals agree with the CSV
    rows = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["roster"]["rows"]
    assert (rows[0]["total"], rows[0]["total_max"]) == (4, 4) and (rows[1]["total"], rows[1]["total_max"]) == (2, 4)


def test_marks_csv_refuses_when_the_template_was_deleted(auth):
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    assert auth.delete(f"/api/assignments/{t['id']}?force=true").status_code == 204
    r = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/marks.csv")
    assert r.status_code == 409 and r.json()["error"]["code"] == "template_deleted"


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


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in entries:
            z.writestr(n, b)
    return buf.getvalue()


def _regs(entries):
    """The register numbers out of a `created`/`skipped` list of {"reg_no": ...} dicts."""
    return sorted(e["reg_no"] for e in entries)


def test_bulk_upload_matches_a_zip_for_a_whole_class_by_register_number(auth, app):
    _with_key(auth)
    t = _template(auth)
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 7, "name": "Amirah"}, {"reg_no": 12, "name": "Ben"}]})
    students = auth.get(f"/api/classes/{c['id']}/students").json()
    amirah = next(s for s in students if s["reg_no"] == 7)
    ben = next(s for s in students if s["reg_no"] == 12)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
             json={"title": ca["title"], "due_at": None, "allow_student_uploads": True, "status": "open"})
    zip_bytes = _zip([("07_a.py", b"print(1)\n"), ("12/prog.py", b"print(2)\n")])

    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk/preview",
                  files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    assert r.status_code == 200
    body = r.json()
    assert body["unmatched"] == [] and body["ambiguous"] == []
    matched = {m["student_id"]: m for m in body["matched"]}
    assert matched[amirah["id"]]["reg_no"] == 7 and matched[amirah["id"]]["files"] == ["07_a.py"]
    assert matched[ben["id"]]["reg_no"] == 12 and matched[ben["id"]]["files"] == ["12/prog.py"]
    assert matched[amirah["id"]]["already_handed_in"] is False and matched[ben["id"]]["already_handed_in"] is False

    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk",
                  files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    assert r.status_code == 202
    result = r.json()
    assert _regs(result["created"]) == [7, 12] and result["skipped"] == [] and result["unmatched"] == []
    assert all(c["ignored"] == [] for c in result["created"])
    sub_a = app.state.db.query("SELECT id FROM submissions WHERE student_id = :s", {"s": amirah["id"]})[0]["id"]
    sub_b = app.state.db.query("SELECT id FROM submissions WHERE student_id = :s", {"s": ben["id"]})[0]["id"]

    # a second preview now shows both as already handed in
    body = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk/preview",
                     files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))]).json()
    matched = {m["student_id"]: m for m in body["matched"]}
    assert matched[amirah["id"]]["already_handed_in"] is True and matched[ben["id"]]["already_handed_in"] is True

    # a second bulk upload without replace skips both — they already handed in
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk",
                  files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    assert r.status_code == 202
    result = r.json()
    assert result["created"] == [] and _regs(result["skipped"]) == [7, 12]

    # with ?replace=1, the old submissions are removed and new ones created in their place
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk?replace=1",
                  files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    assert r.status_code == 202
    result = r.json()
    assert _regs(result["created"]) == [7, 12] and result["skipped"] == []
    assert app.state.db.query("SELECT 1 FROM submissions WHERE id = :s", {"s": sub_a}) == []
    assert app.state.db.query("SELECT 1 FROM submissions WHERE id = :s", {"s": sub_b}) == []


def test_bulk_upload_reports_unmatched_entries_without_blocking_a_matched_student(auth, app):
    # `students` has a UNIQUE(class_id, reg_no) constraint, so two students sharing a register
    # number cannot exist in one class via the public API — `ambiguous` is exercised at the
    # `match_entries` unit level (tests/unit/test_files_bulk.py) instead of here.
    _with_key(auth)
    t = _template(auth)
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 7, "name": "Amirah"}]})
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
             json={"title": ca["title"], "due_at": None, "allow_student_uploads": True, "status": "open"})
    # "notes.txt" matches no register number: unmatched, but does not block Amirah's own hand-in
    zip_bytes = _zip([("07_a.py", b"print(1)\n"), ("notes.txt", b"hi\n")])
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk/preview",
                  files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    assert r.status_code == 200
    body = r.json()
    assert body["ambiguous"] == [] and body["unmatched"] == ["notes.txt"]
    assert [m["reg_no"] for m in body["matched"]] == [7]
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk",
                  files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    assert r.status_code == 202
    result = r.json()
    assert _regs(result["created"]) == [7] and result["unmatched"] == ["notes.txt"] and result["ambiguous"] == []


def test_bulk_upload_ignores_junk_without_failing_the_matched_student(auth, app):
    _with_key(auth)
    t = _template(auth)
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 7, "name": "Amirah"}]})
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
             json={"title": ca["title"], "due_at": None, "allow_student_uploads": True, "status": "open"})
    # a zero-byte stray inside the student's folder must not fail the whole student; the preview
    # already shows it split into `files` (usable) and `ignored`
    zip_bytes = _zip([("7/prog.py", b"print(1)\n"), ("7/empty.py", b"")])
    body = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk/preview",
                     files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))]).json()
    assert body["matched"][0]["files"] == ["7/prog.py"] and body["matched"][0]["ignored"] == ["7/empty.py"]
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk",
                  files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    assert r.status_code == 202
    result = r.json()
    assert result["failed"] == [] and len(result["created"]) == 1
    assert result["created"][0] == {"reg_no": 7, "ignored": ["7/empty.py"]}


def _bulk_setup(auth, rows=({"reg_no": 7, "name": "Amirah"},)):
    t = _template(auth)
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    auth.put(f"/api/classes/{c['id']}/students", json={"rows": list(rows)})
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
             json={"title": ca["title"], "due_at": None, "allow_student_uploads": True, "status": "open"})
    return c, ca


def test_bulk_replace_validates_new_files_before_touching_the_old_hand_in(auth, app):
    _with_key(auth)
    c, ca = _bulk_setup(auth)
    good_zip = _zip([("7/prog.py", b"print(1)\n")])
    auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk", files=[("zip", ("bulk.zip", good_zip, "application/zip"))])
    sub = app.state.db.query("SELECT id FROM submissions WHERE class_assignment_id = :a", {"a": ca["id"]})[0]["id"]

    # the replace zip's only entry for this student is unsupported (an unrelated usable entry keeps
    # the archive itself from being rejected as "nothing usable"): the old hand-in must be left alone
    bad_zip = _zip([("7/notes.txt", b"hi\n"), ("99_extra.py", b"print(1)\n")])
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk?replace=1",
                  files=[("zip", ("bulk.zip", bad_zip, "application/zip"))])
    assert r.status_code == 202
    result = r.json()
    assert result["created"] == [] and len(result["failed"]) == 1
    failed = result["failed"][0]
    assert failed["reg_no"] == 7 and "no usable files" in failed["error"] and "Previous hand-in removed" not in failed["error"]
    assert app.state.db.query("SELECT 1 FROM submissions WHERE id = :s", {"s": sub}) != []


def test_bulk_replace_prefixes_the_failure_once_the_old_hand_in_is_already_gone(auth, app, monkeypatch):
    _with_key(auth)
    c, ca = _bulk_setup(auth)
    zip_bytes = _zip([("7/prog.py", b"print(1)\n")])
    auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk", files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    sub = app.state.db.query("SELECT id FROM submissions WHERE class_assignment_id = :a", {"a": ca["id"]})[0]["id"]

    def _boom(*a, **k):
        raise ApiError(400, "bad_subject", "boom")

    monkeypatch.setattr(class_assignments, "hand_in", _boom)
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk?replace=1",
                  files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    assert r.status_code == 202
    result = r.json()
    assert result["created"] == [] and len(result["failed"]) == 1
    failed = result["failed"][0]
    assert failed["reg_no"] == 7 and failed["error"] == "Previous hand-in removed — boom"
    # the old hand-in really is gone — a `replace` does not get a free rollback
    assert app.state.db.query("SELECT 1 FROM submissions WHERE id = :s", {"s": sub}) == []


def test_bulk_upload_one_student_with_no_usable_files_does_not_block_another(auth, app):
    _with_key(auth)
    c, ca = _bulk_setup(auth, rows=[{"reg_no": 7, "name": "Amirah"}, {"reg_no": 12, "name": "Ben"}])
    zip_bytes = _zip([("7/notes.txt", b"hi\n"), ("12/prog.py", b"print(1)\n")])
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk",
                  files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    assert r.status_code == 202
    result = r.json()
    assert _regs(result["created"]) == [12]
    assert len(result["failed"]) == 1 and result["failed"][0]["reg_no"] == 7
    assert "no usable files" in result["failed"][0]["error"]


def test_bulk_upload_a_student_level_crash_does_not_abort_the_batch(auth, app, monkeypatch):
    _with_key(auth)
    c, ca = _bulk_setup(auth, rows=[{"reg_no": 7, "name": "Amirah"}, {"reg_no": 12, "name": "Ben"}])
    zip_bytes = _zip([("7/prog.py", b"print(1)\n"), ("12/prog.py", b"print(2)\n")])
    real_hand_in = class_assignments.hand_in

    def _flaky(db, storage, jobs, *, ca, student, files, source):
        if student["reg_no"] == 7:
            raise RuntimeError("boom")
        return real_hand_in(db, storage, jobs, ca=ca, student=student, files=files, source=source)

    monkeypatch.setattr(class_assignments, "hand_in", _flaky)
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk",
                  files=[("zip", ("bulk.zip", zip_bytes, "application/zip"))])
    assert r.status_code == 202
    result = r.json()
    assert _regs(result["created"]) == [12]
    assert len(result["failed"]) == 1 and result["failed"][0]["reg_no"] == 7
    assert result["failed"][0]["error"] and "Previous hand-in removed" not in result["failed"][0]["error"]


def test_bulk_zip_takes_more_than_one_submission_s_20_mb_unpacked(auth, app):
    """A class's photos are not downsized in the browser the way one hand-in's are, so the bulk
    archive's decompressed cap is the 50 MB body cap, not the 20 MB a single submission's zip gets."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("7/scan.jpg", b"0" * (21 * 1024 * 1024))
    c, ca = _bulk_setup(auth)
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk/preview",
                  files=[("zip", ("bulk.zip", buf.getvalue(), "application/zip"))])
    assert r.status_code == 200 and _regs(r.json()["matched"]) == [7]


def test_bulk_zip_over_fifty_mb_unpacked_is_too_large_not_a_zip_bomb(auth, app):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("7/scan.jpg", b"0" * (51 * 1024 * 1024))
    c, ca = _bulk_setup(auth)
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/bulk/preview",
                  files=[("zip", ("bulk.zip", buf.getvalue(), "application/zip"))])
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "too_large"
    assert err["message"] == ("bulk zip is over 50 MB unpacked — downsize the photos or split the "
                             "class into two zips")


def _zip_with_one_unreadable_entry():
    """A stored entry whose bytes are altered after the fact: reading it fails the CRC, which is
    what a password-protected or oddly compressed entry looks like from here. Its extension is one
    `classify_uploads` skips without reading, so only `_read_bulk_zip` ever opens it."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("7/prog.py", b"print(1)\n")
        z.writestr("7/notes.txt", b"A" * 32)
    return buf.getvalue().replace(b"A" * 32, b"B" * 32)


def test_bulk_zip_with_an_unreadable_entry_is_a_400_not_a_500(auth, app):
    _with_key(auth)
    c, ca = _bulk_setup(auth)
    for path in ("bulk/preview", "bulk"):
        r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/{path}",
                      files=[("zip", ("bulk.zip", _zip_with_one_unreadable_entry(), "application/zip"))])
        assert r.status_code == 400, path
        err = r.json()["error"]
        assert err["code"] == "bad_file" and "bulk.zip" in err["message"]
        assert "could not be unpacked" in err["message"]

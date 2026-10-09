def test_requires_auth(client):
    assert client.get("/api/classes").status_code == 401


def test_create_list_rename_archive_regenerate(auth):
    r = auth.post("/api/classes", json={"name": "4E2 Mathematics"})
    assert r.status_code == 201
    c = r.json()
    assert c["name"] == "4E2 Mathematics" and len(c["code"]) == 4 and c["student_count"] == 0 and c["open_assignments"] == 0
    assert c["archived_at"] is None
    assert auth.post("/api/classes", json={"name": "  "}).json()["error"]["code"] == "bad_name"
    assert [x["id"] for x in auth.get("/api/classes").json()] == [c["id"]]
    assert auth.get(f"/api/classes/{c['id']}").json()["code"] == c["code"]
    assert auth.get("/api/classes/999").status_code == 404
    assert auth.put(f"/api/classes/{c['id']}", json={"name": "4E2 Maths"}).json()["name"] == "4E2 Maths"
    old = c["code"]
    new = auth.post(f"/api/classes/{c['id']}/regenerate-code").json()["code"]
    assert new != old and len(new) == 4
    archived = auth.post(f"/api/classes/{c['id']}/archive").json()
    assert archived["archived_at"] is not None
    # archived classes list last
    d = auth.post("/api/classes", json={"name": "3N1 Science"}).json()
    assert [x["id"] for x in auth.get("/api/classes").json()] == [d["id"], c["id"]]
    assert auth.post(f"/api/classes/{c['id']}/unarchive").json()["archived_at"] is None


CSV = b"name,reg_no\nTan Wei Ling,1\nMuhammad Danish,2\nPriya Nair,3\n"


def _class(auth, name="4E2"):
    return auth.post("/api/classes", json={"name": name}).json()


def test_classlist_preview_confirm_and_list(auth):
    c = _class(auth)
    p = auth.post(f"/api/classes/{c['id']}/students/preview", files=[("file", ("list.csv", CSV, "text/csv"))]).json()
    assert p["errors"] == [] and [r["name"] for r in p["rows"]] == ["Tan Wei Ling", "Muhammad Danish", "Priya Nair"]
    assert auth.get(f"/api/classes/{c['id']}/students").json() == []   # preview saves nothing
    r = auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": x["reg_no"], "name": x["name"]} for x in p["rows"]]})
    assert r.status_code == 200 and r.json()["kept"] == []
    students = auth.get(f"/api/classes/{c['id']}/students").json()
    assert [(s["reg_no"], s["name"], s["submissions"], s["last_seen_at"]) for s in students] == \
        [(1, "Tan Wei Ling", 0, None), (2, "Muhammad Danish", 0, None), (3, "Priya Nair", 0, None)]
    assert auth.get(f"/api/classes/{c['id']}").json()["student_count"] == 3


def test_classlist_rejects_rows_with_issues(auth):
    c = _class(auth)
    r = auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 1, "name": "Tan"}, {"reg_no": 1, "name": "Lim"}]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_rows"
    r = auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 0, "name": "Tan"}]})
    assert r.json()["error"]["code"] == "bad_rows"
    r = auth.put(f"/api/classes/{c['id']}/students", json={"rows": []})
    assert r.json()["error"]["code"] == "bad_rows"


def test_replace_classlist_keeps_students_with_submissions(auth, app):
    c = _class(auth)
    auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 1, "name": "Tan"}, {"reg_no": 2, "name": "Lim"}]})
    tan = auth.get(f"/api/classes/{c['id']}/students").json()[0]
    app.state.db.execute("INSERT INTO submissions (label, subject, context, rubric_json, status, student_id) "
                         "VALUES ('#1 Tan', 'math', '', '{}', 'done', :s)", {"s": tan["id"]})
    r = auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 2, "name": "Lim J H"}, {"reg_no": 3, "name": "Ong"}]}).json()
    assert r["kept"] == [1]
    assert [(s["reg_no"], s["name"], s["submissions"]) for s in r["students"]] == [(1, "Tan", 1), (2, "Lim J H", 0), (3, "Ong", 0)]


def test_preview_reports_file_errors(auth):
    c = _class(auth)
    p = auth.post(f"/api/classes/{c['id']}/students/preview", files=[("file", ("list.csv", b"a,b\n1,2\n", "text/csv"))]).json()
    assert p["rows"] == [] and p["errors"] == ["The first row must have the columns name and reg_no"]


def _template(auth, subject="math"):
    return auth.post("/api/assignments", json={
        "title": f"{subject} paper", "subject": subject, "context": "",
        "rubric": {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]},
        "scheme_kind": "mark_scheme", "questions": [{"q_id": "1a", "text": "Solve 3x = 9", "max_marks": 2}],
        "scheme": [{"q_id": "1a", "answer": "x = 3", "marks": [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 1}], "notes": ""}]}).json()


def test_subject_is_saved_validated_or_derived_from_the_latest_class_assignment(auth):
    c = auth.post("/api/classes", json={"name": "4E2 Mathematics", "subject": "math"}).json()
    assert c["subject"] == "math" and c["marking"] == 0 and c["needs_you"] == 0
    assert auth.post("/api/classes", json={"name": "X", "subject": "art"}).json()["error"]["code"] == "bad_subject"
    d = auth.post("/api/classes", json={"name": "2E3"}).json()
    assert d["subject"] is None
    t_sci = _template(auth, "science"); t_eng = _template(auth, "language")
    auth.post(f"/api/classes/{d['id']}/assignments", json={"template_id": t_sci["id"]})
    auth.post(f"/api/classes/{d['id']}/assignments", json={"template_id": t_eng["id"]})
    assert auth.get(f"/api/classes/{d['id']}").json()["subject"] == "language"   # the latest set wins
    assert auth.put(f"/api/classes/{d['id']}", json={"name": "2E3", "subject": "science"}).json()["subject"] == "science"
    assert auth.put(f"/api/classes/{d['id']}", json={"name": "2E3 Sci"}).json()["subject"] == "science"   # name-only keeps it
    assert auth.put(f"/api/classes/{d['id']}", json={"name": "2E3 Sci", "subject": None}).json()["subject"] == "language"  # back to derived


def test_marking_and_needs_you_count_this_class_only(auth, app):
    from tests.web.seed_v2 import seed_v2
    t = _template(auth)
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    other = auth.post("/api/classes", json={"name": "3N1"}).json()
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    ca2 = auth.post(f"/api/classes/{other['id']}/assignments", json={"template_id": t["id"]}).json()
    a, _ = seed_v2(app, run_id="r-1", queue={}); b, _ = seed_v2(app, run_id="r-2", queue={}); x, _ = seed_v2(app, run_id="r-3", queue={})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :ca, status = 'marking' WHERE id = :i", {"ca": ca["id"], "i": a})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :ca, status = 'needs_you' WHERE id = :i", {"ca": ca["id"], "i": b})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :ca, status = 'queued' WHERE id = :i", {"ca": ca2["id"], "i": x})
    rows = {r["name"]: r for r in auth.get("/api/classes").json()}
    assert (rows["4E2"]["marking"], rows["4E2"]["needs_you"]) == (1, 1)
    assert (rows["3N1"]["marking"], rows["3N1"]["needs_you"]) == (1, 0)

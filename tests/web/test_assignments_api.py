import io
import json

from PIL import Image

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2},
                              {"id": "c2", "description": "answer", "max_score": 3}]}


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def _create(auth, **over):
    body = {"title": "Worksheet 3", "subject": "math", "context": "Sec 4 · Quadratics", "rubric": RUBRIC}
    body.update(over)
    return auth.post("/api/assignments", json=body)


def _with_key(auth):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x",
                                    "rpm_limit": 60, "confidence_threshold": 0})
    return auth


def test_requires_auth(client):
    assert client.get("/api/assignments").status_code == 401
    assert client.post("/api/assignments", json={}).status_code == 401
    assert client.get("/api/assignments/export").status_code == 401


def test_create_lists_with_counts_and_orders_by_times_used(auth, app):
    a = _create(auth, title="A")
    assert a.status_code == 201
    body = a.json()
    assert body["title"] == "A" and body["criteria_count"] == 2 and body["total_marks"] == 5 and body["times_used"] == 0
    assert body["rubric"]["criterion_defs"][0]["id"] == "c1"
    assert body["created_at"].endswith("Z") and body["updated_at"].endswith("Z")
    b = _create(auth, title="B").json()
    app.state.db.execute("UPDATE assignment_templates SET times_used = 3 WHERE id = :id", {"id": b["id"]})
    lst = auth.get("/api/assignments").json()
    assert [t["title"] for t in lst] == ["B", "A"]


def test_validation_codes(auth):
    assert _create(auth, title="   ").json()["error"]["code"] == "bad_title"
    assert _create(auth, subject="art").json()["error"]["code"] == "bad_subject"
    assert _create(auth, rubric={"criterion_defs": []}).json()["error"]["code"] == "bad_rubric"
    assert _create(auth, rubric={"nope": 1}).json()["error"]["code"] == "bad_rubric"
    assert _create(auth, title="   ").status_code == 400


def test_update(auth):
    t = _create(auth).json()
    r = auth.put(f"/api/assignments/{t['id']}", json={"title": "Renamed", "subject": "science", "context": "ctx",
                                                      "rubric": {"criterion_defs": [{"id": "x", "description": "d", "max_score": 4}]}})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Renamed" and body["subject"] == "science" and body["total_marks"] == 4 and body["criteria_count"] == 1
    assert auth.put("/api/assignments/9999", json={"title": "x", "subject": "math", "context": "", "rubric": RUBRIC}).status_code == 404
    assert auth.put(f"/api/assignments/{t['id']}", json={"title": "", "subject": "math", "context": "", "rubric": RUBRIC}).json()["error"]["code"] == "bad_title"


def test_delete_then_404(auth):
    t = _create(auth).json()
    assert auth.delete(f"/api/assignments/{t['id']}").status_code == 204
    assert auth.delete(f"/api/assignments/{t['id']}").status_code == 404
    assert auth.get("/api/assignments").json() == []


def test_export_import_round_trip_skips_duplicates(auth):
    _create(auth, title="A")
    _create(auth, title="B", subject="science")
    r = auth.get("/api/assignments/export")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="assignments.json"'
    payload = r.json()
    assert payload["version"] == 1 and len(payload["assignments"]) == 2
    assert set(payload["assignments"][0]) == {"title", "subject", "context", "rubric", "scheme_kind", "questions", "scheme"}
    # importing the export again creates nothing (exact title+subject duplicates are skipped)
    r = auth.post("/api/assignments/import", json=payload)
    assert r.status_code == 200 and r.json() == {"created": 0}
    payload["assignments"].append({"title": "A", "subject": "language", "context": "", "rubric": RUBRIC})
    assert auth.post("/api/assignments/import", json=payload).json() == {"created": 1}
    assert len(auth.get("/api/assignments").json()) == 3


def test_import_rejects_bad_shape(auth):
    r = auth.post("/api/assignments/import", json={"version": 1})
    assert r.status_code == 400
    r = auth.post("/api/assignments/import", json={"version": 1, "assignments": [{"title": "x"}]})
    assert r.status_code == 400
    r = auth.post("/api/assignments/import", json={"version": 1, "assignments": [{"title": "x", "subject": "math", "context": "", "rubric": {"criterion_defs": []}}]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_rubric"


def test_marking_with_assignment_id_counts_usage_and_shows_title(auth):
    auth = _with_key(auth)
    t = _create(auth, title="Worksheet 3").json()
    data = {"label": "Tan Wei Ling", "subject": "math", "context": "", "rubric": json.dumps(RUBRIC), "assignment_id": str(t["id"])}
    r = auth.post("/api/submissions", data=data, files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 202
    sid = r.json()["id"]
    assert auth.get("/api/assignments").json()[0]["times_used"] == 1
    row = auth.get("/api/submissions").json()[0]
    assert row["assignment_id"] == t["id"] and row["assignment_title"] == "Worksheet 3"
    detail = auth.get(f"/api/submissions/{sid}").json()
    assert detail["assignment_id"] == t["id"] and detail["assignment_title"] == "Worksheet 3"


def test_marking_without_assignment_id_has_nulls(auth):
    auth = _with_key(auth)
    data = {"label": "Tan", "subject": "math", "context": "", "rubric": json.dumps(RUBRIC)}
    r = auth.post("/api/submissions", data=data, files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 202
    row = auth.get("/api/submissions").json()[0]
    assert row["assignment_id"] is None and row["assignment_title"] is None
    # an unknown assignment id is ignored rather than rejected
    data["assignment_id"] = "9999"
    r = auth.post("/api/submissions", data=data, files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 202 and auth.get("/api/submissions").json()[0]["assignment_id"] is None


# --- scheme kind, question list and question paper -------------------------------------------

QUESTIONS = [{"q_id": "q1", "text": "Solve 2x + 3 = 7", "max_marks": 2},
             {"q_id": "q2", "text": "Factorise x^2 - 9", "max_marks": 3}]
MARK_SCHEME = [{"q_id": "q1", "answer": "x = 2", "marks": [{"label": "M1 rearranges", "marks": 1}, {"label": "A1 x = 2", "marks": 1}], "notes": "Accept 2"},
               {"q_id": "q2", "answer": "(x-3)(x+3)", "marks": [{"label": "A1", "marks": 3}], "notes": ""}]
BANDS = [{"criterion": "Structure", "bands": [{"band": "A", "marks": 5, "descriptor": "Clear"}, {"band": "B", "marks": 3, "descriptor": "Some"}]}]


def test_defaults_to_criteria_scheme_with_empty_lists(auth):
    t = _create(auth).json()
    assert t["scheme_kind"] == "criteria" and t["questions"] == [] and t["scheme"] == [] and t["paper_page_ids"] == []


def test_mark_scheme_template_round_trips_questions_and_scheme(auth):
    r = _create(auth, scheme_kind="mark_scheme", questions=QUESTIONS, scheme=MARK_SCHEME)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["scheme_kind"] == "mark_scheme"
    assert [q["q_id"] for q in t["questions"]] == ["q1", "q2"] and t["questions"][1]["max_marks"] == 3
    assert t["scheme"][0]["marks"][0]["label"] == "M1 rearranges" and t["scheme"][0]["notes"] == "Accept 2"
    got = auth.get("/api/assignments").json()[0]
    assert got["questions"] == t["questions"] and got["scheme"] == t["scheme"]
    r = auth.put(f"/api/assignments/{t['id']}", json={"title": "W", "subject": "language", "context": "", "rubric": RUBRIC,
                                                      "scheme_kind": "rubric", "scheme": BANDS})
    assert r.status_code == 200, r.text
    assert r.json()["scheme_kind"] == "rubric" and r.json()["scheme"][0]["bands"][1]["band"] == "B" and r.json()["questions"] == []


def test_scheme_validation_codes(auth):
    assert _create(auth, scheme_kind="essay").json()["error"]["code"] == "bad_scheme_kind"
    assert _create(auth, questions=[{"text": "no id"}]).json()["error"]["code"] == "bad_questions"
    assert _create(auth, questions="q1").json()["error"]["code"] == "bad_questions"
    assert _create(auth, scheme_kind="mark_scheme", scheme=[{"answer": "x"}]).json()["error"]["code"] == "bad_scheme"
    assert _create(auth, scheme_kind="mark_scheme", scheme=BANDS).json()["error"]["code"] == "bad_scheme"
    assert _create(auth, scheme_kind="rubric", scheme=MARK_SCHEME).json()["error"]["code"] == "bad_scheme"
    assert _create(auth, scheme_kind="criteria", scheme=MARK_SCHEME).json()["error"]["code"] == "bad_scheme"


def test_paper_upload_stores_template_pages_and_replaces_previous(auth, app, client):
    t = _create(auth).json()
    r = auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("p1.png", _png(), "image/png")),
                                                              ("files", ("p2.png", _png(), "image/png"))])
    assert r.status_code == 200, r.text
    first = r.json()["pages"]
    assert len(first) == 2 and first[0]["page_index"] == 0 and first[1]["page_index"] == 1
    got = auth.get("/api/assignments").json()[0]
    assert got["paper_page_ids"] == [p["id"] for p in first]
    row = app.state.db.query("SELECT submission_id, template_id FROM pages WHERE id = :id", {"id": first[0]["id"]})[0]
    assert row["submission_id"] is None and row["template_id"] == t["id"]
    # template pages are served by the page route, and only to a signed-in teacher
    assert auth.get(f"/api/pages/{first[0]['id']}").headers["content-type"] == "image/jpeg"
    # a second upload replaces the first paper
    r = auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("p3.png", _png(), "image/png"))])
    second = r.json()["pages"]
    assert len(second) == 1 and auth.get("/api/assignments").json()[0]["paper_page_ids"] == [second[0]["id"]]
    assert app.state.db.query("SELECT COUNT(*) AS c FROM pages WHERE template_id = :t", {"t": t["id"]})[0]["c"] == 1
    # (SQLite may reuse the first id for the new row, so check the second old page rather than the first)
    assert auth.get(f"/api/pages/{first[1]['id']}").status_code == 404
    assert auth.post("/api/assignments/9999/paper", files=[("files", ("p.png", _png(), "image/png"))]).status_code == 404
    r = auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("notes.txt", b"hi", "text/plain"))])
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_upload"
    # deleting the template removes its paper pages
    auth.delete(f"/api/assignments/{t['id']}")
    assert app.state.db.query("SELECT COUNT(*) AS c FROM pages WHERE template_id = :t", {"t": t["id"]})[0]["c"] == 0
    client.cookies.clear()
    assert client.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("p.png", _png(), "image/png"))]).status_code == 401


def test_export_import_carry_scheme_fields_but_not_pages(auth):
    t = _create(auth, title="Paper 1", scheme_kind="mark_scheme", questions=QUESTIONS, scheme=MARK_SCHEME).json()
    auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("p1.png", _png(), "image/png"))])
    payload = auth.get("/api/assignments/export").json()
    item = payload["assignments"][0]
    assert set(item) == {"title", "subject", "context", "rubric", "scheme_kind", "questions", "scheme"}
    assert item["scheme_kind"] == "mark_scheme" and item["questions"] == t["questions"] and item["scheme"] == t["scheme"]
    item["title"] = "Paper 1 (copy)"
    assert auth.post("/api/assignments/import", json=payload).json() == {"created": 1}
    copy = next(x for x in auth.get("/api/assignments").json() if x["title"] == "Paper 1 (copy)")
    assert copy["scheme_kind"] == "mark_scheme" and copy["scheme"] == t["scheme"] and copy["paper_page_ids"] == []
    # legacy exports without the new fields still import as plain criteria templates
    legacy = {"version": 1, "assignments": [{"title": "Old", "subject": "math", "context": "", "rubric": RUBRIC}]}
    assert auth.post("/api/assignments/import", json=legacy).json() == {"created": 1}
    # and a bad scheme in an import is rejected as a whole
    bad = {"version": 1, "assignments": [{"title": "New", "subject": "math", "context": "", "rubric": RUBRIC, "scheme_kind": "nope"}]}
    r = auth.post("/api/assignments/import", json=bad)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_scheme_kind"


def test_rename_keeps_paper_pages(auth):
    t = _create(auth, title="Paper 1").json()
    pages = auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("p1.png", _png(), "image/png")),
                                                                  ("files", ("p2.png", _png(), "image/png"))]).json()["pages"]
    ids = [p["id"] for p in pages]
    r = auth.put(f"/api/assignments/{t['id']}", json={"title": "Paper 1 renamed", "subject": "math", "context": "", "rubric": RUBRIC})
    assert r.status_code == 200 and r.json()["paper_page_ids"] == ids
    got = next(x for x in auth.get("/api/assignments").json() if x["id"] == t["id"])
    assert got["title"] == "Paper 1 renamed" and got["paper_page_ids"] == ids
    # paper_page_ids is derived from the pages table, not accepted from the client
    r = auth.put(f"/api/assignments/{t['id']}", json={"title": "x", "subject": "math", "context": "", "rubric": RUBRIC, "paper_page_ids": []})
    assert r.status_code == 200 and r.json()["paper_page_ids"] == ids


def test_duplicate_copies_scheme_and_paper_pages(auth, app):
    t = _create(auth, title="Paper 1", scheme_kind="mark_scheme", questions=QUESTIONS, scheme=MARK_SCHEME).json()
    src_pages = auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("p1.png", _png(), "image/png"))]).json()["pages"]
    r = auth.post(f"/api/assignments/{t['id']}/duplicate")
    assert r.status_code == 201, r.text
    copy = r.json()
    assert copy["id"] != t["id"] and copy["title"] == "Paper 1 (copy)" and copy["scheme"] == t["scheme"] and copy["questions"] == t["questions"]
    assert len(copy["paper_page_ids"]) == 1 and copy["paper_page_ids"] != [p["id"] for p in src_pages]
    rows = app.state.db.query("SELECT template_id, storage_path, sha256, page_index FROM pages ORDER BY id")
    assert len(rows) == 2 and rows[0]["storage_path"] == rows[1]["storage_path"] and rows[1]["template_id"] == copy["id"]
    assert auth.get(f"/api/pages/{copy['paper_page_ids'][0]}").status_code == 200
    # deleting the copy leaves the original's page intact
    auth.delete(f"/api/assignments/{copy['id']}")
    assert auth.get("/api/assignments").json()[0]["paper_page_ids"] == [p["id"] for p in src_pages]
    assert auth.post("/api/assignments/9999/duplicate").status_code == 404


# --- delete student pages after marking (per assignment, NULL = follow the global default) ------

def test_delete_pages_flag_defaults_to_null_and_follows_global_setting(auth):
    t = _create(auth).json()
    assert t["delete_pages_after_marking"] is None and t["effective_delete_pages"] is True
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 60,
                                    "confidence_threshold": 0, "delete_pages_after_marking": False})
    got = auth.get("/api/assignments").json()[0]
    assert got["delete_pages_after_marking"] is None and got["effective_delete_pages"] is False
    on = _create(auth, title="On", delete_pages_after_marking=True).json()
    assert on["delete_pages_after_marking"] is True and on["effective_delete_pages"] is True


def test_delete_pages_flag_put_get_and_duplicate(auth):
    t = _create(auth, delete_pages_after_marking=False).json()
    assert t["delete_pages_after_marking"] is False and t["effective_delete_pages"] is False
    body = {"title": "W", "subject": "math", "context": "", "rubric": RUBRIC, "delete_pages_after_marking": True}
    r = auth.put(f"/api/assignments/{t['id']}", json=body)
    assert r.status_code == 200 and r.json()["delete_pages_after_marking"] is True
    body["delete_pages_after_marking"] = None
    assert auth.put(f"/api/assignments/{t['id']}", json=body).json()["delete_pages_after_marking"] is None
    body["delete_pages_after_marking"] = False
    auth.put(f"/api/assignments/{t['id']}", json=body)
    copy = auth.post(f"/api/assignments/{t['id']}/duplicate").json()
    assert copy["delete_pages_after_marking"] is False
    assert auth.get("/api/assignments").json()[0]["id"] == copy["id"]

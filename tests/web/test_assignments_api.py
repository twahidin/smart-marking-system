import io
import json

from PIL import Image

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2},
                              {"id": "c2", "description": "answer", "max_score": 3}]}


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def _body():
    return {"title": "Worksheet 3", "subject": "math", "context": "Sec 4 · Quadratics", "rubric": RUBRIC}


def _create(auth, **over):
    body = _body()
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


def test_delete_refuses_an_assignment_scripts_reference_unless_forced(auth, app):
    from tests.web.seed_v2 import seed_v2
    t = _create(auth, scheme_kind="mark_scheme").json()
    assert (t["submission_count"], t["pending_count"]) == (0, 0)
    seed_v2(app, assignment_id=t["id"])                          # marked (needs_you)
    seed_v2(app, assignment_id=t["id"], run_id="r3", status="done")
    app.state.db.execute("INSERT INTO submissions (label, subject, context, rubric_json, status, assignment_id, scheme_kind) "
                         "VALUES ('waiting', 'math', '', '{\"criterion_defs\": []}', 'queued', :a, 'mark_scheme')", {"a": t["id"]})
    got = auth.get(f"/api/assignments/{t['id']}").json()
    assert (got["submission_count"], got["pending_count"]) == (3, 1)
    listed = [a for a in auth.get("/api/assignments").json() if a["id"] == t["id"]][0]
    assert (listed["submission_count"], listed["pending_count"]) == (3, 1)
    r = auth.delete(f"/api/assignments/{t['id']}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "in_use"
    assert "3 scripts" in r.json()["error"]["message"]
    assert auth.get(f"/api/assignments/{t['id']}").status_code == 200
    assert auth.delete(f"/api/assignments/{t['id']}?force=true").status_code == 204
    assert auth.get(f"/api/assignments/{t['id']}").status_code == 404
    # the marked scripts keep their marks and their record still opens from the run's snapshot
    subs = auth.get("/api/submissions").json()
    assert {s["label"] for s in subs} == {"Tan", "waiting"} and all(s["assignment_id"] is None or True for s in subs)
    marked = [s for s in subs if s["status"] in ("needs_you", "done")]
    assert all(auth.get(f"/api/submissions/{s['id']}/record.docx").status_code == 200 for s in marked)


def test_delete_refuses_an_assignment_set_in_a_class_unless_forced(auth):
    t = _create(auth).json()
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]})
    assert auth.get(f"/api/assignments/{t['id']}").json()["class_assignment_count"] == 1
    r = auth.delete(f"/api/assignments/{t['id']}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "in_use"
    assert r.json()["error"]["message"] == "set in 1 class — delete anyway to remove it from the bank"
    assert auth.delete(f"/api/assignments/{t['id']}?force=true").status_code == 204


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


# --- scheme upload and extraction jobs ---------------------------------------------------------

def test_scheme_upload_stores_scheme_pages_and_replaces_previous(auth, app):
    t = _create(auth, scheme_kind="mark_scheme").json()
    assert t["scheme_page_ids"] == []
    paper = auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("p1.png", _png(), "image/png"))]).json()["pages"]
    r = auth.post(f"/api/assignments/{t['id']}/scheme", files=[("files", ("s1.png", _png(), "image/png")),
                                                               ("files", ("s2.png", _png(), "image/png"))])
    assert r.status_code == 200, r.text
    first = r.json()["pages"]
    assert len(first) == 2 and [p["page_index"] for p in first] == [0, 1]
    got = auth.get("/api/assignments").json()[0]
    assert got["scheme_page_ids"] == [p["id"] for p in first] and got["paper_page_ids"] == [paper[0]["id"]]
    kinds = {r["id"]: r["kind"] for r in app.state.db.query("SELECT id, kind FROM pages WHERE template_id = :t", {"t": t["id"]})}
    assert kinds[paper[0]["id"]] == "paper" and kinds[first[0]["id"]] == "scheme"
    assert auth.get(f"/api/pages/{first[0]['id']}").status_code == 200
    # replacing the scheme leaves the paper alone, and vice versa
    second = auth.post(f"/api/assignments/{t['id']}/scheme", files=[("files", ("s3.png", _png(), "image/png"))]).json()["pages"]
    got = auth.get("/api/assignments").json()[0]
    assert got["scheme_page_ids"] == [second[0]["id"]] and got["paper_page_ids"] == [paper[0]["id"]]
    paper2 = auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("p2.png", _png(), "image/png"))]).json()["pages"]
    got = auth.get("/api/assignments").json()[0]
    assert got["scheme_page_ids"] == [second[0]["id"]] and got["paper_page_ids"] == [paper2[0]["id"]]
    assert auth.post("/api/assignments/9999/scheme", files=[("files", ("p.png", _png(), "image/png"))]).status_code == 404
    r = auth.post(f"/api/assignments/{t['id']}/scheme", files=[("files", ("notes.txt", b"hi", "text/plain"))])
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_upload"
    # a duplicate carries both kinds of page
    copy = auth.post(f"/api/assignments/{t['id']}/duplicate").json()
    assert len(copy["paper_page_ids"]) == 1 and len(copy["scheme_page_ids"]) == 1


def test_extract_paper_enqueues_once_then_409(auth, app):
    t = _create(auth, scheme_kind="mark_scheme").json()
    r = auth.post(f"/api/assignments/{t['id']}/extract/paper")
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_paper"
    auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("p1.png", _png(), "image/png"))])
    r = auth.post(f"/api/assignments/{t['id']}/extract/paper")
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    job = app.state.db.query("SELECT kind, payload_json, dedupe_key, status FROM jobs WHERE id = :id", {"id": job_id})[0]
    assert job["kind"] == "paper_extract" and json.loads(job["payload_json"]) == {"template_id": t["id"]}
    assert job["dedupe_key"] == f"paper:{t['id']}" and job["status"] == "queued"
    r = auth.post(f"/api/assignments/{t['id']}/extract/paper")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_running"
    assert auth.post("/api/assignments/9999/extract/paper").status_code == 404
    assert auth.post(f"/api/assignments/{t['id']}/extract/nope").status_code == 404


def test_extract_scheme_needs_type_and_scheme_pages(auth, app):
    t = _create(auth).json()  # criteria
    auth.post(f"/api/assignments/{t['id']}/scheme", files=[("files", ("s1.png", _png(), "image/png"))])
    r = auth.post(f"/api/assignments/{t['id']}/extract/scheme")
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_scheme_kind"
    t2 = _create(auth, title="R", subject="language", scheme_kind="rubric").json()
    r = auth.post(f"/api/assignments/{t2['id']}/extract/scheme")
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_scheme"
    auth.post(f"/api/assignments/{t2['id']}/scheme", files=[("files", ("s1.png", _png(), "image/png"))])
    r = auth.post(f"/api/assignments/{t2['id']}/extract/scheme")
    assert r.status_code == 202
    job = app.state.db.query("SELECT kind, dedupe_key FROM jobs WHERE id = :id", {"id": r.json()["job_id"]})[0]
    assert job["kind"] == "scheme_extract" and job["dedupe_key"] == f"scheme:{t2['id']}"
    assert auth.post(f"/api/assignments/{t2['id']}/extract/scheme").status_code == 409


def test_extract_status_reports_latest_jobs(auth, app):
    t = _create(auth, scheme_kind="mark_scheme").json()
    r = auth.get(f"/api/assignments/{t['id']}/extract")
    assert r.status_code == 200
    assert r.json() == {"paper": {"status": None, "error": None, "job_id": None},
                        "scheme": {"status": None, "error": None, "job_id": None}}
    auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("p1.png", _png(), "image/png"))])
    auth.post(f"/api/assignments/{t['id']}/scheme", files=[("files", ("s1.png", _png(), "image/png"))])
    pj = auth.post(f"/api/assignments/{t['id']}/extract/paper").json()["job_id"]
    sj = auth.post(f"/api/assignments/{t['id']}/extract/scheme").json()["job_id"]
    st = auth.get(f"/api/assignments/{t['id']}/extract").json()
    assert st["paper"] == {"status": "queued", "error": None, "job_id": pj}
    assert st["scheme"] == {"status": "queued", "error": None, "job_id": sj}
    db = app.state.db
    db.execute("UPDATE jobs SET status = 'failed', error = 'No API key configured' WHERE id = :id", {"id": pj})
    db.execute("UPDATE jobs SET status = 'done' WHERE id = :id", {"id": sj})
    st = auth.get(f"/api/assignments/{t['id']}/extract").json()
    assert st["paper"]["status"] == "failed" and "API key" in st["paper"]["error"]
    assert st["scheme"] == {"status": "done", "error": None, "job_id": sj}
    # after a failure a new extract can be queued, and the status follows the newest job
    pj2 = auth.post(f"/api/assignments/{t['id']}/extract/paper").json()["job_id"]
    assert pj2 != pj and auth.get(f"/api/assignments/{t['id']}/extract").json()["paper"]["job_id"] == pj2
    assert auth.get("/api/assignments/9999/extract").status_code == 404


def test_template_model_override_requires_a_saved_key(auth):
    t = _create(auth).json()
    assert t["provider"] is None and t["effective_model"]["provider"] == "tokenrouter"
    r = auth.put(f"/api/assignments/{t['id']}", json={**_body(), "provider": "openai", "model": "gpt-5.5"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_key_for_provider"
    _with_key(auth)   # saves an OpenAI key
    r = auth.put(f"/api/assignments/{t['id']}", json={**_body(), "provider": "openai", "model": "gpt-5.5", "extractor_model": "gpt-5-mini"})
    assert r.status_code == 200 and r.json()["effective_model"] == {"provider": "openai", "model": "gpt-5.5", "extractor_model": "gpt-5-mini"}
    r = auth.put(f"/api/assignments/{t['id']}", json={**_body(), "provider": "openai", "model": ""})
    assert r.json()["model"] == "gpt-5-mini"                      # blank model -> provider default
    r = auth.put(f"/api/assignments/{t['id']}", json={**_body(), "provider": ""})
    assert r.json()["provider"] is None and r.json()["model"] is None
    assert auth.put(f"/api/assignments/{t['id']}", json={**_body(), "provider": "nope", "model": "x"}).json()["error"]["code"] == "bad_provider"

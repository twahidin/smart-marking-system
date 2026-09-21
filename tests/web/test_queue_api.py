import concurrent.futures
import json

from sms.web.errors import ApiError
from sms.web.services.queue import resolve_queue_item

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2},
                              {"id": "c2", "description": "answer", "max_score": 3}]}


def _seed(app):
    db = app.state.db
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status, run_id) "
                    "VALUES ('Tan', 'math', '', :r, 'needs_you', 'r1') RETURNING id", {"r": json.dumps(RUBRIC)})
    db.execute("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height) VALUES (?, 0, 'h', 'pages/h.jpg', 1, 1)", (sid,))
    marks = {"marks": [{"q_id": "q2", "criterion_scores": [1, 1], "total": 2, "confidence": 0.3, "rationale": "hmm", "evidence": "x=2"}]}
    extracted = {"questions": [{"q_id": "q2", "transcribed_answer": "x = 2", "workings": "2x=4", "confidence": 0.5, "needs_human_transcription": False}]}
    reviewed = {"verdicts": [{"q_id": "q2", "verdict": "ESCALATE", "reviewer_note": "method unclear"}], "final_marks": [], "disagreement_flags": []}
    db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, marks_json, final_marks_json, reviewed_json, submission_id, final_status) "
               "VALUES ('r1', 'complete', 'math', ?, ?, ?, ?, ?, ?, 'escalated')",
               (json.dumps(RUBRIC), json.dumps(extracted), json.dumps(marks), json.dumps(marks), json.dumps(reviewed), sid))
    qid = db.insert("INSERT INTO teacher_queue (run_id, q_id, reason, status, submission_id) VALUES ('r1', 'q2', 'reviewer escalated', 'pending', :s) RETURNING id", {"s": sid})
    return sid, qid


def test_queue_requires_auth(client):
    assert client.get("/api/queue").status_code == 401


def test_queue_lists_joined_item(auth, app):
    sid, qid = _seed(app)
    items = auth.get("/api/queue").json()
    assert len(items) == 1
    it = items[0]
    assert it["id"] == qid and it["submission_label"] == "Tan" and it["transcription"] == "x = 2"
    assert it["proposed_criterion_scores"] == [1, 1] and it["reviewer_note"] == "method unclear"
    assert it["criterion_defs"][0]["id"] == "c1" and it["page_ids"] and it["reason"] == "reviewer escalated"
    assert it["reason_text"] == "Marker and reviewer disagreed"
    assert it["input_kind"] == "pages"


def test_queue_item_of_a_files_only_script_says_so_instead_of_offering_pages(auth, app):
    """A .py hand-in has no page to crop, so the reviewer reads the transcription — and must not be
    told the pages were deleted after marking."""
    sid, qid = _seed(app)
    db = app.state.db
    db.execute("UPDATE submissions SET input_kind = 'files' WHERE id = :s", {"s": sid})
    db.execute("DELETE FROM pages WHERE submission_id = :s", {"s": sid})
    it = auth.get("/api/queue").json()[0]
    assert it["input_kind"] == "files" and it["page_ids"] == [] and it["transcription"] == "x = 2"


def test_resolve_records_correction_and_flips_submission(auth, app):
    sid, qid = _seed(app)
    r = auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [2, 2], "reason": "method fine"})
    assert r.status_code == 200 and r.json()["submission_status"] == "done"
    db = app.state.db
    c = db.query("SELECT agent_mark, teacher_mark, criterion_scores_json, reason FROM teacher_corrections")[0]
    assert (c["agent_mark"], c["teacher_mark"], c["reason"]) == (2, 4, "method fine")
    assert json.loads(c["criterion_scores_json"]) == [2, 2]
    assert db.query("SELECT status FROM teacher_queue")[0]["status"] == "resolved"
    assert auth.get("/api/queue").json() == []
    d = auth.get(f"/api/submissions/{sid}").json()
    assert d["marks"][0]["teacher_scores"] == [2, 2] and d["totals"]["total"] == 4


def test_resolve_validates_scores(auth, app):
    _, qid = _seed(app)
    assert auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [9, 0], "reason": ""}).status_code == 400
    assert auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [1], "reason": ""}).status_code == 400


def test_resolve_twice_404(auth, app):
    _, qid = _seed(app)
    auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [1, 1], "reason": ""})
    assert auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [1, 1], "reason": ""}).status_code == 404


def test_resolve_is_race_safe_under_concurrent_requests(auth, app):
    sid, qid = _seed(app)
    db = app.state.db
    r = auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [1, 1], "reason": "first"})
    assert r.status_code == 200
    db.execute("UPDATE teacher_queue SET status = 'pending' WHERE id = :id", {"id": qid})

    def _resolve(_):
        try:
            return ("ok", resolve_queue_item(db, qid, [1, 1], "", storage=app.state.storage))
        except ApiError as e:
            return ("error", e.status)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(_resolve, range(2)))

    outcomes = [kind for kind, _ in results]
    assert outcomes.count("ok") == 1
    assert outcomes.count("error") == 1
    assert [payload for kind, payload in results if kind == "error"] == [404]
    assert len(db.query("SELECT id FROM teacher_corrections")) == 2


def test_learning_endpoints(auth, app):
    db = app.state.db
    nid = db.insert("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'units matter', 'draft') RETURNING id")
    eid = db.insert("INSERT INTO exemplar_cases (subject, topic, q_id, answer_text, awarded, max_score, why_it_matters, status) "
                    "VALUES ('math', 'algebra', 'q1', 'x=3', 2, 2, 'clean', 'draft') RETURNING id")
    assert auth.get("/api/notes").json()[0]["status"] == "draft"
    assert auth.post(f"/api/notes/{nid}/approve").json()["status"] == "active"
    assert auth.post(f"/api/exemplars/{eid}/approve").json()["status"] == "active"
    assert auth.get("/api/exemplars").json()[0]["status"] == "active"
    stats = auth.get("/api/stats").json()
    assert set(stats) == {"extractor", "marker", "reviewer", "feedback", "reflection"}


# --- version 2 (per-part) items ---------------------------------------------------------------

from tests.web.seed_v2 import seed_v2  # noqa: E402


def test_queue_v2_item_carries_the_scheme_row_and_the_proposed_part(auth, app):
    sid, qids = seed_v2(app)
    items = auth.get("/api/queue").json()
    assert len(items) == 1
    it = items[0]
    assert it["id"] == qids["2"] and it["submission_id"] == sid and it["marks_version"] == 2
    assert it["q_id"] == "2" and it["label"] == "2" and it["question_text"] == "Expand (x+1)^2" and it["reason"] == "not in scheme"
    assert it["reason_text"] == "Answer not in the scheme — different method"
    assert it["scheme_row"]["answer"] == "x^2 + 2x + 1" and [m["label"] for m in it["scheme_row"]["marks"]] == ["M1", "A1"]
    assert it["proposed"]["q_id"] == "2" and it["proposed"]["total"] == 1 and it["proposed"]["in_scheme"] is False
    assert it["proposed"]["awarded"][0] == {"label": "M1", "marks": 1, "got": True, "why": ""}
    assert it["transcription"] == "x^2 + 2x + 1" and it["workings"] == "(x+1)(x+1)"
    assert it["reviewer_note"] == "unsure about 2" and it["page_ids"] and it["submission_label"] == "Tan"
    assert it["proposed_total"] == 1 and it["proposed_criterion_scores"] == [] and it["criterion_defs"] == []


def test_resolve_v2_with_allocations_records_the_v2_correction_and_flips_the_submission(auth, app):
    sid, qids = seed_v2(app)
    r = auth.post(f"/api/queue/{qids['2']}/resolve",
                  json={"allocations": [{"label": "M1", "got": True}, {"label": "A1", "got": True}], "reason": "method valid"})
    assert r.status_code == 200 and r.json()["submission_status"] == "done"
    c = app.state.db.query("SELECT agent_mark, teacher_mark, criterion_scores_json, reason FROM teacher_corrections")[0]
    assert (c["agent_mark"], c["teacher_mark"], c["reason"]) == (1, 3, "method valid")
    assert json.loads(c["criterion_scores_json"]) == {
        "version": 2, "allocations": [{"label": "M1", "got": True, "marks": 1}, {"label": "A1", "got": True, "marks": 2}], "total": 3}
    assert auth.get("/api/queue").json() == []
    d = auth.get(f"/api/submissions/{sid}").json()
    p2 = d["parts"][2]
    assert p2["escalated"] is False and p2["teacher"] == {"allocations": [{"label": "M1", "got": True, "marks": 1},
                                                                          {"label": "A1", "got": True, "marks": 2}], "total": 3}
    assert d["totals"] == {"total": 5, "total_upper": 5, "total_max": 6} and d["status"] == "done"
    # allocations left out are recorded as lost: only the labels sent count
    sid2, qids2 = seed_v2(app, label="Lim", run_id="r3")
    r = auth.post(f"/api/queue/{qids2['2']}/resolve", json={"allocations": [{"label": " A1 ", "got": True}], "reason": ""})
    assert r.status_code == 200
    d = auth.get(f"/api/submissions/{sid2}").json()
    assert d["parts"][2]["teacher"]["allocations"] == [{"label": "M1", "got": False, "marks": 1}, {"label": "A1", "got": True, "marks": 2}]
    assert d["parts"][2]["teacher"]["total"] == 2


def test_resolve_v2_validates_against_the_scheme_row(auth, app):
    _, qids = seed_v2(app)
    q = qids["2"]
    r = auth.post(f"/api/queue/{q}/resolve", json={"allocations": [{"label": "Z9", "got": True}], "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_allocations" and "Z9" in r.json()["error"]["message"]
    r = auth.post(f"/api/queue/{q}/resolve", json={"allocations": [{"label": "M1", "got": True}, {"label": "M1", "got": False}], "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_allocations"
    r = auth.post(f"/api/queue/{q}/resolve", json={"criterion_scores": [1, 1], "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_allocations"
    r = auth.post(f"/api/queue/{q}/resolve", json={"band": "A", "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_allocations"
    assert auth.get("/api/queue").json()[0]["id"] == q  # still pending
    # a v1 item does not take allocations
    _, v1_qid = _seed(app)
    r = auth.post(f"/api/queue/{v1_qid}/resolve", json={"allocations": [{"label": "M1", "got": True}], "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_scores"


def test_resolve_v2_rubric_with_a_band(auth, app):
    sid, qids = seed_v2(app, kind="rubric")
    it = auth.get("/api/queue").json()[0]
    assert it["marks_version"] == 2 and it["q_id"] == "Language" and it["scheme_row"]["criterion"] == "Language"
    assert it["proposed"]["band"] == "B" and it["proposed"]["marks"] == 2
    r = auth.post(f"/api/queue/{qids['Language']}/resolve", json={"band": "Z", "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_band"
    r = auth.post(f"/api/queue/{qids['Language']}/resolve", json={"band": "A", "reason": "fine"})
    assert r.status_code == 200 and r.json()["submission_status"] == "done"
    c = app.state.db.query("SELECT agent_mark, teacher_mark, criterion_scores_json FROM teacher_corrections")[0]
    assert (c["agent_mark"], c["teacher_mark"]) == (2, 5) and json.loads(c["criterion_scores_json"]) == {"version": 2, "band": "A", "marks": 5}
    d = auth.get(f"/api/submissions/{sid}").json()
    assert d["parts"][1]["teacher"] == {"band": "A", "marks": 5, "total": 5} and d["totals"] == {"total": 10, "total_upper": 10, "total_max": 10}


# --- deleting student pages on the last resolve ----------------------------------------------------

def _real_page(app, sid, content=b"\xff\xd8\xffjpeg", index=0):
    digest, rel = app.state.storage.put_jpeg(content)
    pid = app.state.db.insert("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height) "
                              "VALUES (:s, :i, :h, :p, 1, 1) RETURNING id", {"s": sid, "i": index, "h": digest, "p": rel})
    return pid, rel


def test_last_resolve_deletes_student_pages(auth, app):
    sid, qid = _seed(app)
    app.state.db.execute("DELETE FROM pages WHERE submission_id = :s", {"s": sid})
    pid, rel = _real_page(app, sid)
    r = auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [2, 2], "reason": ""})
    assert r.status_code == 200 and r.json()["submission_status"] == "done"
    assert auth.get(f"/api/pages/{pid}").status_code == 410
    assert not app.state.storage.abs(rel).exists()
    assert auth.get(f"/api/submissions/{sid}").json()["pages_deleted"] is True


def test_resolve_with_parts_still_pending_keeps_pages(auth, app):
    sid, qids = seed_v2(app, queue={"1b": "low confidence", "2": "not in scheme"})
    app.state.db.execute("DELETE FROM pages WHERE submission_id = :s", {"s": sid})
    pid, rel = _real_page(app, sid)
    r = auth.post(f"/api/queue/{qids['2']}/resolve", json={"allocations": [{"label": "M1", "got": True}, {"label": "A1", "got": False}]})
    assert r.status_code == 200 and r.json()["submission_status"] == "needs_you"
    assert auth.get(f"/api/pages/{pid}").status_code == 200 and app.state.storage.abs(rel).exists()
    r = auth.post(f"/api/queue/{qids['1b']}/resolve", json={"allocations": [{"label": "B1", "got": True}]})
    assert r.status_code == 200 and r.json()["submission_status"] == "done"
    assert auth.get(f"/api/pages/{pid}").status_code == 410 and not app.state.storage.abs(rel).exists()


def test_last_resolve_respects_the_delete_flag(auth, app):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 60,
                                    "confidence_threshold": 0, "delete_pages_after_marking": False})
    sid, qid = _seed(app)
    app.state.db.execute("DELETE FROM pages WHERE submission_id = :s", {"s": sid})
    pid, rel = _real_page(app, sid)
    r = auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [2, 2], "reason": ""})
    assert r.json()["submission_status"] == "done"
    assert auth.get(f"/api/pages/{pid}").status_code == 200 and app.state.storage.abs(rel).exists()


def test_concurrent_resolves_of_two_parts_converge_on_done(auth, app):
    """Two teachers resolve different pending parts of one script at the same moment: the script must
    end `done` (never stuck at `needs_you` with an empty queue), with one correction per part and its
    pages deleted."""
    sid, qids = seed_v2(app, queue={"1b": "low confidence", "2": "not in scheme"})
    db = app.state.db
    db.execute("DELETE FROM pages WHERE submission_id = :s", {"s": sid})
    pid, rel = _real_page(app, sid)
    bodies = {qids["2"]: [{"label": "M1", "got": True}, {"label": "A1", "got": False}],
              qids["1b"]: [{"label": "B1", "got": True}]}

    def _resolve(qid):
        return resolve_queue_item(db, qid, None, "", storage=app.state.storage, allocations=bodies[qid])

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(_resolve, list(bodies)))
    statuses = [r["submission_status"] for r in results]
    assert "done" in statuses and set(statuses) <= {"done", "needs_you"}  # the later one always sees done
    assert db.query("SELECT status FROM submissions WHERE id = :s", {"s": sid})[0]["status"] == "done"
    assert db.query("SELECT COUNT(*) AS c FROM teacher_corrections")[0]["c"] == 2
    assert db.query("SELECT COUNT(*) AS c FROM teacher_queue WHERE status = 'pending'")[0]["c"] == 0
    assert auth.get(f"/api/pages/{pid}").status_code == 410 and not app.state.storage.abs(rel).exists()
    assert auth.get("/api/queue").json() == []


def test_resolve_heals_a_script_stuck_at_needs_you(auth, app):
    """A lost update left the script `needs_you` although only one part is still pending: resolving
    that part reports `done` from a fresh read and deletes the pages."""
    sid, qids = seed_v2(app, queue={"1b": "low confidence", "2": "not in scheme"})
    db = app.state.db
    db.execute("DELETE FROM pages WHERE submission_id = :s", {"s": sid})
    pid, rel = _real_page(app, sid)
    db.execute("UPDATE teacher_queue SET status = 'resolved' WHERE id = :id", {"id": qids["2"]})
    r = auth.post(f"/api/queue/{qids['1b']}/resolve", json={"allocations": [{"label": "B1", "got": True}]})
    assert r.status_code == 200 and r.json()["submission_status"] == "done"
    assert auth.get(f"/api/pages/{pid}").status_code == 410 and not app.state.storage.abs(rel).exists()


# --- parts the scheme cannot account for: the resolve must still be possible ---------------------

def test_resolve_rubric_criterion_not_in_scheme_accepts_the_proposed_band(auth, app):
    """A criterion the marker invented has no rubric row, so no band can validate against it: the
    proposed band is accepted with the marker's marks (or 0), and the script is not stuck at needs_you."""
    invented = {"criterion": "Flair", "band": "B", "marks": 3, "descriptor_met": "", "justification": "Stylish", "confidence": 0.7}
    rubric = [{"criterion": "Content", "band": "A", "marks": 5, "descriptor_met": "", "justification": "", "confidence": 0.9},
              {"criterion": "Language", "band": "A", "marks": 5, "descriptor_met": "", "justification": "", "confidence": 0.9}, invented]
    sid, qids = seed_v2(app, kind="rubric", rubric=rubric, queue={"Flair": "not in scheme"})
    it = auth.get("/api/queue").json()[0]
    assert it["q_id"] == "Flair" and it["scheme_row"] is None and it["proposed"]["band"] == "B" and it["proposed_total"] == 3
    r = auth.post(f"/api/queue/{qids['Flair']}/resolve", json={"band": "  ", "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_band"
    r = auth.post(f"/api/queue/{qids['Flair']}/resolve", json={"band": "B", "marks": 9, "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_band"
    r = auth.post(f"/api/queue/{qids['Flair']}/resolve", json={"band": "B", "reason": "fair"})
    assert r.status_code == 200 and r.json()["submission_status"] == "done"
    c = app.state.db.query("SELECT agent_mark, teacher_mark, criterion_scores_json FROM teacher_corrections")[0]
    assert (c["agent_mark"], c["teacher_mark"]) == (3, 3) and json.loads(c["criterion_scores_json"]) == {"version": 2, "band": "B", "marks": 3}
    d = auth.get(f"/api/submissions/{sid}").json()
    assert d["status"] == "done" and d["parts"][2]["teacher"] == {"band": "B", "marks": 3, "total": 3}
    # a criterion whose rubric row has no bands behaves the same, and 0 can be awarded instead
    sid2, qids2 = seed_v2(app, kind="rubric", label="Lim", run_id="r4", rubric=rubric[:2] + [invented],
                          scheme=RUBRIC_NO_BANDS, queue={"Flair": "low confidence"})
    r = auth.post(f"/api/queue/{qids2['Flair']}/resolve", json={"band": "B", "marks": 0, "reason": ""})
    assert r.status_code == 200 and r.json()["submission_status"] == "done"
    c = app.state.db.query("SELECT teacher_mark, criterion_scores_json FROM teacher_corrections WHERE run_id = 'r4'")[0]
    assert c["teacher_mark"] == 0 and json.loads(c["criterion_scores_json"]) == {"version": 2, "band": "B", "marks": 0}
    # a criterion that IS in the rubric still validates the band and ignores `marks`
    sid3, qids3 = seed_v2(app, kind="rubric", label="Ng", run_id="r5")
    r = auth.post(f"/api/queue/{qids3['Language']}/resolve", json={"band": "A", "marks": 0, "reason": ""})
    assert r.status_code == 200
    c = app.state.db.query("SELECT teacher_mark FROM teacher_corrections WHERE run_id = 'r5'")[0]
    assert c["teacher_mark"] == 5


RUBRIC_NO_BANDS = [{"criterion": "Content", "bands": [{"band": "A", "marks": 5, "descriptor": ""}]},
                   {"criterion": "Language", "bands": [{"band": "A", "marks": 5, "descriptor": ""}]},
                   {"criterion": "Flair", "bands": []}]


def test_resolve_mark_scheme_part_with_no_allocations_takes_a_total(auth, app):
    """A part with nothing to tick (no scheme row and a proposal without allocations, or a row with no
    allocations) is resolved with {"total": n}, 0 <= n <= the row max or the proposed total."""
    from tests.web.seed_v2 import DEFAULT_PARTS, part
    parts = DEFAULT_PARTS[:2] + [part("3", [], 2, "Bonus question", in_scheme=False, confidence=0.6)]
    sid, qids = seed_v2(app, parts=parts, queue={"3": "not in scheme"})
    it = auth.get("/api/queue").json()[0]
    assert it["q_id"] == "3" and it["scheme_row"] is None and it["proposed"]["awarded"] == [] and it["proposed_total"] == 2
    r = auth.post(f"/api/queue/{qids['3']}/resolve", json={"total": 3, "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_allocations"
    r = auth.post(f"/api/queue/{qids['3']}/resolve", json={"total": -1, "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_allocations"
    r = auth.post(f"/api/queue/{qids['3']}/resolve", json={"total": 1, "reason": "half"})
    assert r.status_code == 200 and r.json()["submission_status"] == "done"
    c = app.state.db.query("SELECT agent_mark, teacher_mark, criterion_scores_json FROM teacher_corrections")[0]
    assert (c["agent_mark"], c["teacher_mark"]) == (2, 1) and json.loads(c["criterion_scores_json"]) == {"version": 2, "allocations": [], "total": 1}
    d = auth.get(f"/api/submissions/{sid}").json()
    assert d["parts"][3]["q_id"] == "3" and d["parts"][3]["teacher"] == {"allocations": [], "total": 1}
    # a scheme row with no allocations: the row max is 0, so only 0 can be given as a total
    scheme = [{"q_id": "1a", "answer": "x = 3", "marks": [], "notes": ""}]
    sid2, qids2 = seed_v2(app, label="Lim", run_id="r6", scheme=scheme, parts=[part("1a", [], 0, "", confidence=0.2)],
                          queue={"1a": "low confidence"})
    r = auth.post(f"/api/queue/{qids2['1a']}/resolve", json={"total": 1, "reason": ""})
    assert r.status_code == 400
    assert auth.post(f"/api/queue/{qids2['1a']}/resolve", json={"total": 0, "reason": ""}).status_code == 200
    # a part with allocations to tick does not take a bare total
    _, qids3 = seed_v2(app, label="Ng", run_id="r7")
    r = auth.post(f"/api/queue/{qids3['2']}/resolve", json={"total": 1, "reason": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_allocations"

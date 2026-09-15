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
            return ("ok", resolve_queue_item(db, qid, [1, 1], ""))
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

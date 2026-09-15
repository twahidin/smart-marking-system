import io
import json

from PIL import Image

from sms.schemas.marking import Rubric, RubricCriterion
from sms.web.services.submissions import compute_totals

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2},
                              {"id": "c2", "description": "answer", "max_score": 3}]}


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def _create(auth, **over):
    data = {"label": "Tan Wei Ling", "subject": "math", "context": "Worksheet 3", "rubric": json.dumps(RUBRIC)}
    data.update(over)
    return auth.post("/api/submissions", data=data, files=[("files", ("p1.png", _png(), "image/png"))])


def test_requires_auth(client):
    assert client.get("/api/submissions").status_code == 401


def test_create_without_key_400(auth):
    r = _create(auth)
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_key"


def _with_key(auth):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x",
                                    "rpm_limit": 60, "confidence_threshold": 0})
    return auth


def test_create_returns_202_and_queues_job(auth):
    r = _create(_with_key(auth))
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and len(body["pages"]) == 1
    lst = auth.get("/api/submissions").json()
    assert lst[0]["id"] == body["id"] and lst[0]["page_count"] == 1 and lst[0]["status"] == "queued"
    detail = auth.get(f"/api/submissions/{body['id']}").json()
    assert detail["job"]["status"] == "queued" and detail["marks"] == [] and detail["feedback"] is None


def test_create_bad_rubric_400(auth):
    r = _create(_with_key(auth), rubric="{}")
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_rubric"


def test_create_bad_file_names_it(auth):
    auth = _with_key(auth)
    r = auth.post("/api/submissions", data={"label": "x", "subject": "math", "context": "", "rubric": json.dumps(RUBRIC)},
                  files=[("files", ("notes.txt", b"hi", "text/plain"))])
    assert r.status_code == 400 and "notes.txt" in r.json()["error"]["message"]


def test_page_route_authenticated_and_serves_jpeg(auth, client):
    body = _create(_with_key(auth)).json()
    pid = body["pages"][0]["id"]
    r = auth.get(f"/api/pages/{pid}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    client.cookies.clear()
    assert client.get(f"/api/pages/{pid}").status_code == 401


def test_retry_only_when_failed(auth, app):
    body = _create(_with_key(auth)).json()
    assert auth.post(f"/api/submissions/{body['id']}/retry").status_code == 409
    app.state.db.execute("UPDATE jobs SET status = 'failed'"); app.state.db.execute("UPDATE submissions SET status = 'failed'")
    assert auth.post(f"/api/submissions/{body['id']}/retry").status_code == 202
    assert auth.get(f"/api/submissions/{body['id']}").json()["status"] == "queued"


def test_detail_after_run_includes_marks_escalations_feedback(auth, app):
    body = _create(_with_key(auth)).json()
    sid = body["id"]
    db = app.state.db
    final = {"marks": [{"q_id": "q1", "criterion_scores": [2, 3], "total": 5, "confidence": 0.9, "rationale": "r", "evidence": "e"},
                       {"q_id": "q2", "criterion_scores": [1, 1], "total": 2, "confidence": 0.3, "rationale": "r2", "evidence": "e2"}]}
    feedback = {"summary": "s", "strengths": ["a"], "per_question_comments": [], "improvement_plan": [], "next_steps": []}
    db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, marks_json, final_marks_json, feedback_json, "
               "reviewed_json, submission_id, final_status) VALUES ('r1', 'complete', 'math', ?, ?, ?, ?, ?, ?, 'escalated')",
               (json.dumps(RUBRIC), json.dumps(final), json.dumps(final), json.dumps(feedback),
                json.dumps({"verdicts": [{"q_id": "q2", "verdict": "ESCALATE", "reviewer_note": "unsure"}], "final_marks": [], "disagreement_flags": []}), sid))
    db.execute("INSERT INTO teacher_queue (run_id, q_id, reason, status, submission_id) VALUES ('r1', 'q2', 'low marker confidence', 'pending', ?)", (sid,))
    db.execute("UPDATE submissions SET status = 'needs_you', run_id = 'r1' WHERE id = ?", (sid,))
    d = auth.get(f"/api/submissions/{sid}").json()
    assert d["status"] == "needs_you" and d["feedback"]["summary"] == "s"
    q2 = next(m for m in d["marks"] if m["q_id"] == "q2")
    assert q2["escalated"] and q2["reason"] == "low marker confidence" and q2["queue_id"] and q2["max"] == 5
    assert d["totals"] == {"total": 7, "total_upper": 10, "total_max": 10}
    lst = auth.get("/api/submissions").json()[0]
    assert lst["total"] == 7 and lst["total_upper"] == 10 and lst["needs_you_qids"] == ["q2"]


def test_compute_totals_pure():
    rubric = Rubric(criterion_defs=[RubricCriterion(id="c1", description="d", max_score=2),
                                    RubricCriterion(id="c2", description="d", max_score=3)])
    final = [{"q_id": "q1", "total": 4}, {"q_id": "q2", "total": 1}]
    t = compute_totals(rubric, final, pending_qids={"q2"}, corrections={})
    assert t == {"total": 5, "total_upper": 9, "total_max": 10}
    t = compute_totals(rubric, final, pending_qids=set(), corrections={"q2": [2, 2]})
    assert t == {"total": 8, "total_upper": 8, "total_max": 10}

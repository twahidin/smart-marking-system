import json

from sms.web.services.class_assignments import get_class_assignment
from sms.web.services.insights import compute_stats, dedupe_key, load_insights, upsert_insights

from tests.web.seed_v2 import QUESTIONS as V2_QUESTIONS, SCHEME as V2_SCHEME, seed_v2
from tests.web.test_class_assignments_api import _class_with_students, _link, _template, _with_key
from tests.web.test_insights_stats import _seed_class

REPORT = {"summary": "The class secured 1(a); follow-through in 1(b) is the gap.",
          "strengths": ["Rearranging is secure"],
          "gaps": [{"part_ids": ["1b"], "title": "Hence questions", "what_went_wrong": "Did not reuse 1(a)",
                    "students_affected": 1}],
          "recommendations": [{"title": "Reteach follow-through", "detail": "Use 1(b)", "part_ids": ["1b"]}],
          "students_to_support": [{"reg_nos": [1], "focus": "follow-through"}]}


def _insights_jobs(app, caid):
    return app.state.db.query("SELECT * FROM jobs WHERE dedupe_key = :d ORDER BY id", {"d": dedupe_key(caid)})


def _seed_one_marked(auth, app):
    t = _template(auth, questions=V2_QUESTIONS, scheme=V2_SCHEME)
    c = _class_with_students(auth, names=("Tan Wei Ling", "Muhammad Danish"))
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    sid, _ = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    _link(app, sid, ca["id"], c["students"][0]["id"])
    return c, ca


def test_insights_endpoint_returns_live_stats_before_any_report(auth, app):
    c, ca = _seed_one_marked(auth, app)
    r = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/insights")
    assert r.status_code == 200
    body = r.json()
    assert body["report"] is None and body["stats"]["n_marked"] == 1 and body["job"] is None
    assert body["generated_at"] is None and body["provider"] is None and body["error"] is None
    assert auth.get(f"/api/classes/{c['id']}/assignments/999/insights").status_code == 404


def test_insights_endpoint_returns_the_stored_report_and_any_running_job(auth, app):
    c, ca = _seed_one_marked(auth, app)
    db = app.state.db
    upsert_insights(db, ca["id"], stats={"n_marked": 1, "parts": []}, report={"headline": "Expansion is the gap"},
                    n_marked=1, provider="openai", model="gpt-5-mini", error=None)
    assert app.state.jobs.enqueue_unique("insights", {"class_assignment_id": ca["id"]}, f"insights:{ca['id']}")
    body = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/insights").json()
    assert body["report"] == {"headline": "Expansion is the gap"} and body["stats"] == {"n_marked": 1, "parts": []}
    assert (body["provider"], body["model"], body["n_marked"]) == ("openai", "gpt-5-mini", 1)
    assert body["generated_at"].endswith("Z") and body["job"] == {"status": "queued"}
    # a second upsert replaces the row rather than adding one
    upsert_insights(db, ca["id"], stats={"n_marked": 2, "parts": []}, report=None, n_marked=2,
                    provider="openai", model="gpt-5-mini", error="rate limited")
    assert db.query("SELECT COUNT(*) AS c FROM assignment_insights")[0]["c"] == 1
    body = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/insights").json()
    assert body["report"] is None and body["error"] == "rate limited" and body["n_marked"] == 2
    assert load_insights(db, ca["id"])["stats"] == {"n_marked": 2, "parts": []}
    assert load_insights(db, 999) is None


def test_insights_endpoint_needs_a_teacher_session(client, auth, app):
    c, ca = _seed_one_marked(auth, app)
    client.cookies.clear()
    assert client.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/insights").status_code == 401


def test_regenerate_queues_one_insights_job_at_a_time(auth, app):
    _with_key(auth)
    _t, c, ca, _qids = _seed_class(auth, app)
    url = f"/api/classes/{c['id']}/assignments/{ca['id']}/insights/regenerate"
    r = auth.post(url)
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    rows = _insights_jobs(app, ca["id"])
    assert [row["id"] for row in rows] == [job_id]
    assert rows[0]["kind"] == "insights" and rows[0]["status"] == "queued"
    assert json.loads(rows[0]["payload_json"]) == {"class_assignment_id": ca["id"]}
    # while that one is queued, a second request is refused
    r = auth.post(url)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_running"
    # ...and the live payload reports the queued job
    assert auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/insights").json()["job"] == {"status": "queued"}
    # once it is done, regenerating is allowed again
    app.state.jobs.finish(job_id)
    assert auth.post(url).status_code == 202
    assert len(_insights_jobs(app, ca["id"])) == 2
    assert auth.post(f"/api/classes/{c['id']}/assignments/999/insights/regenerate").status_code == 404


def test_regenerate_is_refused_when_nothing_is_marked(auth, app):
    _with_key(auth)
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/insights/regenerate")
    assert r.status_code == 409 and r.json()["error"]["code"] == "nothing_marked"
    assert _insights_jobs(app, ca["id"]) == []


def test_insights_pdf_downloads_with_and_without_a_narrative(auth, app):
    _with_key(auth)
    _t, c, ca, _qids = _seed_class(auth, app)
    r = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/insights.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert 'filename="quadratics-worksheet-3-insights.pdf"' in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF" and len(r.content) > 2000
    stats_only = len(r.content)
    # with a stored narrative the same URL carries it too
    row = get_class_assignment(app.state.db, c["id"], ca["id"])
    upsert_insights(app.state.db, ca["id"], stats=compute_stats(app.state.db, app.state.jobs, row),
                    report=REPORT, n_marked=2, provider="openai", model="gpt-5-mini", error=None)
    r = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/insights.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > stats_only
    assert auth.get(f"/api/classes/{c['id']}/assignments/999/insights.pdf").status_code == 404


def test_release_enqueues_insights(auth, app):
    _with_key(auth)
    _t, c, ca, qids = _seed_class(auth, app)
    auth.post(f"/api/queue/{qids['2']}/resolve",
              json={"allocations": [{"label": "M1", "got": True}, {"label": "A1", "got": False}], "reason": "ok"})
    assert _insights_jobs(app, ca["id"]) == []
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release")
    assert r.status_code == 200 and r.json()["status"] == "released"
    rows = _insights_jobs(app, ca["id"])
    assert len(rows) == 1 and rows[0]["kind"] == "insights" and rows[0]["status"] == "queued"

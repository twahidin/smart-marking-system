from sms.web.services.insights import load_insights, upsert_insights

from tests.web.seed_v2 import QUESTIONS as V2_QUESTIONS, SCHEME as V2_SCHEME, seed_v2
from tests.web.test_class_assignments_api import _class_with_students, _link, _template


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

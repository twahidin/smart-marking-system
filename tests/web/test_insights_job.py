"""run_insights_job: what the model is shown (never a name), what is stored, and what a failed call
leaves behind. Web fixtures because the seeding goes through the API (`app` builds the schema)."""
import json

import pytest

from sms.schemas.insights import Gap, InsightsReport, Recommendation, Support
from sms.web.services.insights import dedupe_key
from sms.worker.insights_job import enqueue_insights, run_insights_job

from tests.web.test_class_assignments_api import _class_with_students, _template, _with_key
from tests.web.test_insights_stats import _seed_class

REPORT = InsightsReport(
    summary="Class did well on 1(a).",
    strengths=["Method in 1(a)"],
    gaps=[Gap(part_ids=["1b"], title="Hence questions", what_went_wrong="Did not reuse 1(a)", students_affected=1)],
    recommendations=[Recommendation(title="Reteach follow-through", detail="Use 1(b)", part_ids=["1b"])],
    students_to_support=[Support(reg_nos=[1], focus="follow-through")],
)


def _row(app, ca_id):
    return app.state.db.query("SELECT * FROM assignment_insights WHERE class_assignment_id = :c", {"c": ca_id})[0]


def test_insights_job_strips_names_and_stores_report(auth, app):
    _with_key(auth)
    _t, _c, ca, _qids = _seed_class(auth, app)
    ca_id = ca["id"]
    captured = {}

    class FakeAgent:
        def run(self, inp):
            captured["input"] = inp
            return REPORT

    out = run_insights_job(app.state.db, app.state.jobs, app.state.settings_store, ca_id,
                           agent_factory=lambda **kw: FakeAgent())
    assert out["summary"].startswith("Class did well")
    inp = captured["input"]
    assert inp.assignment_title == ca["title"] and inp.subject == "math" and inp.scheme_kind == "mark_scheme"
    dumped = inp.model_dump_json()
    assert "Tan Wei Ling" not in dumped and "Muhammad" not in dumped
    assert '"reg_no": 1' in dumped.replace('"reg_no":1', '"reg_no": 1')
    assert all("name" not in s and "student_id" not in s for s in inp.stats["students"])
    assert inp.samples and all(s.part in {p["q_id"] for p in inp.stats["parts"]} for s in inp.samples)
    row = _row(app, ca_id)
    assert json.loads(row["report_json"])["summary"].startswith("Class did well")
    assert row["n_marked"] == 2 and row["error"] is None
    assert row["provider"] == "openai" and row["model"] == "gpt-5-mini"
    assert json.loads(row["stats_json"])["n_marked"] == 2

    # a failing model call keeps the previous report and records the error
    class Boom:
        def run(self, inp):
            raise RuntimeError("model down")

    with pytest.raises(RuntimeError):
        run_insights_job(app.state.db, app.state.jobs, app.state.settings_store, ca_id,
                         agent_factory=lambda **kw: Boom())
    row = _row(app, ca_id)
    assert row["error"] == "model down" and json.loads(row["report_json"])["summary"].startswith("Class did well")
    assert row["n_marked"] == 2


def test_insights_job_with_nothing_marked_records_the_reason_and_calls_no_model(auth, app):
    _with_key(auth)
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()

    def no_model(**_kw):
        pytest.fail("the model must not be called with nothing marked")

    stats = run_insights_job(app.state.db, app.state.jobs, app.state.settings_store, ca["id"],
                             agent_factory=no_model)
    assert stats["n_marked"] == 0
    row = _row(app, ca["id"])
    assert row["error"] == "Nothing marked yet" and row["report_json"] is None and row["n_marked"] == 0


def test_insights_job_needs_a_key_and_a_real_assignment(auth, app):
    _t, _c, ca, _qids = _seed_class(auth, app)
    with pytest.raises(RuntimeError, match="API key"):
        run_insights_job(app.state.db, app.state.jobs, app.state.settings_store, ca["id"])
    with pytest.raises(ValueError, match="not found"):
        run_insights_job(app.state.db, app.state.jobs, app.state.settings_store, 9999)


def test_enqueue_insights_is_one_at_a_time_per_assignment(app):
    jobs = app.state.jobs
    first = enqueue_insights(jobs, 7)
    assert first is not None and enqueue_insights(jobs, 7) is None
    assert enqueue_insights(jobs, 8) is not None
    row = app.state.db.query("SELECT kind, payload_json, dedupe_key FROM jobs WHERE id = :i", {"i": first})[0]
    assert row["kind"] == "insights" and row["dedupe_key"] == dedupe_key(7)
    assert json.loads(row["payload_json"]) == {"class_assignment_id": 7}

def _corrections(app, subject="math", run_id="r1"):
    db = app.state.db
    db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, final_status) VALUES (?, 'complete', ?, '{}', 'complete')",
               (run_id, subject))
    db.execute("INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason) VALUES (?, 'q1', 1, 2, 'x')", (run_id,))


def test_reflect_requires_auth(client):
    assert client.post("/api/reflect", json={"subject": "math"}).status_code == 401
    assert client.get("/api/reflect/runs").status_code == 401


def test_post_reflect_enqueues_and_409s_while_pending(auth, app):
    r = auth.post("/api/reflect", json={"subject": "math"})
    assert r.status_code == 202, r.text
    jid = r.json()["job_id"]
    job = app.state.db.query("SELECT kind, status, submission_id, payload_json FROM jobs WHERE id = :id", {"id": jid})[0]
    assert job["kind"] == "reflect" and job["status"] == "queued" and job["submission_id"] is None
    assert '"subject": "math"' in job["payload_json"] and '"lookback_days": 7' in job["payload_json"]
    r = auth.post("/api/reflect", json={"subject": "math", "lookback_days": 14})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_running"
    # another subject is independent, and lookback_days is honoured
    r = auth.post("/api/reflect", json={"subject": "science", "lookback_days": 14})
    assert r.status_code == 202
    assert '"lookback_days": 14' in app.state.db.query("SELECT payload_json FROM jobs WHERE id = :id", {"id": r.json()["job_id"]})[0]["payload_json"]
    runs = auth.get("/api/reflect/runs").json()
    assert runs["runs"] == [] and sorted(runs["pending"]) == ["math", "science"]


def test_post_reflect_validates(auth):
    assert auth.post("/api/reflect", json={"subject": "art"}).json()["error"]["code"] == "bad_subject"
    assert auth.post("/api/reflect", json={"subject": "math", "lookback_days": 0}).status_code == 400
    assert auth.post("/api/reflect", json={"subject": "math", "lookback_days": 400}).status_code == 400


def test_get_runs_lists_latest_twenty_with_iso_timestamps(auth, app):
    db = app.state.db
    for i in range(22):
        db.execute("INSERT INTO reflection_runs (subject, lookback_days, proposed_notes, finished_at, error) "
                   "VALUES ('math', 7, ?, CURRENT_TIMESTAMP, ?)", (i, "rate limited" if i == 21 else None))
    body = auth.get("/api/reflect/runs").json()
    assert len(body["runs"]) == 20 and body["pending"] == []
    latest = body["runs"][0]
    assert latest["proposed_notes"] == 21 and latest["error"] == "rate limited" and latest["subject"] == "math"
    assert latest["started_at"].endswith("Z") and latest["finished_at"].endswith("Z") and latest["lookback_days"] == 7
    assert body["runs"][-1]["proposed_notes"] == 2


def test_reflect_job_done_clears_pending(auth, app):
    r = auth.post("/api/reflect", json={"subject": "math"})
    app.state.db.execute("UPDATE jobs SET status = 'done' WHERE id = :id", {"id": r.json()["job_id"]})
    assert auth.get("/api/reflect/runs").json()["pending"] == []
    assert auth.post("/api/reflect", json={"subject": "math"}).status_code == 202


def test_settings_expose_auto_reflect(auth):
    assert auth.get("/api/settings").json()["auto_reflect"] is True
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 60,
                                        "confidence_threshold": 0, "auto_reflect": False})
    assert r.status_code == 200 and r.json()["auto_reflect"] is False
    assert auth.get("/api/settings").json()["auto_reflect"] is False
    # omitted -> stays as the default True (body default), matching the SPA always sending it
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 60, "confidence_threshold": 0})
    assert r.json()["auto_reflect"] is True

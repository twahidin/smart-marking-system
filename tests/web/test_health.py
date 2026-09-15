def test_health_without_auth(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok" and "worker_last_seen" in body


def test_spa_fallback_serves_index_when_built(app, tmp_path):
    from fastapi.testclient import TestClient
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Smart Marking</title>")
    app.state.config.static_dir = dist
    from sms.web.app import mount_spa
    mount_spa(app, dist)
    with TestClient(app) as c:
        assert "Smart Marking" in c.get("/submissions/3").text
        assert c.get("/api/nope").status_code == 404

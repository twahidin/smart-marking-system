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


def test_api_404_has_uniform_error_shape(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        r = c.get("/api/nope")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "http_404"


def test_spa_path_traversal_blocked(app, tmp_path):
    from fastapi.testclient import TestClient
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Smart Marking</title>")
    secret = tmp_path / "secret.txt"
    secret.write_text("do not serve me")
    app.state.config.static_dir = dist
    from sms.web.app import mount_spa
    mount_spa(app, dist)
    with TestClient(app) as c:
        for path in ("/%2e%2e/secret.txt", "/..%2fsecret.txt"):
            r = c.get(path)
            assert r.status_code == 200
            assert "Smart Marking" in r.text
            assert "do not serve me" not in r.text

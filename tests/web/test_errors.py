import logging

from fastapi.testclient import TestClient


def test_unhandled_exception_returns_500_error_shape(app, caplog):
    @app.get("/api/_boom")
    def boom():
        raise RuntimeError("secret detail that must not leak")

    # Starlette re-raises server errors after the handler runs; the client must see only the response.
    with TestClient(app, raise_server_exceptions=False) as c, caplog.at_level(logging.ERROR, logger="sms.web.errors"):
        r = c.get("/api/_boom")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal", "message": "Something went wrong"}}
    assert "secret detail" not in r.text
    assert any("Unhandled error on GET /api/_boom" in rec.getMessage() and rec.exc_info for rec in caplog.records)

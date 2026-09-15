from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sms.web.app import create_app
from sms.web.config import AppConfig


@pytest.fixture
def config(tmp_path):
    return AppConfig(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        secret_key="test-secret",
        teacher_password="letmein",
        storage_dir=Path(tmp_path / "data"),
        embedded_worker=False,
        env={},
    )


@pytest.fixture
def app(config):
    return create_app(config)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    r = client.post("/api/auth/login", json={"password": "letmein"})
    assert r.status_code == 204
    return client

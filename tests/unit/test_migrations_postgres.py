"""Run the migration chain on a real Postgres when one is provided.

SQLite accepts SQL that Postgres rejects (`boolean = 1`, Text columns with CURRENT_TIMESTAMP ...), and
production runs Postgres. Set SMS_TEST_PG_URL (e.g. postgresql+psycopg://sms@127.0.0.1:54329/smstest)
to exercise the chain here; the test is skipped otherwise.
"""
import os

import pytest
from sqlalchemy import create_engine, text

from sms.memory.migrate import upgrade

PG_URL = os.environ.get("SMS_TEST_PG_URL")

pytestmark = pytest.mark.skipif(not PG_URL, reason="SMS_TEST_PG_URL not set")


@pytest.fixture
def pg_engine():
    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    yield engine
    engine.dispose()


def test_chain_applies_on_postgres(pg_engine):
    upgrade(pg_engine, "head")
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0015"


def test_0013_backfills_retention_from_the_boolean(pg_engine):
    upgrade(pg_engine, "0012")
    with pg_engine.begin() as conn:
        conn.execute(text("INSERT INTO settings (id, provider, model, delete_pages_after_marking) VALUES (1, 'p', 'm', TRUE)"))
        conn.execute(text(
            "INSERT INTO assignment_templates (title, subject, rubric_json, delete_pages_after_marking) VALUES "
            "('keep', 'english', '{}', FALSE), ('delete', 'english', '{}', TRUE), ('default', 'english', '{}', NULL)"))
    upgrade(pg_engine, "0013")
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT page_retention FROM settings WHERE id = 1")).scalar() == "crops"
        rows = dict(conn.execute(text("SELECT title, page_retention FROM assignment_templates")).all())
    assert rows == {"keep": "pages", "delete": "crops", "default": None}


def test_chain_reaches_0015_on_postgres(pg_engine):
    upgrade(pg_engine, "head")
    with pg_engine.begin() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0015"
        conn.execute(text("INSERT INTO settings (id, provider, model) VALUES (1, 'p', 'm')"))
        assert conn.execute(text("SELECT reflect_days FROM settings WHERE id = 1")).scalar() == 7


def test_0015_subject_is_nullable_on_postgres(pg_engine):
    upgrade(pg_engine, "head")
    with pg_engine.begin() as conn:
        conn.execute(text("INSERT INTO classes (id, name, code) VALUES (1, '4E2', 'ABCD')"))
        assert conn.execute(text("SELECT subject FROM classes WHERE id = 1")).scalar() is None
        conn.execute(text("UPDATE classes SET subject = 'math' WHERE id = 1"))

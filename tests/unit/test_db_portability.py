import pytest

from sms.memory.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(path=str(tmp_path / "s.db"))


def test_tables_exist_after_construct(db):
    names = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"marking_runs", "teacher_corrections", "rubric_notes", "exemplar_cases",
            "extraction_cache", "agent_metrics", "teacher_queue", "alembic_version"} <= names


def test_qmark_tuple_params(db):
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES (?, ?, ?)", ("math", "n1", "draft"))
    rows = db.query("SELECT note FROM rubric_notes WHERE subject = ?", ("math",))
    assert [r["note"] for r in rows] == ["n1"]


def test_named_dict_params(db):
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES (:s, :n, :st)",
               {"s": "math", "n": "n2", "st": "draft"})
    rows = db.query("SELECT note FROM rubric_notes WHERE subject = :s", {"s": "math"})
    assert [r["note"] for r in rows] == ["n2"]


def test_insert_returning_id(db):
    new_id = db.insert("INSERT INTO rubric_notes (subject, note, status) VALUES (:s, :n, 'draft') RETURNING id",
                       {"s": "math", "n": "x"})
    assert isinstance(new_id, int) and new_id >= 1


def test_execute_returns_rowcount(db):
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'a', 'draft')")
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'b', 'draft')")
    assert db.execute("UPDATE rubric_notes SET status = 'active' WHERE subject = 'math'") == 2


def test_url_constructor_and_postgres_scheme_normalisation(tmp_path):
    d = Database(url=f"sqlite:///{tmp_path / 'u.db'}")
    assert d.is_sqlite
    d2 = Database.__new__(Database)
    assert d2._normalise_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert d2._normalise_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_created_at_default_is_populated(db):
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'a', 'draft')")
    row = db.query("SELECT created_at FROM rubric_notes")[0]
    assert row["created_at"]


def test_qmark_inside_string_literal_is_not_a_placeholder(db):
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'why?', 'draft')")
    rows = db.query(
        "SELECT note FROM rubric_notes WHERE subject = ? AND note != 'unused?'",
        ("math",),
    )
    assert [r["note"] for r in rows] == ["why?"]


def test_qmark_param_count_mismatch_raises_value_error(db):
    with pytest.raises(ValueError) as exc_info:
        db.query("SELECT note FROM rubric_notes WHERE subject = ? AND note = ?", ("math",))
    message = str(exc_info.value)
    assert "2" in message and "1" in message


def test_web_tables_exist(db):
    names = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"settings", "submissions", "pages", "jobs", "worker_heartbeat"} <= names
    cols = {r["name"] for r in db.query("PRAGMA table_info(marking_runs)")}
    assert {"submission_id", "final_marks_json"} <= cols
    assert "submission_id" in {r["name"] for r in db.query("PRAGMA table_info(teacher_queue)")}
    assert "criterion_scores_json" in {r["name"] for r in db.query("PRAGMA table_info(teacher_corrections)")}


# The seven tables exactly as the pre-Alembic CLI's `Database.SCHEMA` created them (commit b210299).
LEGACY_CLI_SCHEMA = """
CREATE TABLE marking_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    subject TEXT NOT NULL,
    rubric_json TEXT NOT NULL,
    extracted_json TEXT,
    marks_json TEXT,
    reviewed_json TEXT,
    feedback_json TEXT,
    final_status TEXT NOT NULL DEFAULT 'running',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE teacher_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    q_id TEXT NOT NULL,
    agent_mark INTEGER,
    teacher_mark INTEGER,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE rubric_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    note TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    source_run_ids_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE exemplar_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    topic TEXT NOT NULL,
    q_id TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    awarded INTEGER NOT NULL,
    max_score INTEGER NOT NULL,
    why_it_matters TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE extraction_cache (
    hash TEXT NOT NULL,
    subject TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    extracted_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (hash, subject, schema_version)
);
CREATE TABLE agent_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    stage TEXT NOT NULL,
    agent_role TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE teacher_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    q_id TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def test_upgrade_stamps_pre_alembic_database(tmp_path):
    """An sms.db created by the pre-Alembic CLI (seven tables, no alembic_version) must upgrade cleanly."""
    import sqlite3

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_CLI_SCHEMA)
    conn.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'keep me', 'active')")
    conn.commit()
    conn.close()

    db = Database(path=str(path))
    names = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"settings", "submissions", "pages", "jobs", "worker_heartbeat", "alembic_version"} <= names
    assert db.query("SELECT version_num FROM alembic_version")[0]["version_num"] != "0001"
    assert "submission_id" in {r["name"] for r in db.query("PRAGMA table_info(marking_runs)")}
    assert db.query("SELECT note FROM rubric_notes")[0]["note"] == "keep me"
    # Re-opening an already-stamped database is a no-op.
    Database(path=str(path))

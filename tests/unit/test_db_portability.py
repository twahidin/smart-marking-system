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


def test_migration_0004_columns_and_page_kind_backfill(tmp_path):
    """0004 adds the typed-marking columns and marks existing template pages as 'paper'."""
    from sms.memory.migrate import upgrade

    db = Database(path=str(tmp_path / "m.db"), migrate=False)
    upgrade(db.engine, "0003")
    tid = db.insert("INSERT INTO assignment_templates (title, subject, rubric_json) VALUES ('t', 'math', '{}') RETURNING id")
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) "
                    "VALUES ('s', 'math', '', '{}', 'uploaded') RETURNING id")
    db.execute("INSERT INTO pages (template_id, page_index, sha256, storage_path, width, height) VALUES (:t, 0, 'h', 'p', 1, 1)",
               {"t": tid})
    db.execute("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height) VALUES (:s, 0, 'h', 'p', 1, 1)",
               {"s": sid})
    upgrade(db.engine, "head")

    def cols(table):
        return {r["name"]: r for r in db.query(f"PRAGMA table_info({table})")}

    assert "delete_pages_after_marking" in cols("assignment_templates")
    assert cols("assignment_templates")["delete_pages_after_marking"]["notnull"] == 0
    assert cols("settings")["delete_pages_after_marking"]["notnull"] == 1
    assert "deleted_at" in cols("pages") and "kind" in cols("pages")
    assert cols("submissions")["marks_version"]["notnull"] == 1
    rows = {r["template_id"] or 0: r for r in db.query("SELECT template_id, kind, deleted_at FROM pages")}
    assert rows[tid]["kind"] == "paper" and rows[0]["kind"] == "student" and rows[tid]["deleted_at"] is None
    assert db.query("SELECT marks_version FROM submissions")[0]["marks_version"] == 1
    assert db.query("SELECT delete_pages_after_marking FROM assignment_templates")[0]["delete_pages_after_marking"] is None
    # a fresh settings row defaults to deleting pages after marking
    db.execute("INSERT INTO settings (id, provider, model) VALUES (1, 'openai', 'm')")
    assert db.query("SELECT delete_pages_after_marking FROM settings")[0]["delete_pages_after_marking"] in (1, True)


def test_migration_0005_adds_scheme_kind_and_backfills_from_the_template(tmp_path):
    from sms.memory.migrate import upgrade

    db = Database(path=str(tmp_path / "m.db"), migrate=False)
    upgrade(db.engine, "0004")
    tid = db.insert("INSERT INTO assignment_templates (title, subject, rubric_json, scheme_kind) VALUES ('t', 'math', '{}', 'rubric') RETURNING id")
    with_t = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status, assignment_id) "
                       "VALUES ('a', 'math', '', '{}', 'uploaded', :t) RETURNING id", {"t": tid})
    without = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) "
                        "VALUES ('b', 'math', '', '{}', 'uploaded') RETURNING id")
    dangling = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status, assignment_id) "
                         "VALUES ('c', 'math', '', '{}', 'uploaded', 999) RETURNING id")
    upgrade(db.engine, "head")
    cols = {r["name"]: r for r in db.query("PRAGMA table_info(submissions)")}
    assert cols["scheme_kind"]["notnull"] == 0 and "marks_version" in cols
    kinds = {r["id"]: r["scheme_kind"] for r in db.query("SELECT id, scheme_kind FROM submissions")}
    assert kinds == {with_t: "rubric", without: None, dangling: None}


def test_migration_0011_timestamps_are_datetime_not_text(tmp_path):
    """Postgres refuses a CURRENT_TIMESTAMP default on a text column ("column is of type text but
    default expression is of type timestamp with time zone"), so the three timestamps 0011 adds must
    be DateTime like every other migration's — SQLite would happily take either."""
    import sqlalchemy as sa

    db = Database(path=str(tmp_path / "t.db"))
    insp = sa.inspect(db.engine)
    files = {c["name"]: c for c in insp.get_columns("submission_files")}
    assert isinstance(files["created_at"]["type"], sa.DateTime)
    assert files["created_at"]["nullable"] is False
    assert isinstance(files["deleted_at"]["type"], sa.DateTime)
    assert files["deleted_at"]["nullable"] is True and files["deleted_at"]["default"] is None
    models = {c["name"]: c for c in insp.get_columns("subject_models")}
    assert isinstance(models["updated_at"]["type"], sa.DateTime)
    assert models["updated_at"]["nullable"] is False


def test_submission_files_timestamps_round_trip(tmp_path):
    """The readers and writers of those columns still work: the server default fills `created_at`,
    and `pages_cleanup`'s `deleted_at = CURRENT_TIMESTAMP` reads back as set."""
    db = Database(path=str(tmp_path / "t.db"))
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) "
                    "VALUES ('s', 'computing', '', '{}', 'uploaded') RETURNING id")
    db.execute("INSERT INTO submission_files (submission_id, name, kind, size, sha256, stored_path) "
               "VALUES (:s, 'a.py', 'py', 3, 'h', 'p')", {"s": sid})
    row = db.query("SELECT created_at, deleted_at FROM submission_files")[0]
    assert row["created_at"] and row["deleted_at"] is None
    db.execute("UPDATE submission_files SET deleted_at = CURRENT_TIMESTAMP WHERE submission_id = :s", {"s": sid})
    assert db.query("SELECT deleted_at FROM submission_files")[0]["deleted_at"] is not None

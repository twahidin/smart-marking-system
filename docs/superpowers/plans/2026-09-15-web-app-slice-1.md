# Smart Marking Web App — Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the `sms` CLI into a Railway-deployable web app: a teacher signs in with a shared password, picks an LLM provider/model and enters a key (default TokenRouter `z-ai/glm-5.3-free`), uploads a script (PDF/JPG/PNG/HEIC), a background worker marks it, and the teacher resolves escalated questions in a review queue.

**Architecture:** One container: FastAPI serves `/api/*` and a built React SPA; a worker thread started in the FastAPI lifespan claims `jobs` rows from Postgres and runs the existing `MarkingPipeline` through a provider-built instructor client, rate-limited per settings. SQLAlchemy Core + Alembic replace raw sqlite3 so the same code runs on SQLite (tests/local) and Postgres (Railway). Page images live on a volume, content-addressed.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, SQLAlchemy 2 Core, Alembic, psycopg 3, instructor 1.14, atomic-agents 2.10, openai SDK, anthropic SDK, cryptography (Fernet), itsdangerous, PyMuPDF, Pillow, pillow-heif; React 18 + TypeScript + Vite, react-router 6, lucide-react, vitest + @testing-library/react; Docker multi-stage; Railway (web + Postgres + volume).

**Spec:** `docs/superpowers/specs/2026-09-15-web-app-slice-1-design.md` — read it first. Design references (screens, tokens, copy): `docs/design-handoff/README.md`, `docs/design-handoff/screenshots/*.png`, `docs/design-handoff/_ds/modernist-74c12b6c-c14e-4137-a9d0-95bc689f713c/styles.css`.

## Global Constraints

- Python `>=3.12`; run everything with `uv run …`; add deps with `uv add …` (never edit `uv.lock` by hand).
- All SQL must run on **both** SQLite and Postgres. No `INSERT OR REPLACE`, no `datetime('now', …)`, no `AUTOINCREMENT` in new migrations; compute timestamps in Python as `datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")` when comparing.
- `Database.execute/query` accept either `?` placeholders with a tuple **or** `:name` placeholders with a dict. New code uses `:name`.
- The API key is never returned by any endpoint; only `has_key` and `key_hint` (last 4 chars).
- Every `/api/*` route except `/api/health` and `/api/auth/login` requires the teacher session cookie.
- Default provider `tokenrouter`, default model `z-ai/glm-5.3-free`, default RPM `8`.
- Upload limits: 50 MB per request, 60 pages per submission; pages normalised to JPEG, long edge ≤ 2000 px, quality 85.
- Frontend: plain CSS from the Modernist tokens (zero border radius, Archivo, accent `#ec3013`, amber only for "Needs you"), touch targets ≥ 44 px, no hover-only affordances. Product copy in short plain sentences. The words "escalation", "confidence", "reviewer" are fine on **teacher** screens (slice 1 has no student screens).
- Commit after every task with a conventional-commit message; end commit messages with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Run the full suite `uv run pytest -q` before each commit; it must stay green.

## File structure

**Backend (modify)**
- `src/sms/memory/db.py` — SQLAlchemy-backed `Database` (URL or `path=`), runs migrations on construct.
- `src/sms/memory/extraction_cache.py` — portable upsert (delete + insert).
- `src/sms/learning/reflection_job.py` — Python-computed cutoff instead of `datetime('now', ?)`.
- `src/sms/pipeline/marking_pipeline.py` — persist `final_marks_json` and `submission_id`.
- `src/sms/cli.py` — `serve` and `worker` commands; `_client()` uses the provider layer.
- `pyproject.toml` — new dependencies; hatch includes migrations.

**Backend (create)**
- `src/sms/migrations/env.py`, `src/sms/migrations/script.py.mako`, `src/sms/migrations/versions/0001_baseline.py`, `0002_web.py` — Alembic, shipped inside the package.
- `src/sms/memory/migrate.py` — `upgrade(engine)`.
- `src/sms/providers/registry.py` — `ProviderSpec`, `ModelSpec`, `PROVIDERS`, `get_provider()`.
- `src/sms/providers/client.py` — `build_client()`.
- `src/sms/providers/crypto.py` — `KeyCipher` (Fernet from `SECRET_KEY`).
- `src/sms/providers/settings.py` — `Settings`, `SettingsStore`.
- `src/sms/providers/ratelimit.py` — `TokenBucket`, `RateLimitedAgent`.
- `src/sms/providers/errors.py` — `is_retryable()`, `error_message()`.
- `src/sms/providers/probe.py` — `probe()`.
- `src/sms/storage.py` — `PageStorage`, `process_uploads()`, `UploadError`.
- `src/sms/worker/jobs.py` — `JobStore` (enqueue/claim/finish/fail/reset_running/heartbeat).
- `src/sms/worker/mark_job.py` — `run_mark_job()`.
- `src/sms/worker/worker.py` — `Worker` loop.
- `src/sms/web/config.py` — `AppConfig.from_env()`.
- `src/sms/web/app.py` — `create_app(config)`, lifespan, SPA mount.
- `src/sms/web/deps.py` — `get_db`, `require_teacher`, session signer.
- `src/sms/web/errors.py` — `ApiError` + handler.
- `src/sms/web/routers/{auth,settings,submissions,pages,queue,learning,health}.py`
- `src/sms/web/services/submissions.py` — create + serialize submissions.
- `src/sms/web/services/queue.py` — list + resolve queue items.

**Frontend (create, under `web/`)**
- `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `vitest.setup.ts`
- `src/main.tsx`, `src/App.tsx` (routes + auth gate)
- `src/styles/tokens.css` (verbatim copy of the Modernist stylesheet), `src/styles/app.css` (product components)
- `src/api/client.ts` (fetch wrapper), `src/api/types.ts`
- `src/lib/rubric.ts`, `src/lib/marks.ts`, `src/lib/format.ts`
- `src/components/{Nav,Button,StatusPill,Notice,EmptyState,CriteriaTable,MarkDisplay,PageCard,PagePager,DropZone,Dialog}.tsx`
- `src/pages/{SignIn,Settings,Submissions,NewSubmission,SubmissionDetail,Review,Learning}.tsx`
- `src/lib/__tests__/rubric.test.ts`, `src/lib/__tests__/marks.test.ts`, `src/components/__tests__/*.test.tsx`

**Deploy (create)**
- `Dockerfile`, `.dockerignore`, `railway.json`, README "Deploy on Railway" + "Run locally".

**Tests (create)**
- `tests/unit/test_db_portability.py`, `tests/unit/test_registry.py`, `tests/unit/test_crypto.py`, `tests/unit/test_settings_store.py`, `tests/unit/test_ratelimit.py`, `tests/unit/test_errors.py`, `tests/unit/test_probe.py`, `tests/unit/test_storage.py`, `tests/unit/test_jobs.py`, `tests/unit/test_worker.py`
- `tests/web/conftest.py`, `tests/web/test_auth.py`, `tests/web/test_settings_api.py`, `tests/web/test_submissions_api.py`, `tests/web/test_queue_api.py`, `tests/web/test_health.py`
- `tests/live/test_tokenrouter_live.py` (opt-in)

**Rubric note (deviation from the mockup, deliberate):** the engine's `Rubric.criterion_defs` are criteria applied to **every** question (each `MarkedQuestion.criterion_scores` has one entry per criterion). The mockup's criteria table has a per-question "Q" column. Slice 1 keeps the engine's model: the criteria table has columns Criterion / Description / Max with the caption "Applied to every question". Per-question rubrics are a slice 2 (assignments) change.

---

### Task 1: SQLAlchemy `Database` + Alembic baseline

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/sms/memory/db.py`
- Create: `src/sms/memory/migrate.py`, `src/sms/migrations/env.py`, `src/sms/migrations/script.py.mako`, `src/sms/migrations/versions/0001_baseline.py`, `alembic.ini`
- Modify: `src/sms/memory/extraction_cache.py`, `src/sms/learning/reflection_job.py`
- Test: `tests/unit/test_db_portability.py`

**Interfaces:**
- Produces: `Database(url: str | None = None, *, path: str | None = None, migrate: bool = True)` with `.engine`, `.url`, `.is_sqlite`, `.execute(sql, params=None) -> int` (rowcount), `.query(sql, params=None) -> list[dict]`, `.insert(sql, params=None) -> int` (sql ends with `RETURNING id`), `.transaction()` context manager yielding a `Database`-like object bound to one connection; `sms.memory.migrate.upgrade(engine)`.

- [ ] **Step 1: Add dependencies**

```bash
uv add "sqlalchemy>=2.0,<3" "alembic>=1.13,<2" "psycopg[binary]>=3.2,<4"
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_db_portability.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_db_portability.py -q`
Expected: FAIL (`Database.__init__() got an unexpected keyword argument 'url'` / missing `insert`).

- [ ] **Step 4: Write the Alembic scaffolding**

`alembic.ini` (repo root, for manual CLI use only):

```ini
[alembic]
script_location = src/sms/migrations
sqlalchemy.url = sqlite:///sms.db

[loggers]
keys = root
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARN
handlers = console
[handler_console]
class = StreamHandler
args = (sys.stderr,)
formatter = generic
[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

`src/sms/migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`src/sms/migrations/env.py`:

```python
from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

config = context.config


def _run_with(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=None, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if connection is not None:
    _run_with(connection)
else:
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    with engine.connect() as conn:
        _run_with(conn)
```

`src/sms/migrations/versions/0001_baseline.py`:

```python
"""baseline: existing sms tables

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marking_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("rubric_json", sa.Text, nullable=False),
        sa.Column("extracted_json", sa.Text),
        sa.Column("marks_json", sa.Text),
        sa.Column("reviewed_json", sa.Text),
        sa.Column("feedback_json", sa.Text),
        sa.Column("final_status", sa.Text, nullable=False, server_default="running"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_marking_runs_run_id", "marking_runs", ["run_id"])
    op.create_table(
        "teacher_corrections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("q_id", sa.Text, nullable=False),
        sa.Column("agent_mark", sa.Integer),
        sa.Column("teacher_mark", sa.Integer),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "rubric_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("source_run_ids_json", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "exemplar_cases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("q_id", sa.Text, nullable=False),
        sa.Column("answer_text", sa.Text, nullable=False),
        sa.Column("awarded", sa.Integer, nullable=False),
        sa.Column("max_score", sa.Integer, nullable=False),
        sa.Column("why_it_matters", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "extraction_cache",
        sa.Column("hash", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("extracted_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("hash", "subject", "schema_version"),
    )
    op.create_table(
        "agent_metrics",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Text),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("agent_role", sa.Text, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "teacher_queue",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("q_id", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    for t in ("teacher_queue", "agent_metrics", "extraction_cache", "exemplar_cases",
              "rubric_notes", "teacher_corrections", "marking_runs"):
        op.drop_table(t)
```

`src/sms/memory/migrate.py`:

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _config(engine: Engine) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", str(engine.url).replace("%", "%%"))
    return cfg


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Apply all migrations using an existing engine (works for SQLite and Postgres)."""
    cfg = _config(engine)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)
```

- [ ] **Step 5: Rewrite `Database`**

`src/sms/memory/db.py`:

```python
import os
import re
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine

Params = Union[None, Sequence[Any], Dict[str, Any]]

_QMARK = re.compile(r"\?")


def _bind(sql: str, params: Params):
    """Accept `?` + tuple (legacy) or `:name` + dict. Returns (sql, dict)."""
    if params is None:
        return sql, {}
    if isinstance(params, dict):
        return sql, params
    seq = list(params)
    counter = iter(range(len(seq)))
    converted = _QMARK.sub(lambda _m: f":p{next(counter)}", sql)
    return converted, {f"p{i}": v for i, v in enumerate(seq)}


class _Executor:
    def __init__(self, conn: Connection):
        self._conn = conn

    def execute(self, sql: str, params: Params = None) -> int:
        sql, bound = _bind(sql, params)
        return self._conn.execute(text(sql), bound).rowcount

    def query(self, sql: str, params: Params = None) -> List[Dict[str, Any]]:
        sql, bound = _bind(sql, params)
        result = self._conn.execute(text(sql), bound)
        return [dict(row) for row in result.mappings().all()]

    def insert(self, sql: str, params: Params = None) -> int:
        sql, bound = _bind(sql, params)
        return int(self._conn.execute(text(sql), bound).scalar_one())


class Database:
    """SQLAlchemy Core wrapper. Same code path on SQLite (tests/local) and Postgres (Railway)."""

    def __init__(self, url: Optional[str] = None, *, path: Optional[str] = None, migrate: bool = True):
        if path is not None:
            url = f"sqlite:///{path}"
        url = url or os.environ.get("DATABASE_URL", "sqlite:///sms.db")
        self.url = self._normalise_url(url)
        self.is_sqlite = self.url.startswith("sqlite")
        kwargs: Dict[str, Any] = {"future": True, "pool_pre_ping": not self.is_sqlite}
        if self.is_sqlite:
            kwargs["connect_args"] = {"check_same_thread": False}
        self.engine: Engine = create_engine(self.url, **kwargs)
        if self.is_sqlite:
            @event.listens_for(self.engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _record):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=5000")
                cur.close()
        if migrate:
            from sms.memory.migrate import upgrade
            upgrade(self.engine)

    @staticmethod
    def _normalise_url(url: str) -> str:
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    def execute(self, sql: str, params: Params = None) -> int:
        with self.engine.begin() as conn:
            return _Executor(conn).execute(sql, params)

    def query(self, sql: str, params: Params = None) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            return _Executor(conn).query(sql, params)

    def insert(self, sql: str, params: Params = None) -> int:
        with self.engine.begin() as conn:
            return _Executor(conn).insert(sql, params)

    @contextmanager
    def transaction(self) -> Iterator[_Executor]:
        with self.engine.begin() as conn:
            yield _Executor(conn)

    def dispose(self) -> None:
        self.engine.dispose()
```

- [ ] **Step 6: Make the two SQLite-only statements portable**

`src/sms/memory/extraction_cache.py` — replace `put`:

```python
    def put(self, hash_: str, subject: str, extracted: Dict[str, Any]) -> None:
        with self.db.transaction() as tx:
            tx.execute(
                "DELETE FROM extraction_cache WHERE hash = :h AND subject = :s AND schema_version = 1",
                {"h": hash_, "s": subject},
            )
            tx.execute(
                "INSERT INTO extraction_cache (hash, subject, schema_version, extracted_json) "
                "VALUES (:h, :s, 1, :j)",
                {"h": hash_, "s": subject, "j": json.dumps(extracted)},
            )
```

`src/sms/learning/reflection_job.py` — replace the query at the top of `run_reflection`:

```python
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = db.query(
        "SELECT tc.run_id, tc.q_id, tc.agent_mark, tc.teacher_mark, tc.reason, mr.subject, "
        "mr.rubric_json, mr.extracted_json "
        "FROM teacher_corrections tc JOIN marking_runs mr ON tc.run_id = mr.run_id "
        "WHERE mr.subject = :subject AND tc.created_at >= :cutoff "
        "AND tc.agent_mark IS NOT NULL AND tc.agent_mark != tc.teacher_mark",
        {"subject": subject, "cutoff": cutoff},
    )
```

(Move the `datetime` import to the top of the file.)

- [ ] **Step 7: Make hatch ship the migrations and confirm packaging**

In `pyproject.toml` the wheel target already packages `src/sms`; add explicit inclusion of the mako template:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/sms"]
include = ["src/sms/migrations/**"]
```

- [ ] **Step 8: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass, including `tests/unit/test_db_portability.py` (7 tests) and every pre-existing test. If `test_memory.py::test_database_creates_tables` fails on the `alembic_version` table not being in its expected set, that test uses `<=`, so it passes; do not edit it.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock alembic.ini src/sms/memory src/sms/migrations src/sms/learning/reflection_job.py tests/unit/test_db_portability.py
git commit -m "feat: SQLAlchemy-backed Database with Alembic baseline (SQLite + Postgres)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Migration 0002 — web tables + pipeline persists final marks

**Files:**
- Create: `src/sms/migrations/versions/0002_web.py`
- Modify: `src/sms/pipeline/marking_pipeline.py`
- Test: `tests/unit/test_db_portability.py` (append), `tests/integration/test_pipeline.py` (append)

**Interfaces:**
- Produces tables `settings`, `submissions`, `pages`, `jobs`, `worker_heartbeat`; columns `marking_runs.submission_id`, `marking_runs.final_marks_json`, `teacher_queue.submission_id`, `teacher_corrections.criterion_scores_json`.
- Produces: `MarkingPipeline.run(images, assignment_context, rubric, submission_id: int | None = None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_db_portability.py`:

```python
def test_web_tables_exist(db):
    names = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"settings", "submissions", "pages", "jobs", "worker_heartbeat"} <= names
    cols = {r["name"] for r in db.query("PRAGMA table_info(marking_runs)")}
    assert {"submission_id", "final_marks_json"} <= cols
    assert "submission_id" in {r["name"] for r in db.query("PRAGMA table_info(teacher_queue)")}
    assert "criterion_scores_json" in {r["name"] for r in db.query("PRAGMA table_info(teacher_corrections)")}
```

Append to `tests/integration/test_pipeline.py` (reuse its existing stubs and `rubric` fixture):

```python
def test_pipeline_persists_final_marks_and_submission_id(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    sub_id = db.insert(
        "INSERT INTO submissions (label, subject, context, rubric_json, status) "
        "VALUES ('t', 'math', 'c', '{}', 'marking') RETURNING id"
    )
    pipeline = MarkingPipeline(
        db=db,
        extractor=StubAgent(EXTRACTED_STUB, None, None),
        marker=StubAgent(MARKED_STUB, None, None),
        reviewer=StubAgent(REVIEWED_STUB, None, None),
        feedback=StubAgent(FEEDBACK_STUB, None, None),
        subject="math",
    )
    result = pipeline.run(images=[b"img"], assignment_context="ctx", rubric=rubric, submission_id=sub_id)
    row = db.query("SELECT submission_id, final_marks_json FROM marking_runs WHERE run_id = ?", (result.run_id,))[0]
    assert row["submission_id"] == sub_id
    assert '"q1"' in row["final_marks_json"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_db_portability.py::test_web_tables_exist tests/integration/test_pipeline.py::test_pipeline_persists_final_marks_and_submission_id -q`
Expected: FAIL (no such table `submissions`).

- [ ] **Step 3: Write migration 0002**

`src/sms/migrations/versions/0002_web.py`:

```python
"""web: settings, submissions, pages, jobs, heartbeat; link runs/queue to submissions

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("base_url", sa.Text),
        sa.Column("extractor_model", sa.Text),
        sa.Column("api_key_enc", sa.Text),
        sa.Column("rpm_limit", sa.Integer, nullable=False, server_default="8"),
        sa.Column("confidence_threshold", sa.Float, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=False, server_default=""),
        sa.Column("rubric_json", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="uploaded"),
        sa.Column("run_id", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "pages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("sha256", sa.Text, nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("source_filename", sa.Text, nullable=False, server_default=""),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.UniqueConstraint("submission_id", "page_index", name="uq_pages_submission_index"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE")),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("not_before", sa.DateTime),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime),
    )
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])
    op.create_table(
        "worker_heartbeat",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("last_seen", sa.DateTime, nullable=False),
    )
    with op.batch_alter_table("marking_runs") as b:
        b.add_column(sa.Column("submission_id", sa.Integer))
        b.add_column(sa.Column("final_marks_json", sa.Text))
    with op.batch_alter_table("teacher_queue") as b:
        b.add_column(sa.Column("submission_id", sa.Integer))
    with op.batch_alter_table("teacher_corrections") as b:
        b.add_column(sa.Column("criterion_scores_json", sa.Text))


def downgrade() -> None:
    with op.batch_alter_table("teacher_corrections") as b:
        b.drop_column("criterion_scores_json")
    with op.batch_alter_table("teacher_queue") as b:
        b.drop_column("submission_id")
    with op.batch_alter_table("marking_runs") as b:
        b.drop_column("final_marks_json")
        b.drop_column("submission_id")
    op.drop_table("worker_heartbeat")
    op.drop_index("ix_jobs_status_created", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("pages")
    op.drop_table("submissions")
    op.drop_table("settings")
```

- [ ] **Step 4: Persist final marks and submission id in the pipeline**

In `src/sms/pipeline/marking_pipeline.py`:

- Change the signature: `def run(self, images: List[bytes], assignment_context: str, rubric: Rubric, submission_id: Optional[int] = None) -> MarkingResult:`
- Change the `_persist` call to `self._persist(run_id, rubric, extracted, marked, reviewed, feedback_report, escalation_reasons, final_marks, submission_id)`.
- Replace `_persist` with:

```python
    def _persist(self, run_id: str, rubric: Rubric, extracted: ExtractedScript, marked: MarkedScript,
                 reviewed: ReviewedScript, feedback: FeedbackReport, escalation_reasons: dict,
                 final_marks: MarkedScript, submission_id: Optional[int]) -> None:
        escalations = list(escalation_reasons.keys())
        self.db.execute(
            "INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, marks_json, "
            "reviewed_json, feedback_json, final_marks_json, submission_id, final_status) "
            "VALUES (:run_id, 'complete', :subject, :rubric, :extracted, :marks, :reviewed, :feedback, "
            ":final_marks, :submission_id, :status)",
            {
                "run_id": run_id,
                "subject": self.subject,
                "rubric": rubric.model_dump_json(),
                "extracted": extracted.model_dump_json(),
                "marks": marked.model_dump_json(),
                "reviewed": reviewed.model_dump_json(),
                "feedback": feedback.model_dump_json(),
                "final_marks": final_marks.model_dump_json(),
                "submission_id": submission_id,
                "status": "escalated" if escalations else "complete",
            },
        )
        for q_id, reason in escalation_reasons.items():
            self.db.execute(
                "INSERT INTO teacher_queue (run_id, q_id, reason, status, submission_id) "
                "VALUES (:run_id, :q_id, :reason, 'pending', :submission_id)",
                {"run_id": run_id, "q_id": q_id, "reason": reason, "submission_id": submission_id},
            )
```

- [ ] **Step 5: Run the suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/sms/migrations/versions/0002_web.py src/sms/pipeline/marking_pipeline.py tests
git commit -m "feat: web tables migration; pipeline persists final marks and submission id

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Provider registry, client factory, key cipher

**Files:**
- Create: `src/sms/providers/__init__.py`, `src/sms/providers/registry.py`, `src/sms/providers/client.py`, `src/sms/providers/crypto.py`
- Modify: `pyproject.toml`
- Test: `tests/unit/test_registry.py`, `tests/unit/test_crypto.py`

**Interfaces:**
- Produces: `ModelSpec(id, label, vision)`, `ProviderSpec(id, label, transport, base_url, mode, default_model, default_rpm, models, key_url, note, base_url_editable, api_params)`, `PROVIDERS: tuple[ProviderSpec, ...]`, `DEFAULT_PROVIDER = "tokenrouter"`, `get_provider(provider_id) -> ProviderSpec` (raises `KeyError`), `registry_as_dicts() -> list[dict]`; `build_client(provider_id, api_key, base_url=None) -> instructor.Instructor`; `KeyCipher(secret_key: str)` with `.encrypt(str) -> str`, `.decrypt(str) -> str`.

- [ ] **Step 1: Add dependencies**

```bash
uv add "anthropic>=0.40" "cryptography>=43"
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_registry.py`:

```python
import pytest

import instructor

from sms.providers.client import build_client
from sms.providers.registry import DEFAULT_PROVIDER, PROVIDERS, get_provider, registry_as_dicts


def test_default_provider_is_tokenrouter_free_glm():
    p = get_provider(DEFAULT_PROVIDER)
    assert p.id == "tokenrouter"
    assert p.default_model == "z-ai/glm-5.3-free"
    assert p.default_rpm == 8
    assert p.base_url == "https://api.tokenrouter.com/v1"


def test_all_six_providers_present_with_vision_default():
    ids = {p.id for p in PROVIDERS}
    assert ids == {"tokenrouter", "openrouter", "openai", "anthropic", "moonshot", "qwen"}
    for p in PROVIDERS:
        default = next(m for m in p.models if m.id == p.default_model)
        assert default.vision, f"{p.id} default model must support vision"


def test_unknown_provider_raises():
    with pytest.raises(KeyError):
        get_provider("nope")


def test_registry_as_dicts_is_json_shaped():
    d = registry_as_dicts()
    assert d[0]["id"] and isinstance(d[0]["models"], list) and "vision" in d[0]["models"][0]


@pytest.mark.parametrize("pid,mode", [
    ("tokenrouter", instructor.Mode.JSON),
    ("openrouter", instructor.Mode.JSON),
    ("moonshot", instructor.Mode.JSON),
    ("qwen", instructor.Mode.JSON),
    ("openai", instructor.Mode.TOOLS),
])
def test_build_client_openai_family(pid, mode):
    client = build_client(pid, api_key="sk-test")
    assert client.mode == mode
    spec = get_provider(pid)
    if spec.base_url:
        assert str(client.client.base_url).rstrip("/") == spec.base_url


def test_build_client_anthropic():
    client = build_client("anthropic", api_key="sk-ant-test")
    assert client.mode == instructor.Mode.ANTHROPIC_TOOLS


def test_anthropic_requires_max_tokens_param():
    assert get_provider("anthropic").api_params == {"max_tokens": 8192}
    assert get_provider("openai").api_params is None


def test_build_client_base_url_override():
    client = build_client("qwen", api_key="k", base_url="https://ws.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1")
    assert "maas.aliyuncs.com" in str(client.client.base_url)


def test_build_client_unknown_provider():
    with pytest.raises(KeyError):
        build_client("nope", api_key="k")
```

`tests/unit/test_crypto.py`:

```python
from sms.providers.crypto import KeyCipher


def test_roundtrip_and_distinct_ciphertext():
    c = KeyCipher("a-secret-that-is-not-32-bytes")
    enc = c.encrypt("sk-abc")
    assert enc != "sk-abc"
    assert c.decrypt(enc) == "sk-abc"


def test_different_secret_cannot_decrypt():
    import pytest
    enc = KeyCipher("one").encrypt("sk-abc")
    with pytest.raises(ValueError):
        KeyCipher("two").decrypt(enc)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_registry.py tests/unit/test_crypto.py -q`
Expected: FAIL with `ModuleNotFoundError: sms.providers`.

- [ ] **Step 4: Write the registry**

`src/sms/providers/__init__.py`: empty.

`src/sms/providers/registry.py`:

```python
from dataclasses import asdict, dataclass
from typing import Optional, Tuple

DEFAULT_PROVIDER = "tokenrouter"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    vision: bool


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    transport: str            # "openai_compatible" | "openai" | "anthropic"
    base_url: Optional[str]   # None = SDK default
    mode: str                 # instructor.Mode name
    default_model: str
    default_rpm: int
    models: Tuple[ModelSpec, ...]
    key_url: str
    note: str = ""
    base_url_editable: bool = False
    api_params: Optional[dict] = None   # extra kwargs every agent call needs (Anthropic: max_tokens)


PROVIDERS: Tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="tokenrouter", label="TokenRouter", transport="openai_compatible",
        base_url="https://api.tokenrouter.com/v1", mode="JSON",
        default_model="z-ai/glm-5.3-free", default_rpm=8,
        models=(
            ModelSpec("z-ai/glm-5.3-free", "GLM 5.3 (free)", True),
            ModelSpec("z-ai/glm-5.3-flash", "GLM 5.3 Flash", True),
        ),
        key_url="https://www.tokenrouter.com/",
        note="Free tier: 8 requests a minute — about 30 s per script. When you create the key, "
             "lock Allowed Models to z-ai/glm-5.3-free so nothing routes to a paid model.",
    ),
    ProviderSpec(
        id="openrouter", label="OpenRouter", transport="openai_compatible",
        base_url="https://openrouter.ai/api/v1", mode="JSON",
        default_model="z-ai/glm-5.3-flash", default_rpm=60,
        models=(
            ModelSpec("z-ai/glm-5.3-flash", "GLM 5.3 Flash", True),
            ModelSpec("anthropic/claude-sonnet-5", "Claude Sonnet 5", True),
            ModelSpec("openai/gpt-5-mini", "GPT-5 mini", True),
            ModelSpec("qwen/qwen3-vl-plus", "Qwen3 VL Plus", True),
        ),
        key_url="https://openrouter.ai/keys",
    ),
    ProviderSpec(
        id="openai", label="OpenAI", transport="openai", base_url=None, mode="TOOLS",
        default_model="gpt-5-mini", default_rpm=60,
        models=(
            ModelSpec("gpt-5-mini", "GPT-5 mini", True),
            ModelSpec("gpt-5.4-mini", "GPT-5.4 mini", True),
            ModelSpec("gpt-5.5", "GPT-5.5", True),
        ),
        key_url="https://platform.openai.com/api-keys",
    ),
    ProviderSpec(
        id="anthropic", label="Anthropic", transport="anthropic", base_url=None, mode="ANTHROPIC_TOOLS",
        default_model="claude-opus-5", default_rpm=60,
        models=(
            ModelSpec("claude-opus-5", "Claude Opus 5", True),
            ModelSpec("claude-sonnet-5", "Claude Sonnet 5", True),
            ModelSpec("claude-haiku-4-5", "Claude Haiku 4.5", True),
        ),
        key_url="https://console.anthropic.com/settings/keys",
        api_params={"max_tokens": 8192},
    ),
    ProviderSpec(
        id="moonshot", label="Moonshot (Kimi)", transport="openai_compatible",
        base_url="https://api.moonshot.ai/v1", mode="JSON",
        default_model="kimi-k2.6", default_rpm=60,
        models=(
            ModelSpec("kimi-k2.6", "Kimi K2.6", True),
            ModelSpec("kimi-k3", "Kimi K3", True),
        ),
        key_url="https://platform.moonshot.ai/",
    ),
    ProviderSpec(
        id="qwen", label="Qwen (Alibaba Model Studio)", transport="openai_compatible",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1", mode="JSON",
        default_model="qwen3-vl-plus", default_rpm=60,
        models=(
            ModelSpec("qwen3-vl-plus", "Qwen3 VL Plus", True),
            ModelSpec("qvq-max", "QVQ Max", True),
            ModelSpec("qwen-plus", "Qwen Plus (text only)", False),
        ),
        key_url="https://modelstudio.console.alibabacloud.com/",
        note="Model Studio now issues workspace-specific URLs like "
             "https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1. "
             "If the default URL is rejected, paste yours here.",
        base_url_editable=True,
    ),
)

_BY_ID = {p.id: p for p in PROVIDERS}


def get_provider(provider_id: str) -> ProviderSpec:
    try:
        return _BY_ID[provider_id]
    except KeyError:
        raise KeyError(f"Unknown provider: {provider_id!r}. Known: {sorted(_BY_ID)}") from None


def registry_as_dicts() -> list:
    return [asdict(p) for p in PROVIDERS]
```

- [ ] **Step 5: Write the client factory and cipher**

`src/sms/providers/client.py`:

```python
from typing import Any, Optional

import instructor

from sms.providers.registry import get_provider


def build_client(provider_id: str, api_key: str, base_url: Optional[str] = None) -> Any:
    """Return an instructor client for the provider. Raises KeyError for unknown providers."""
    spec = get_provider(provider_id)
    mode = getattr(instructor.Mode, spec.mode)
    url = base_url or spec.base_url
    if spec.transport == "anthropic":
        import anthropic
        kwargs = {"api_key": api_key}
        if url:
            kwargs["base_url"] = url
        return instructor.from_anthropic(anthropic.Anthropic(**kwargs), mode=mode)
    import openai
    kwargs = {"api_key": api_key}
    if url:
        kwargs["base_url"] = url
    return instructor.from_openai(openai.OpenAI(**kwargs), mode=mode)
```

`src/sms/providers/crypto.py`:

```python
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class KeyCipher:
    """Fernet cipher whose key is derived from SECRET_KEY (any length)."""

    def __init__(self, secret_key: str):
        digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as e:
            raise ValueError("Stored API key cannot be decrypted with this SECRET_KEY") from e
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/unit/test_registry.py tests/unit/test_crypto.py -q`
Expected: PASS. If `client.client.base_url` on the openai client renders with a trailing slash, the test already strips it.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/sms/providers tests/unit/test_registry.py tests/unit/test_crypto.py
git commit -m "feat: provider registry, instructor client factory, API key cipher

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Settings store with env seeding

**Files:**
- Create: `src/sms/providers/settings.py`
- Test: `tests/unit/test_settings_store.py`

**Interfaces:**
- Consumes: `Database`, `KeyCipher`, `get_provider`, `DEFAULT_PROVIDER`.
- Produces: `Settings` dataclass (`provider, model, base_url, extractor_model, api_key, rpm_limit, confidence_threshold`) with `.key_hint -> str`, `.has_key -> bool`, `.effective_extractor_model -> str`, `.public_dict() -> dict`; `SettingsStore(db, cipher)` with `.load() -> Settings`, `.save(settings: Settings) -> Settings`, `.ensure_seeded(env: Mapping[str, str]) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_settings_store.py`:

```python
import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore


@pytest.fixture
def store(tmp_path):
    return SettingsStore(Database(path=str(tmp_path / "s.db")), KeyCipher("secret"))


def test_load_without_row_returns_defaults(store):
    s = store.load()
    assert s.provider == "tokenrouter" and s.model == "z-ai/glm-5.3-free"
    assert s.rpm_limit == 8 and s.api_key is None and not s.has_key


def test_save_encrypts_and_load_decrypts(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-12345678", rpm_limit=60))
    raw = store.db.query("SELECT api_key_enc FROM settings")[0]["api_key_enc"]
    assert "sk-12345678" not in raw
    s = store.load()
    assert s.api_key == "sk-12345678" and s.key_hint == "5678" and s.provider == "openai"


def test_save_without_key_keeps_existing(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-keepme", rpm_limit=60))
    store.save(Settings(provider="openai", model="gpt-5.5", api_key=None, rpm_limit=60))
    assert store.load().api_key == "sk-keepme" and store.load().model == "gpt-5.5"


def test_save_rejects_unknown_provider(store):
    with pytest.raises(KeyError):
        store.save(Settings(provider="nope", model="x", api_key=None, rpm_limit=1))


def test_ensure_seeded_from_env_only_once(store):
    store.ensure_seeded({"LLM_PROVIDER": "openrouter", "LLM_MODEL": "z-ai/glm-5.3-flash", "LLM_API_KEY": "or-key"})
    s = store.load()
    assert s.provider == "openrouter" and s.api_key == "or-key" and s.rpm_limit == 60
    store.ensure_seeded({"LLM_PROVIDER": "openai", "LLM_API_KEY": "other"})
    assert store.load().provider == "openrouter"


def test_ensure_seeded_defaults_when_env_empty(store):
    store.ensure_seeded({})
    s = store.load()
    assert s.provider == "tokenrouter" and s.model == "z-ai/glm-5.3-free" and not s.has_key


def test_public_dict_never_contains_key(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-secret99", rpm_limit=60))
    d = store.load().public_dict()
    assert "api_key" not in d and d["has_key"] is True and d["key_hint"] == "et99"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_settings_store.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/sms/providers/settings.py`:

```python
from dataclasses import dataclass, asdict
from typing import Mapping, Optional

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.registry import DEFAULT_PROVIDER, get_provider


@dataclass
class Settings:
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extractor_model: Optional[str] = None
    rpm_limit: int = 8
    confidence_threshold: float = 0.0

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    @property
    def key_hint(self) -> str:
        return self.api_key[-4:] if self.api_key else ""

    @property
    def effective_extractor_model(self) -> str:
        return self.extractor_model or self.model

    @property
    def effective_base_url(self) -> Optional[str]:
        return self.base_url or get_provider(self.provider).base_url

    def public_dict(self) -> dict:
        d = asdict(self)
        d.pop("api_key")
        d["has_key"] = self.has_key
        d["key_hint"] = self.key_hint
        return d


def default_settings() -> Settings:
    spec = get_provider(DEFAULT_PROVIDER)
    return Settings(provider=spec.id, model=spec.default_model, rpm_limit=spec.default_rpm)


class SettingsStore:
    def __init__(self, db: Database, cipher: KeyCipher):
        self.db = db
        self.cipher = cipher

    def load(self) -> Settings:
        rows = self.db.query("SELECT * FROM settings WHERE id = 1")
        if not rows:
            return default_settings()
        r = rows[0]
        key = self.cipher.decrypt(r["api_key_enc"]) if r["api_key_enc"] else None
        return Settings(
            provider=r["provider"], model=r["model"], api_key=key, base_url=r["base_url"],
            extractor_model=r["extractor_model"] or None, rpm_limit=int(r["rpm_limit"]),
            confidence_threshold=float(r["confidence_threshold"]),
        )

    def save(self, settings: Settings) -> Settings:
        get_provider(settings.provider)  # raises KeyError for unknown providers
        existing = self.db.query("SELECT api_key_enc FROM settings WHERE id = 1")
        if settings.api_key:
            key_enc = self.cipher.encrypt(settings.api_key)
        else:
            key_enc = existing[0]["api_key_enc"] if existing else None
        params = {
            "provider": settings.provider, "model": settings.model, "base_url": settings.base_url or None,
            "extractor_model": settings.extractor_model or None, "key": key_enc,
            "rpm": int(settings.rpm_limit), "thr": float(settings.confidence_threshold),
        }
        if existing:
            self.db.execute(
                "UPDATE settings SET provider = :provider, model = :model, base_url = :base_url, "
                "extractor_model = :extractor_model, api_key_enc = :key, rpm_limit = :rpm, "
                "confidence_threshold = :thr, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                params,
            )
        else:
            self.db.execute(
                "INSERT INTO settings (id, provider, model, base_url, extractor_model, api_key_enc, "
                "rpm_limit, confidence_threshold) VALUES (1, :provider, :model, :base_url, "
                ":extractor_model, :key, :rpm, :thr)",
                params,
            )
        return self.load()

    def ensure_seeded(self, env: Mapping[str, str]) -> None:
        if self.db.query("SELECT id FROM settings WHERE id = 1"):
            return
        provider_id = env.get("LLM_PROVIDER") or DEFAULT_PROVIDER
        spec = get_provider(provider_id)
        self.save(Settings(
            provider=spec.id,
            model=env.get("LLM_MODEL") or spec.default_model,
            api_key=env.get("LLM_API_KEY") or None,
            rpm_limit=spec.default_rpm,
        ))
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_settings_store.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sms/providers/settings.py tests/unit/test_settings_store.py
git commit -m "feat: encrypted settings store with env seeding

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Rate limiting and retryable-error classification

**Files:**
- Create: `src/sms/providers/ratelimit.py`, `src/sms/providers/errors.py`
- Test: `tests/unit/test_ratelimit.py`, `tests/unit/test_errors.py`

**Interfaces:**
- Produces: `TokenBucket(rpm: int, clock=time.monotonic, sleep=time.sleep)` with `.acquire() -> None`; `RateLimitedAgent(agent, bucket)` exposing `.run(x)`, `.client`, `.model`; `is_retryable(exc: BaseException) -> bool`; `error_message(exc: BaseException, limit: int = 300) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_ratelimit.py`:

```python
from sms.providers.ratelimit import RateLimitedAgent, TokenBucket


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_bucket_allows_rpm_calls_then_waits():
    clock = FakeClock()
    b = TokenBucket(rpm=2, clock=clock.now, sleep=clock.sleep)
    b.acquire(); b.acquire()
    assert clock.slept == []
    b.acquire()
    assert len(clock.slept) == 1 and 0 < clock.slept[0] <= 60


def test_bucket_zero_rpm_never_waits():
    clock = FakeClock()
    b = TokenBucket(rpm=0, clock=clock.now, sleep=clock.sleep)
    for _ in range(50):
        b.acquire()
    assert clock.slept == []


def test_rate_limited_agent_delegates_and_exposes_client_model():
    class Agent:
        client = object(); model = "m"
        def run(self, x): return x + 1
    calls = []
    class Bucket:
        def acquire(self): calls.append(1)
    wrapped = RateLimitedAgent(Agent(), Bucket())
    assert wrapped.run(1) == 2 and calls == [1]
    assert wrapped.model == "m" and wrapped.client is Agent.client
```

`tests/unit/test_errors.py`:

```python
import httpx
import openai

from sms.providers.errors import error_message, is_retryable


def _status_error(code):
    resp = httpx.Response(code, request=httpx.Request("POST", "https://x"))
    return openai.APIStatusError("boom", response=resp, body=None)


def test_429_and_5xx_retryable():
    assert is_retryable(_status_error(429))
    assert is_retryable(_status_error(503))


def test_4xx_not_retryable():
    assert not is_retryable(_status_error(400))
    assert not is_retryable(_status_error(401))
    assert not is_retryable(ValueError("bad"))


def test_connection_and_timeout_retryable():
    req = httpx.Request("POST", "https://x")
    assert is_retryable(openai.APIConnectionError(request=req))
    assert is_retryable(openai.APITimeoutError(request=req))
    assert is_retryable(TimeoutError())


def test_error_message_trims():
    assert len(error_message(RuntimeError("x" * 500))) <= 300
    assert error_message(_status_error(429)).startswith("HTTP 429")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_ratelimit.py tests/unit/test_errors.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/sms/providers/ratelimit.py`:

```python
import threading
import time
from collections import deque
from typing import Any, Callable, Deque


class TokenBucket:
    """Sliding-window limiter: at most `rpm` acquisitions in any 60 s window. rpm<=0 disables."""

    def __init__(self, rpm: int, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.rpm = int(rpm)
        self._clock = clock
        self._sleep = sleep
        self._stamps: Deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self.rpm <= 0:
            return
        while True:
            with self._lock:
                now = self._clock()
                while self._stamps and now - self._stamps[0] >= 60.0:
                    self._stamps.popleft()
                if len(self._stamps) < self.rpm:
                    self._stamps.append(now)
                    return
                wait = 60.0 - (now - self._stamps[0])
            self._sleep(max(wait, 0.01))


class RateLimitedAgent:
    """Wraps an AtomicAgent so every .run() first takes a token. Keeps .client/.model for wire_metrics."""

    def __init__(self, agent: Any, bucket: TokenBucket):
        self._agent = agent
        self._bucket = bucket

    def run(self, user_input: Any) -> Any:
        self._bucket.acquire()
        return self._agent.run(user_input)

    @property
    def client(self) -> Any:
        return self._agent.client

    @property
    def model(self) -> Any:
        return self._agent.model

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)
```

`src/sms/providers/errors.py`:

```python
RETRYABLE_STATUSES = {408, 409, 425, 429}


def _status(exc: BaseException):
    code = getattr(exc, "status_code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
    return code


def is_retryable(exc: BaseException) -> bool:
    code = _status(exc)
    if isinstance(code, int):
        return code in RETRYABLE_STATUSES or code >= 500
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    name = type(exc).__name__
    return "Timeout" in name or "Connection" in name


def error_message(exc: BaseException, limit: int = 300) -> str:
    code = _status(exc)
    text = str(exc) or type(exc).__name__
    msg = f"HTTP {code}: {text}" if isinstance(code, int) else text
    return msg[:limit]
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_ratelimit.py tests/unit/test_errors.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sms/providers/ratelimit.py src/sms/providers/errors.py tests/unit/test_ratelimit.py tests/unit/test_errors.py
git commit -m "feat: token-bucket rate limiter and retryable error classification

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Test-connection probe

**Files:**
- Create: `src/sms/providers/probe.py`
- Modify: `pyproject.toml` (Pillow)
- Test: `tests/unit/test_probe.py`, `tests/live/__init__.py`, `tests/live/test_tokenrouter_live.py`

**Interfaces:**
- Consumes: `build_client`.
- Produces: `Check(ok: bool, latency_ms: int, error: str | None)`, `ProbeResult(text: Check, vision: Check)` with `.to_dict()`; `probe(provider, model, api_key, extractor_model=None, base_url=None, client_factory=build_client) -> ProbeResult`; `render_number_png(number: int) -> bytes`.

- [ ] **Step 1: Add Pillow**

```bash
uv add "pillow>=10"
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_probe.py`:

```python
from sms.providers.probe import Digits, Pong, ProbeResult, probe, render_number_png


class FakeInstructor:
    """Mimics instructor client .chat.completions.create(response_model=...)."""

    def __init__(self, text_ok=True, vision_number=None, raise_text=None):
        self.text_ok = text_ok
        self.vision_number = vision_number
        self.raise_text = raise_text
        self.calls = []

        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                rm = kwargs["response_model"]
                if rm is Pong:
                    if outer.raise_text:
                        raise outer.raise_text
                    return Pong(ok=outer.text_ok)
                if rm is Digits:
                    return Digits(number=outer.vision_number)
                raise AssertionError(rm)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_render_png_is_png():
    assert render_number_png(42)[:8] == b"\x89PNG\r\n\x1a\n"


def test_probe_success(monkeypatch):
    fake = FakeInstructor(vision_number=None)

    def factory(provider, api_key, base_url=None):
        return fake

    monkeypatch.setattr("sms.providers.probe.random.randint", lambda a, b: 37)
    fake.vision_number = 37
    r = probe("tokenrouter", "z-ai/glm-5.3-free", "k", client_factory=factory)
    assert r.text.ok and r.vision.ok and r.text.error is None
    assert fake.calls[0]["model"] == "z-ai/glm-5.3-free"


def test_probe_uses_extractor_model_for_vision(monkeypatch):
    fake = FakeInstructor(vision_number=5)
    monkeypatch.setattr("sms.providers.probe.random.randint", lambda a, b: 5)
    probe("openai", "gpt-5.5", "k", extractor_model="gpt-5-mini", client_factory=lambda *a, **k: fake)
    assert fake.calls[1]["model"] == "gpt-5-mini"


def test_probe_vision_mismatch_is_failure(monkeypatch):
    fake = FakeInstructor(vision_number=11)
    monkeypatch.setattr("sms.providers.probe.random.randint", lambda a, b: 22)
    r = probe("openai", "gpt-5-mini", "k", client_factory=lambda *a, **k: fake)
    assert r.text.ok and not r.vision.ok and "22" in r.vision.error


def test_probe_reports_provider_error():
    fake = FakeInstructor(raise_text=RuntimeError("invalid api key"))
    r = probe("openai", "gpt-5-mini", "k", client_factory=lambda *a, **k: fake)
    assert not r.text.ok and "invalid api key" in r.text.error
    assert isinstance(r.to_dict()["text"]["latency_ms"], int)
```

`tests/live/__init__.py`: empty.

`tests/live/test_tokenrouter_live.py`:

```python
import os

import pytest

from sms.providers.probe import probe

pytestmark = pytest.mark.skipif(
    os.environ.get("SMS_LIVE_TESTS") != "1" or not os.environ.get("TOKENROUTER_API_KEY"),
    reason="set SMS_LIVE_TESTS=1 and TOKENROUTER_API_KEY to run",
)


def test_glm_free_text_and_vision():
    r = probe("tokenrouter", "z-ai/glm-5.3-free", os.environ["TOKENROUTER_API_KEY"])
    assert r.text.ok, r.text.error
    assert r.vision.ok, r.vision.error
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_probe.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

`src/sms/providers/probe.py`:

```python
import base64
import io
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from sms.providers.client import build_client
from sms.providers.errors import error_message


class Pong(BaseModel):
    ok: bool = Field(..., description="True if you can read this")


class Digits(BaseModel):
    number: int = Field(..., description="The number shown in the image")


@dataclass
class Check:
    ok: bool
    latency_ms: int
    error: Optional[str] = None


@dataclass
class ProbeResult:
    text: Check
    vision: Check

    def to_dict(self) -> dict:
        return {"text": self.text.__dict__, "vision": self.vision.__dict__}


def render_number_png(number: int) -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (160, 80), "white")
    draw = ImageDraw.Draw(img)
    text = str(number)
    # Default bitmap font is small; scale by drawing then resizing for legibility.
    small = Image.new("RGB", (40, 20), "white")
    ImageDraw.Draw(small).text((2, 4), text, fill="black")
    img.paste(small.resize((160, 80), Image.NEAREST))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _timed(fn: Callable[[], Any]) -> Check:
    t0 = time.monotonic()
    try:
        fn()
        return Check(ok=True, latency_ms=int((time.monotonic() - t0) * 1000))
    except AssertionError as e:
        return Check(ok=False, latency_ms=int((time.monotonic() - t0) * 1000), error=str(e))
    except Exception as e:  # noqa: BLE001 - we report every provider error to the teacher
        return Check(ok=False, latency_ms=int((time.monotonic() - t0) * 1000), error=error_message(e))


def probe(provider: str, model: str, api_key: str, extractor_model: Optional[str] = None,
          base_url: Optional[str] = None, client_factory: Callable[..., Any] = build_client) -> ProbeResult:
    client = client_factory(provider, api_key, base_url=base_url)

    def text_check() -> None:
        out = client.chat.completions.create(
            model=model,
            response_model=Pong,
            messages=[{"role": "user", "content": "Reply with ok=true."}],
            max_retries=0,
            max_tokens=256,
        )
        assert out.ok, "Model replied but did not return ok=true"

    number = random.randint(10, 99)
    png_b64 = base64.b64encode(render_number_png(number)).decode()

    def vision_check() -> None:
        out = client.chat.completions.create(
            model=extractor_model or model,
            response_model=Digits,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "What two-digit number is written in this image?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_b64}"}},
                ],
            }],
            max_retries=0,
            max_tokens=256,
        )
        assert out.number == number, f"Model read {out.number}, expected {number} — it may not support images"

    text = _timed(text_check)
    vision = _timed(vision_check) if text.ok else Check(ok=False, latency_ms=0, error="Skipped — text check failed")
    return ProbeResult(text=text, vision=vision)
```

Note for the Anthropic transport: instructor's Anthropic client also accepts the OpenAI-style `image_url` content part and converts it (instructor ≥1.x multimodal support). If the live Anthropic path rejects it, switch the vision message to `instructor.Image.from_base64(png_b64, "image/png")` in the content list — instructor normalises `Image` objects for every provider.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_probe.py -q`
Expected: PASS (5 tests). `tests/live` skips.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/sms/providers/probe.py tests/unit/test_probe.py tests/live
git commit -m "feat: provider probe (text + vision test connection)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Page storage and upload processing

**Files:**
- Create: `src/sms/storage.py`
- Modify: `pyproject.toml` (pymupdf, pillow-heif)
- Test: `tests/unit/test_storage.py`

**Interfaces:**
- Produces: `UploadError(Exception)` with `.filename`; `ProcessedPage(sha256, storage_path, width, height, source_filename)`; `PageStorage(root: Path)` with `.put_jpeg(data: bytes) -> tuple[str, str]` (sha256, relative path), `.read(relative_path) -> bytes`, `.abs(relative_path) -> Path`; `process_uploads(files: list[tuple[str, bytes]], storage: PageStorage, max_pages=60, max_total_bytes=50*1024*1024) -> list[ProcessedPage]`; constants `MAX_LONG_EDGE = 2000`, `JPEG_QUALITY = 85`.

- [ ] **Step 1: Add dependencies**

```bash
uv add "pymupdf>=1.24" "pillow-heif>=0.18"
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_storage.py`:

```python
import io

import fitz  # PyMuPDF
import pytest
from PIL import Image

from sms.storage import MAX_LONG_EDGE, PageStorage, UploadError, process_uploads


def _png(w, h, color="white"):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _pdf(pages):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((50, 100), f"page {i + 1}")
    return doc.tobytes()


@pytest.fixture
def storage(tmp_path):
    return PageStorage(tmp_path / "data")


def test_png_becomes_jpeg_and_is_content_addressed(storage):
    pages = process_uploads([("a.png", _png(100, 50))], storage)
    assert len(pages) == 1
    p = pages[0]
    assert p.storage_path == f"pages/{p.sha256}.jpg" and (p.width, p.height) == (100, 50)
    assert storage.read(p.storage_path)[:3] == b"\xff\xd8\xff"
    again = process_uploads([("b.png", _png(100, 50))], storage)
    assert again[0].sha256 == p.sha256


def test_pdf_splits_into_pages_in_order(storage):
    pages = process_uploads([("scan.pdf", _pdf(3))], storage)
    assert len(pages) == 3 and all(p.source_filename == "scan.pdf" for p in pages)
    assert len({p.sha256 for p in pages}) == 3


def test_files_ordered_then_pdf_pages(storage):
    pages = process_uploads([("1.png", _png(10, 10, "red")), ("2.pdf", _pdf(2)), ("3.png", _png(10, 10, "blue"))], storage)
    assert [p.source_filename for p in pages] == ["1.png", "2.pdf", "2.pdf", "3.png"]


def test_large_image_is_downscaled(storage):
    pages = process_uploads([("big.png", _png(4000, 2000))], storage)
    assert max(pages[0].width, pages[0].height) == MAX_LONG_EDGE


def test_bad_file_names_the_file(storage):
    with pytest.raises(UploadError) as e:
        process_uploads([("notes.txt", b"hello")], storage)
    assert e.value.filename == "notes.txt"


def test_corrupt_pdf_names_the_file(storage):
    with pytest.raises(UploadError) as e:
        process_uploads([("x.pdf", b"%PDF-1.4 garbage")], storage)
    assert e.value.filename == "x.pdf"


def test_page_limit(storage):
    with pytest.raises(UploadError):
        process_uploads([("many.pdf", _pdf(3))], storage, max_pages=2)


def test_total_size_limit(storage):
    with pytest.raises(UploadError):
        process_uploads([("a.png", _png(10, 10))], storage, max_total_bytes=10)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_storage.py -q`
Expected: FAIL with `ModuleNotFoundError: sms.storage`.

- [ ] **Step 4: Implement**

`src/sms/storage.py`:

```python
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_LONG_EDGE = 2000
JPEG_QUALITY = 85
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
PDF_EXTS = {".pdf"}


class UploadError(Exception):
    def __init__(self, filename: str, message: str):
        super().__init__(f"{filename}: {message}")
        self.filename = filename
        self.message = message


@dataclass(frozen=True)
class ProcessedPage:
    sha256: str
    storage_path: str
    width: int
    height: int
    source_filename: str


class PageStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        (self.root / "pages").mkdir(parents=True, exist_ok=True)

    def put_jpeg(self, data: bytes) -> Tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        rel = f"pages/{digest}.jpg"
        path = self.root / rel
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return digest, rel

    def abs(self, relative_path: str) -> Path:
        return self.root / relative_path

    def read(self, relative_path: str) -> bytes:
        return self.abs(relative_path).read_bytes()


def _register_heif() -> None:
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:  # pragma: no cover
        pass


def _normalise(img: Image.Image) -> Tuple[bytes, int, int]:
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    long_edge = max(w, h)
    if long_edge > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / long_edge
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue(), img.size[0], img.size[1]


def _images_from_pdf(filename: str, data: bytes) -> List[Image.Image]:
    import fitz
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        if doc.page_count == 0:
            raise UploadError(filename, "PDF has no pages")
        out = []
        for page in doc:
            pix = page.get_pixmap(dpi=150, colorspace=fitz.csRGB, alpha=False)
            out.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return out
    except UploadError:
        raise
    except Exception as e:  # noqa: BLE001
        raise UploadError(filename, f"not a valid PDF ({e})") from e


def _image_from_bytes(filename: str, data: bytes) -> Image.Image:
    _register_heif()
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img
    except (UnidentifiedImageError, OSError) as e:
        raise UploadError(filename, "not a readable image (use JPG, PNG or HEIC)") from e


def process_uploads(files: List[Tuple[str, bytes]], storage: PageStorage, max_pages: int = 60,
                    max_total_bytes: int = 50 * 1024 * 1024) -> List[ProcessedPage]:
    total = sum(len(b) for _, b in files)
    if total > max_total_bytes:
        raise UploadError(files[0][0] if files else "upload", f"upload is {total // (1024 * 1024)} MB; the limit is {max_total_bytes // (1024 * 1024)} MB")
    pages: List[ProcessedPage] = []
    for filename, data in files:
        ext = Path(filename).suffix.lower()
        if ext in PDF_EXTS:
            images = _images_from_pdf(filename, data)
        elif ext in IMAGE_EXTS:
            images = [_image_from_bytes(filename, data)]
        else:
            raise UploadError(filename, "unsupported file type (use PDF, JPG, PNG or HEIC)")
        for img in images:
            if len(pages) >= max_pages:
                raise UploadError(filename, f"too many pages; the limit is {max_pages} per script")
            jpeg, w, h = _normalise(img)
            digest, rel = storage.put_jpeg(jpeg)
            pages.append(ProcessedPage(sha256=digest, storage_path=rel, width=w, height=h, source_filename=filename))
    return pages
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_storage.py -q`
Expected: PASS (8 tests).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/sms/storage.py tests/unit/test_storage.py
git commit -m "feat: page storage and PDF/image upload processing

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Job store, mark job, worker loop

**Files:**
- Create: `src/sms/worker/__init__.py`, `src/sms/worker/jobs.py`, `src/sms/worker/mark_job.py`, `src/sms/worker/worker.py`
- Modify: `src/sms/agents/extractor.py`, `src/sms/agents/marker.py`, `src/sms/agents/reviewer.py`, `src/sms/agents/feedback.py`, `src/sms/agents/reflection.py` (add `model_api_parameters` passthrough)
- Test: `tests/unit/test_jobs.py`, `tests/unit/test_worker.py`, `tests/integration/test_agent_factories.py` (append)

**Interfaces:**
- Consumes: `Database`, `SettingsStore`, `PageStorage`, `build_client`, `TokenBucket`, `RateLimitedAgent`, `is_retryable`, `error_message`, agent factories, `MarkingPipeline`, `wire_metrics`.
- Produces:
  - `JobStore(db)` with `.enqueue(kind, submission_id) -> int`, `.claim() -> dict | None` (sets `running`, `started_at`, `attempts+1`, submission `marking`), `.finish(job_id)`, `.retry_later(job_id, delay_s, error)` (job `queued`, `not_before`, submission `queued`), `.fail(job_id, error)` (job + submission `failed`), `.reset_running() -> int`, `.heartbeat()`, `.last_heartbeat() -> str | None`, `.job_for_submission(submission_id) -> dict | None`.
  - `run_mark_job(db, storage, settings_store, submission_id, pipeline_factory=None) -> None` — raises on failure.
  - `Worker(db, storage, settings_store, runner=run_mark_job, poll_s=2.0, max_attempts=5, base_backoff_s=30)` with `.run_once() -> bool`, `.run_forever(stop: threading.Event)`, `.start_thread(stop) -> threading.Thread`.
  - `MAX_ATTEMPTS = 5`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_jobs.py`:

```python
import pytest

from sms.memory.db import Database
from sms.worker.jobs import JobStore


@pytest.fixture
def db(tmp_path):
    return Database(path=str(tmp_path / "s.db"))


def _submission(db):
    return db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) "
                     "VALUES ('s', 'math', '', '{}', 'uploaded') RETURNING id")


def test_enqueue_claim_finish(db):
    js = JobStore(db)
    sid = _submission(db)
    jid = js.enqueue("mark", sid)
    job = js.claim()
    assert job["id"] == jid and job["status"] == "running" and job["attempts"] == 1
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "marking"
    assert js.claim() is None
    js.finish(jid)
    assert db.query("SELECT status, finished_at FROM jobs WHERE id = ?", (jid,))[0]["status"] == "done"


def test_retry_later_respects_not_before(db):
    js = JobStore(db)
    sid = _submission(db)
    jid = js.enqueue("mark", sid)
    js.claim()
    js.retry_later(jid, delay_s=3600, error="HTTP 429")
    row = db.query("SELECT status, error, not_before FROM jobs WHERE id = ?", (jid,))[0]
    assert row["status"] == "queued" and row["error"] == "HTTP 429" and row["not_before"]
    assert js.claim() is None
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "queued"
    js.retry_later(jid, delay_s=0, error="x")
    assert js.claim()["id"] == jid


def test_fail_marks_submission_failed(db):
    js = JobStore(db)
    sid = _submission(db)
    jid = js.enqueue("mark", sid)
    js.claim()
    js.fail(jid, "boom")
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "failed"
    assert js.job_for_submission(sid)["error"] == "boom"


def test_reset_running(db):
    js = JobStore(db)
    sid = _submission(db)
    js.enqueue("mark", sid)
    js.claim()
    assert js.reset_running() == 1
    assert js.claim() is not None


def test_heartbeat(db):
    js = JobStore(db)
    assert js.last_heartbeat() is None
    js.heartbeat()
    assert js.last_heartbeat()
    js.heartbeat()
    assert db.query("SELECT COUNT(*) AS c FROM worker_heartbeat")[0]["c"] == 1


def test_claim_orders_by_created(db):
    js = JobStore(db)
    a = js.enqueue("mark", _submission(db))
    b = js.enqueue("mark", _submission(db))
    assert js.claim()["id"] == a and js.claim()["id"] == b
```

`tests/unit/test_worker.py`:

```python
import threading

import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore
from sms.storage import PageStorage
from sms.worker.jobs import JobStore
from sms.worker.mark_job import run_mark_job
from sms.worker.worker import Worker


@pytest.fixture
def env(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0))
    storage = PageStorage(tmp_path / "data")
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) VALUES "
                    "('s', 'math', 'ctx', '{\"criterion_defs\": [{\"id\": \"c1\", \"description\": \"d\", \"max_score\": 2}]}', 'uploaded') RETURNING id")
    digest, rel = storage.put_jpeg(b"\xff\xd8\xffjpegbytes")
    db.execute("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height) VALUES (?, 0, ?, ?, 10, 10)",
               (sid, digest, rel))
    return db, store, storage, sid


class FakePipeline:
    def __init__(self, escalations):
        self.escalations = escalations
        self.calls = []

    def run(self, images, assignment_context, rubric, submission_id=None):
        self.calls.append((images, assignment_context, rubric, submission_id))
        from sms.pipeline.marking_pipeline import MarkingResult
        from sms.schemas.extraction import ExtractedScript
        from sms.schemas.marking import MarkedScript
        return MarkingResult(run_id="r1", extracted=ExtractedScript(questions=[]),
                             final_marks=MarkedScript(marks=[]), escalations=self.escalations)


def test_run_mark_job_done(env):
    db, store, storage, sid = env
    fp = FakePipeline(escalations=[])
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: fp)
    assert fp.calls[0][0] == [b"\xff\xd8\xffjpegbytes"] and fp.calls[0][3] == sid
    row = db.query("SELECT status, run_id FROM submissions WHERE id = ?", (sid,))[0]
    assert row["status"] == "done" and row["run_id"] == "r1"


def test_run_mark_job_needs_you(env):
    db, store, storage, sid = env
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline(["q2"]))
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "needs_you"


def test_run_mark_job_without_key_raises_non_retryable(env):
    db, store, storage, sid = env
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=0))
    db.execute("UPDATE settings SET api_key_enc = NULL")
    with pytest.raises(RuntimeError, match="API key"):
        run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline([]))


def test_worker_success_path(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("mark", sid)
    w = Worker(db, storage, store, runner=lambda db_, st_, ss_, sid_: None)
    assert w.run_once() is True
    assert db.query("SELECT status FROM jobs")[0]["status"] == "done"
    assert w.run_once() is False


def test_worker_retryable_error_requeues_with_backoff(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("mark", sid)
    import httpx, openai
    err = openai.APIStatusError("rl", response=httpx.Response(429, request=httpx.Request("POST", "https://x")), body=None)

    def runner(*a):
        raise err

    w = Worker(db, storage, store, runner=runner)
    w.run_once()
    row = db.query("SELECT status, attempts, not_before, error FROM jobs")[0]
    assert row["status"] == "queued" and row["attempts"] == 1 and row["not_before"] and "429" in row["error"]


def test_worker_non_retryable_fails(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("mark", sid)

    def runner(*a):
        raise ValueError("bad rubric")

    Worker(db, storage, store, runner=runner).run_once()
    assert db.query("SELECT status FROM jobs")[0]["status"] == "failed"
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "failed"


def test_worker_gives_up_after_max_attempts(env):
    db, store, storage, sid = env
    js = JobStore(db)
    jid = js.enqueue("mark", sid)
    db.execute("UPDATE jobs SET attempts = 4 WHERE id = ?", (jid,))

    def runner(*a):
        raise TimeoutError()

    Worker(db, storage, store, runner=runner).run_once()
    assert db.query("SELECT status FROM jobs")[0]["status"] == "failed"


def test_worker_resets_running_on_start_and_heartbeats(env):
    db, store, storage, sid = env
    js = JobStore(db)
    js.enqueue("mark", sid)
    js.claim()
    stop = threading.Event()
    w = Worker(db, storage, store, runner=lambda *a: None, poll_s=0.01)
    t = w.start_thread(stop)
    import time
    for _ in range(200):
        if db.query("SELECT status FROM jobs")[0]["status"] == "done":
            break
        time.sleep(0.01)
    stop.set(); t.join(timeout=2)
    assert db.query("SELECT status FROM jobs")[0]["status"] == "done"
    assert js.last_heartbeat()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_jobs.py tests/unit/test_worker.py -q`
Expected: FAIL with `ModuleNotFoundError: sms.worker`.

- [ ] **Step 3: Let every agent factory pass provider API params through**

In each of `src/sms/agents/{extractor,marker,reviewer,feedback,reflection}.py` add a trailing keyword parameter `model_api_parameters: Optional[dict] = None` to the `build_*` function (import `Optional` where missing) and pass it into `AgentConfig(...)` as `model_api_parameters=model_api_parameters`. Anthropic rejects requests without `max_tokens`; the registry's `api_params` supplies it.

Append to `tests/integration/test_agent_factories.py`:

```python
def test_factories_accept_model_api_parameters():
    from sms.agents.extractor import build_extractor
    from sms.agents.feedback import build_feedback
    from sms.agents.marker import build_marker
    from sms.agents.reflection import build_reflection
    from sms.agents.reviewer import build_reviewer
    import instructor, openai
    client = instructor.from_openai(openai.OpenAI(api_key="x"))
    for build in (build_extractor, build_feedback, build_reflection):
        agent = build(client=client, model="m", model_api_parameters={"max_tokens": 10})
        assert agent.model_api_parameters == {"max_tokens": 10}
    for build in (build_marker, build_reviewer):
        agent = build(client=client, model="m", subject="math", model_api_parameters={"max_tokens": 10})
        assert agent.model_api_parameters == {"max_tokens": 10}
```

Run `uv run pytest tests/integration/test_agent_factories.py -q` — PASS. (`AtomicAgent` stores the dict as `self.model_api_parameters`; if the attribute name differs in the installed version, assert via `agent._get_completion_kwargs()` instead.)

- [ ] **Step 4: Implement the job store**

`src/sms/worker/__init__.py`: empty.

`src/sms/worker/jobs.py`:

```python
from datetime import datetime, timedelta, timezone
from typing import Optional

from sms.memory.db import Database

MAX_ATTEMPTS = 5


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _in(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


class JobStore:
    def __init__(self, db: Database):
        self.db = db

    def enqueue(self, kind: str, submission_id: Optional[int]) -> int:
        job_id = self.db.insert(
            "INSERT INTO jobs (kind, submission_id, status) VALUES (:k, :s, 'queued') RETURNING id",
            {"k": kind, "s": submission_id},
        )
        if submission_id is not None:
            self.db.execute("UPDATE submissions SET status = 'queued', updated_at = CURRENT_TIMESTAMP WHERE id = :s",
                            {"s": submission_id})
        return job_id

    def claim(self) -> Optional[dict]:
        now = _now()
        with self.db.transaction() as tx:
            lock = " FOR UPDATE SKIP LOCKED" if not self.db.is_sqlite else ""
            rows = tx.query(
                "SELECT id FROM jobs WHERE status = 'queued' AND (not_before IS NULL OR not_before <= :now) "
                f"ORDER BY created_at, id LIMIT 1{lock}",
                {"now": now},
            )
            if not rows:
                return None
            job_id = rows[0]["id"]
            changed = tx.execute(
                "UPDATE jobs SET status = 'running', started_at = :now, attempts = attempts + 1, error = NULL "
                "WHERE id = :id AND status = 'queued'",
                {"now": now, "id": job_id},
            )
            if changed != 1:
                return None
            tx.execute(
                "UPDATE submissions SET status = 'marking', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = (SELECT submission_id FROM jobs WHERE id = :id)",
                {"id": job_id},
            )
            return tx.query("SELECT * FROM jobs WHERE id = :id", {"id": job_id})[0]

    def finish(self, job_id: int) -> None:
        self.db.execute("UPDATE jobs SET status = 'done', finished_at = :now WHERE id = :id",
                        {"now": _now(), "id": job_id})

    def retry_later(self, job_id: int, delay_s: float, error: str) -> None:
        with self.db.transaction() as tx:
            tx.execute(
                "UPDATE jobs SET status = 'queued', not_before = :nb, error = :err WHERE id = :id",
                {"nb": _in(delay_s), "err": error, "id": job_id},
            )
            tx.execute(
                "UPDATE submissions SET status = 'queued', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = (SELECT submission_id FROM jobs WHERE id = :id)",
                {"id": job_id},
            )

    def fail(self, job_id: int, error: str) -> None:
        with self.db.transaction() as tx:
            tx.execute("UPDATE jobs SET status = 'failed', finished_at = :now, error = :err WHERE id = :id",
                       {"now": _now(), "err": error, "id": job_id})
            tx.execute(
                "UPDATE submissions SET status = 'failed', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = (SELECT submission_id FROM jobs WHERE id = :id)",
                {"id": job_id},
            )

    def reset_running(self) -> int:
        with self.db.transaction() as tx:
            tx.execute(
                "UPDATE submissions SET status = 'queued' WHERE id IN "
                "(SELECT submission_id FROM jobs WHERE status = 'running' AND submission_id IS NOT NULL)"
            )
            return tx.execute("UPDATE jobs SET status = 'queued', started_at = NULL WHERE status = 'running'")

    def heartbeat(self) -> None:
        now = _now()
        if self.db.execute("UPDATE worker_heartbeat SET last_seen = :now WHERE id = 1", {"now": now}) == 0:
            self.db.execute("INSERT INTO worker_heartbeat (id, last_seen) VALUES (1, :now)", {"now": now})

    def last_heartbeat(self) -> Optional[str]:
        rows = self.db.query("SELECT last_seen FROM worker_heartbeat WHERE id = 1")
        return str(rows[0]["last_seen"]) if rows else None

    def job_for_submission(self, submission_id: int) -> Optional[dict]:
        rows = self.db.query("SELECT * FROM jobs WHERE submission_id = :s ORDER BY id DESC LIMIT 1",
                             {"s": submission_id})
        return rows[0] if rows else None
```

- [ ] **Step 5: Implement the mark job**

`src/sms/worker/mark_job.py`:

```python
from typing import Any, Callable, Optional

from sms.agents.extractor import build_extractor
from sms.agents.feedback import build_feedback
from sms.agents.marker import build_marker
from sms.agents.reviewer import build_reviewer
from sms.memory.db import Database
from sms.memory.metrics_hook import wire_metrics
from sms.pipeline.marking_pipeline import MarkingPipeline
from sms.providers.client import build_client
from sms.providers.ratelimit import RateLimitedAgent, TokenBucket
from sms.providers.registry import get_provider
from sms.providers.settings import SettingsStore
from sms.schemas.marking import Rubric
from sms.storage import PageStorage


def _default_pipeline_factory(*, db: Database, settings, subject: str) -> MarkingPipeline:
    client = build_client(settings.provider, settings.api_key, base_url=settings.base_url)
    params = get_provider(settings.provider).api_params
    bucket = TokenBucket(settings.rpm_limit)
    agents = {
        "extractor": build_extractor(client=client, model=settings.effective_extractor_model, model_api_parameters=params),
        "marker": build_marker(client=client, model=settings.model, subject=subject, db=db, model_api_parameters=params),
        "reviewer": build_reviewer(client=client, model=settings.model, subject=subject, db=db, model_api_parameters=params),
        "feedback": build_feedback(client=client, model=settings.model, model_api_parameters=params),
    }
    wire_metrics(db=db, agents=agents)
    limited = {k: RateLimitedAgent(v, bucket) for k, v in agents.items()}
    return MarkingPipeline(db=db, subject=subject, confidence_threshold=settings.confidence_threshold, **limited)


def run_mark_job(db: Database, storage: PageStorage, settings_store: SettingsStore, submission_id: int,
                 pipeline_factory: Optional[Callable[..., Any]] = None) -> None:
    rows = db.query("SELECT * FROM submissions WHERE id = :id", {"id": submission_id})
    if not rows:
        raise ValueError(f"submission {submission_id} not found")
    sub = rows[0]
    settings = settings_store.load()
    if not settings.has_key:
        raise RuntimeError("No API key configured — add one under Settings")
    pages = db.query("SELECT storage_path FROM pages WHERE submission_id = :id ORDER BY page_index",
                     {"id": submission_id})
    images = [storage.read(p["storage_path"]) for p in pages]
    rubric = Rubric.model_validate_json(sub["rubric_json"])
    factory = pipeline_factory or _default_pipeline_factory
    pipeline = factory(db=db, settings=settings, subject=sub["subject"])
    result = pipeline.run(images=images, assignment_context=sub["context"] or "Student script",
                          rubric=rubric, submission_id=submission_id)
    status = "needs_you" if result.escalations else "done"
    db.execute("UPDATE submissions SET status = :st, run_id = :rid, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
               {"st": status, "rid": result.run_id, "id": submission_id})
```

- [ ] **Step 6: Implement the worker loop**

`src/sms/worker/worker.py`:

```python
import logging
import threading
import time
from typing import Callable

from sms.memory.db import Database
from sms.providers.errors import error_message, is_retryable
from sms.providers.settings import SettingsStore
from sms.storage import PageStorage
from sms.worker.jobs import MAX_ATTEMPTS, JobStore
from sms.worker.mark_job import run_mark_job

log = logging.getLogger("sms.worker")

Runner = Callable[[Database, PageStorage, SettingsStore, int], None]


class Worker:
    def __init__(self, db: Database, storage: PageStorage, settings_store: SettingsStore,
                 runner: Runner = run_mark_job, poll_s: float = 2.0, max_attempts: int = MAX_ATTEMPTS,
                 base_backoff_s: float = 30.0):
        self.db = db
        self.storage = storage
        self.settings_store = settings_store
        self.runner = runner
        self.poll_s = poll_s
        self.max_attempts = max_attempts
        self.base_backoff_s = base_backoff_s
        self.jobs = JobStore(db)

    def run_once(self) -> bool:
        job = self.jobs.claim()
        if job is None:
            return False
        try:
            if job["kind"] != "mark":
                raise ValueError(f"unknown job kind {job['kind']!r}")
            self.runner(self.db, self.storage, self.settings_store, job["submission_id"])
            self.jobs.finish(job["id"])
        except Exception as e:  # noqa: BLE001 - every failure is recorded on the job
            msg = error_message(e)
            if is_retryable(e) and job["attempts"] < self.max_attempts:
                delay = self.base_backoff_s * (2 ** (job["attempts"] - 1))
                log.warning("job %s retry in %.0fs: %s", job["id"], delay, msg)
                self.jobs.retry_later(job["id"], delay, msg)
            else:
                log.error("job %s failed: %s", job["id"], msg)
                self.jobs.fail(job["id"], msg)
        return True

    def run_forever(self, stop: threading.Event) -> None:
        reset = self.jobs.reset_running()
        if reset:
            log.info("re-queued %d interrupted job(s)", reset)
        while not stop.is_set():
            try:
                self.jobs.heartbeat()
                worked = self.run_once()
            except Exception:  # noqa: BLE001
                log.exception("worker loop error")
                worked = False
            if not worked:
                stop.wait(self.poll_s)

    def start_thread(self, stop: threading.Event) -> threading.Thread:
        t = threading.Thread(target=self.run_forever, args=(stop,), name="sms-worker", daemon=True)
        t.start()
        return t
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/unit/test_jobs.py tests/unit/test_worker.py -q`
Expected: PASS (13 tests). Then `uv run pytest -q` — all green.

Timestamp note: `JobStore` writes `YYYY-MM-DD HH:MM:SS` strings into `DateTime` columns. SQLite stores them as text; on Postgres, psycopg 3 sends `str` parameters with the *unknown* OID so the server casts them to `timestamp`. Task 20 verifies this on the live Postgres; if Postgres rejects it, switch `_now()`/`_in()` to return naive `datetime` objects (`datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)`) — both dialects accept those.

- [ ] **Step 8: Commit**

```bash
git add src/sms/worker src/sms/agents tests/unit/test_jobs.py tests/unit/test_worker.py tests/integration/test_agent_factories.py
git commit -m "feat: job store, mark job runner and worker loop with retry/backoff

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: FastAPI app skeleton — config, errors, auth, health, SPA mount

**Files:**
- Create: `src/sms/web/__init__.py`, `src/sms/web/config.py`, `src/sms/web/errors.py`, `src/sms/web/deps.py`, `src/sms/web/app.py`, `src/sms/web/routers/__init__.py`, `src/sms/web/routers/auth.py`, `src/sms/web/routers/health.py`
- Modify: `pyproject.toml`
- Test: `tests/web/__init__.py`, `tests/web/conftest.py`, `tests/web/test_auth.py`, `tests/web/test_health.py`

**Interfaces:**
- Produces: `AppConfig(database_url, secret_key, teacher_password, storage_dir: Path, embedded_worker: bool, env: dict)` + `AppConfig.from_env()`; `create_app(config: AppConfig) -> FastAPI` with `app.state.db`, `app.state.settings_store`, `app.state.storage`, `app.state.jobs`, `app.state.config`; deps `get_db(request)`, `get_settings_store(request)`, `get_storage(request)`, `get_jobs(request)`, `require_teacher(request)`; `ApiError(status, code, message)`; `SessionSigner(secret).issue() -> str` / `.verify(token) -> bool`; cookie name `sms_session`.

- [ ] **Step 1: Add dependencies**

```bash
uv add "fastapi>=0.115" "uvicorn[standard]>=0.30" "python-multipart>=0.0.9" "itsdangerous>=2.2" "httpx>=0.27"
```

(`httpx` is needed by FastAPI's `TestClient`.)

- [ ] **Step 2: Write the failing tests**

`tests/web/__init__.py`: empty.

`tests/web/conftest.py`:

```python
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
```

`tests/web/test_auth.py`:

```python
def test_login_sets_cookie_and_me_works(client):
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"password": "letmein"})
    assert r.status_code == 204 and "sms_session" in r.cookies
    assert client.get("/api/auth/me").json() == {"authenticated": True}


def test_wrong_password_401_with_error_shape(client):
    r = client.post("/api/auth/login", json={"password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "bad_password"


def test_logout_clears(auth):
    auth.post("/api/auth/logout")
    assert auth.get("/api/auth/me").status_code == 401


def test_login_rate_limited_after_five_failures(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"password": "nope"})
    r = client.post("/api/auth/login", json={"password": "nope"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_attempts"


def test_tampered_cookie_rejected(client):
    client.cookies.set("sms_session", "garbage")
    assert client.get("/api/auth/me").status_code == 401
```

`tests/web/test_health.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/web -q`
Expected: FAIL with `ModuleNotFoundError: sms.web`.

- [ ] **Step 4: Implement config, errors, deps**

`src/sms/web/__init__.py`, `src/sms/web/routers/__init__.py`: empty.

`src/sms/web/config.py`:

```python
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[3] / "web" / "dist"


@dataclass
class AppConfig:
    database_url: str
    secret_key: str
    teacher_password: str
    storage_dir: Path
    embedded_worker: bool = True
    env: Dict[str, str] = field(default_factory=dict)
    static_dir: Optional[Path] = None

    @classmethod
    def from_env(cls) -> "AppConfig":
        secret = os.environ.get("SECRET_KEY")
        password = os.environ.get("TEACHER_PASSWORD")
        if not secret or not password:
            raise RuntimeError("SECRET_KEY and TEACHER_PASSWORD must be set")
        return cls(
            database_url=os.environ.get("DATABASE_URL", "sqlite:///sms.db"),
            secret_key=secret,
            teacher_password=password,
            storage_dir=Path(os.environ.get("STORAGE_DIR", "./data")),
            embedded_worker=os.environ.get("SMS_EMBEDDED_WORKER", "1") != "0",
            env={k: v for k, v in os.environ.items() if k.startswith("LLM_")},
            static_dir=Path(os.environ["SMS_STATIC_DIR"]) if os.environ.get("SMS_STATIC_DIR") else DEFAULT_STATIC_DIR,
        )
```

`src/sms/web/errors.py`:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})
```

`src/sms/web/deps.py`:

```python
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from sms.web.errors import ApiError

COOKIE = "sms_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30


class SessionSigner:
    def __init__(self, secret: str):
        self._s = URLSafeTimedSerializer(secret, salt="sms-session")

    def issue(self) -> str:
        return self._s.dumps({"role": "teacher"})

    def verify(self, token: str) -> bool:
        try:
            data = self._s.loads(token, max_age=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False
        return data.get("role") == "teacher"


class LoginLimiter:
    """5 failed attempts per IP per 60 s."""

    def __init__(self, limit: int = 5, window_s: float = 60.0):
        self.limit = limit
        self.window_s = window_s
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def blocked(self, ip: str) -> bool:
        q = self._hits[ip]
        now = time.monotonic()
        while q and now - q[0] > self.window_s:
            q.popleft()
        return len(q) >= self.limit

    def record_failure(self, ip: str) -> None:
        self._hits[ip].append(time.monotonic())


def get_db(request: Request):
    return request.app.state.db


def get_settings_store(request: Request):
    return request.app.state.settings_store


def get_storage(request: Request):
    return request.app.state.storage


def get_jobs(request: Request):
    return request.app.state.jobs


def require_teacher(request: Request) -> None:
    token = request.cookies.get(COOKIE)
    if not token or not request.app.state.signer.verify(token):
        raise ApiError(401, "unauthenticated", "Sign in to continue")
```

- [ ] **Step 5: Implement auth and health routers**

`src/sms/web/routers/auth.py`:

```python
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from sms.web.deps import COOKIE, SESSION_MAX_AGE, require_teacher
from sms.web.errors import ApiError

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    password: str


@router.post("/login", status_code=204)
def login(body: LoginBody, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    limiter = request.app.state.login_limiter
    if limiter.blocked(ip):
        raise ApiError(429, "too_many_attempts", "Too many attempts — wait a minute and try again")
    if body.password != request.app.state.config.teacher_password:
        limiter.record_failure(ip)
        raise ApiError(401, "bad_password", "That password is not right")
    secure = request.url.hostname not in ("localhost", "127.0.0.1", "testserver")
    response.set_cookie(COOKIE, request.app.state.signer.issue(), max_age=SESSION_MAX_AGE,
                        httponly=True, samesite="lax", secure=secure, path="/")
    # Return None: FastAPI then sends the injected `response` (with the cookie) as a 204.
    # Returning a new Response object here would DROP the cookie.
    return None


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return None


@router.get("/me")
def me(_: None = Depends(require_teacher)):
    return {"authenticated": True}
```

`src/sms/web/routers/health.py`:

```python
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request):
    try:
        request.app.state.db.query("SELECT 1 AS one")
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"db": f"error: {e}", "worker_last_seen": None})
    return {"db": "ok", "worker_last_seen": request.app.state.jobs.last_heartbeat()}
```

- [ ] **Step 6: Implement the app factory**

`src/sms/web/app.py`:

```python
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import SettingsStore
from sms.storage import PageStorage
from sms.web.config import AppConfig
from sms.web.deps import LoginLimiter, SessionSigner
from sms.web.errors import install_error_handlers
from sms.web.routers import auth, health
from sms.worker.jobs import JobStore
from sms.worker.worker import Worker

log = logging.getLogger("sms.web")


def mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA: /assets/* statically, everything else -> index.html (except /api)."""
    if not (dist / "index.html").exists():
        log.warning("SPA not built at %s — API only", dist)
        return
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str, request: Request):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "No such route"}})
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


def create_app(config: AppConfig) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings_store.ensure_seeded(config.env)
        stop = threading.Event()
        thread: Optional[threading.Thread] = None
        if config.embedded_worker:
            thread = Worker(app.state.db, app.state.storage, app.state.settings_store).start_thread(stop)
        try:
            yield
        finally:
            stop.set()
            if thread:
                thread.join(timeout=5)
            app.state.db.dispose()

    app = FastAPI(title="Smart Marking", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.config = config
    app.state.db = Database(url=config.database_url)
    app.state.settings_store = SettingsStore(app.state.db, KeyCipher(config.secret_key))
    app.state.storage = PageStorage(config.storage_dir)
    app.state.jobs = JobStore(app.state.db)
    app.state.signer = SessionSigner(config.secret_key)
    app.state.login_limiter = LoginLimiter()
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    if config.static_dir:
        mount_spa(app, config.static_dir)
    return app


def app_from_env() -> FastAPI:
    return create_app(AppConfig.from_env())
```

`app.py`'s `app_from_env` is what uvicorn targets: `uvicorn "sms.web.app:app_from_env" --factory`.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/web -q`
Expected: PASS (7 tests). Note: `test_spa_fallback_serves_index_when_built` mounts the SPA after routers, so `/api/nope` is caught by the SPA route's `api/` guard — the assertion expects 404 JSON.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/sms/web tests/web
git commit -m "feat: FastAPI app with password session auth, health check and SPA mount

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Settings and providers API

**Files:**
- Create: `src/sms/web/routers/settings.py`
- Modify: `src/sms/web/app.py` (include router)
- Test: `tests/web/test_settings_api.py`

**Interfaces:**
- Consumes: `SettingsStore`, `registry_as_dicts`, `probe`.
- Produces: `GET /api/providers`, `GET /api/settings`, `PUT /api/settings`, `POST /api/settings/test`.

- [ ] **Step 1: Write the failing tests**

`tests/web/test_settings_api.py`:

```python
from sms.providers.probe import Check, ProbeResult


def test_requires_auth(client):
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/providers").status_code == 401


def test_providers_lists_six(auth):
    body = auth.get("/api/providers").json()
    assert {p["id"] for p in body} == {"tokenrouter", "openrouter", "openai", "anthropic", "moonshot", "qwen"}


def test_get_defaults_and_never_leaks_key(auth):
    s = auth.get("/api/settings").json()
    assert s["provider"] == "tokenrouter" and s["has_key"] is False and "api_key" not in s


def test_put_saves_and_blank_key_keeps(auth):
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-abcd1234",
                                        "rpm_limit": 60, "confidence_threshold": 0.5})
    assert r.status_code == 200 and r.json()["key_hint"] == "1234" and r.json()["has_key"]
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5.5", "api_key": "", "rpm_limit": 60,
                                        "confidence_threshold": 0.5})
    assert r.json()["model"] == "gpt-5.5" and r.json()["key_hint"] == "1234"


def test_put_unknown_provider_400(auth):
    r = auth.put("/api/settings", json={"provider": "nope", "model": "x", "rpm_limit": 1, "confidence_threshold": 0})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_provider"


def test_test_connection_uses_submitted_then_stored_key(auth, monkeypatch):
    seen = []

    def fake_probe(provider, model, api_key, extractor_model=None, base_url=None, **_):
        seen.append(api_key)
        return ProbeResult(text=Check(True, 10), vision=Check(True, 20))

    monkeypatch.setattr("sms.web.routers.settings.probe", fake_probe)
    r = auth.post("/api/settings/test", json={"provider": "openai", "model": "gpt-5-mini"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_key"
    r = auth.post("/api/settings/test", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-new"})
    assert r.status_code == 200 and r.json()["vision"]["ok"] and seen == ["sk-new"]
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-stored",
                                    "rpm_limit": 60, "confidence_threshold": 0})
    auth.post("/api/settings/test", json={"provider": "openai", "model": "gpt-5-mini"})
    assert seen[-1] == "sk-stored"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/web/test_settings_api.py -q`
Expected: FAIL (404s / import error).

- [ ] **Step 3: Implement**

`src/sms/web/routers/settings.py`:

```python
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from sms.providers.probe import probe
from sms.providers.registry import registry_as_dicts
from sms.providers.settings import Settings, SettingsStore
from sms.web.deps import get_settings_store, require_teacher
from sms.web.errors import ApiError

router = APIRouter(prefix="/api", tags=["settings"], dependencies=[Depends(require_teacher)])


class SettingsBody(BaseModel):
    provider: str
    model: str = Field(min_length=1)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extractor_model: Optional[str] = None
    rpm_limit: int = Field(ge=0, le=10000)
    confidence_threshold: float = Field(ge=0.0, le=1.0)


class TestBody(BaseModel):
    provider: str
    model: str = Field(min_length=1)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extractor_model: Optional[str] = None


@router.get("/providers")
def providers():
    return registry_as_dicts()


@router.get("/settings")
def get_settings(store: SettingsStore = Depends(get_settings_store)):
    return store.load().public_dict()


@router.put("/settings")
def put_settings(body: SettingsBody, store: SettingsStore = Depends(get_settings_store)):
    try:
        saved = store.save(Settings(
            provider=body.provider, model=body.model.strip(), api_key=(body.api_key or "").strip() or None,
            base_url=(body.base_url or "").strip() or None,
            extractor_model=(body.extractor_model or "").strip() or None,
            rpm_limit=body.rpm_limit, confidence_threshold=body.confidence_threshold,
        ))
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))
    return saved.public_dict()


@router.post("/settings/test")
def test_connection(body: TestBody, store: SettingsStore = Depends(get_settings_store)):
    key = (body.api_key or "").strip() or store.load().api_key
    if not key:
        raise ApiError(400, "no_key", "Enter an API key first")
    try:
        result = probe(body.provider, body.model.strip(), key,
                       extractor_model=(body.extractor_model or "").strip() or None,
                       base_url=(body.base_url or "").strip() or None)
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))
    return result.to_dict()
```

In `src/sms/web/app.py` add `settings` to the router import and `app.include_router(settings.router)` after `auth`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/web -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sms/web tests/web/test_settings_api.py
git commit -m "feat: settings, providers and test-connection API

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: Submissions and pages API

**Files:**
- Create: `src/sms/web/services/__init__.py`, `src/sms/web/services/submissions.py`, `src/sms/web/routers/submissions.py`, `src/sms/web/routers/pages.py`
- Modify: `src/sms/web/app.py`
- Test: `tests/web/test_submissions_api.py`

**Interfaces:**
- Consumes: `process_uploads`, `UploadError`, `JobStore`, `Rubric`.
- Produces: `create_submission(db, storage, jobs, *, label, subject, context, rubric_json, files) -> dict`; `list_submissions(db) -> list[dict]`; `get_submission(db, jobs, submission_id) -> dict | None`; `compute_totals(rubric, final_marks, pending_qids, corrections) -> dict(total, total_upper, total_max, per_question_max)`; routes `POST/GET /api/submissions`, `GET /api/submissions/{id}`, `POST /api/submissions/{id}/retry`, `GET /api/pages/{id}`.

Detail shape returned by `GET /api/submissions/{id}`:

```json
{"id": 1, "label": "…", "subject": "math", "context": "…", "status": "needs_you",
 "created_at": "…", "rubric": {"criterion_defs": [...]},
 "pages": [{"id": 1, "page_index": 0, "width": 1000, "height": 1400}],
 "marks": [{"q_id": "q1", "criterion_scores": [2, 1], "total": 3, "max": 4, "confidence": 0.7,
            "evidence": "…", "rationale": "…", "escalated": false, "reason": null,
            "queue_id": null, "teacher_scores": null}],
 "totals": {"total": 3, "total_upper": 3, "total_max": 4},
 "feedback": {...FeedbackReport...} | null,
 "job": {"status": "done", "attempts": 1, "error": null, "started_at": "…", "finished_at": "…"} | null}
```

- [ ] **Step 1: Write the failing tests**

`tests/web/test_submissions_api.py`:

```python
import io
import json

from PIL import Image

from sms.schemas.marking import Rubric, RubricCriterion
from sms.web.services.submissions import compute_totals

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2},
                              {"id": "c2", "description": "answer", "max_score": 3}]}


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def _create(auth, **over):
    data = {"label": "Tan Wei Ling", "subject": "math", "context": "Worksheet 3", "rubric": json.dumps(RUBRIC)}
    data.update(over)
    return auth.post("/api/submissions", data=data, files=[("files", ("p1.png", _png(), "image/png"))])


def test_requires_auth(client):
    assert client.get("/api/submissions").status_code == 401


def test_create_without_key_400(auth):
    r = _create(auth)
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_key"


def _with_key(auth):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x",
                                    "rpm_limit": 60, "confidence_threshold": 0})
    return auth


def test_create_returns_202_and_queues_job(auth):
    r = _create(_with_key(auth))
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and len(body["pages"]) == 1
    lst = auth.get("/api/submissions").json()
    assert lst[0]["id"] == body["id"] and lst[0]["page_count"] == 1 and lst[0]["status"] == "queued"
    detail = auth.get(f"/api/submissions/{body['id']}").json()
    assert detail["job"]["status"] == "queued" and detail["marks"] == [] and detail["feedback"] is None


def test_create_bad_rubric_400(auth):
    r = _create(_with_key(auth), rubric="{}")
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_rubric"


def test_create_bad_file_names_it(auth):
    auth = _with_key(auth)
    r = auth.post("/api/submissions", data={"label": "x", "subject": "math", "context": "", "rubric": json.dumps(RUBRIC)},
                  files=[("files", ("notes.txt", b"hi", "text/plain"))])
    assert r.status_code == 400 and "notes.txt" in r.json()["error"]["message"]


def test_page_route_authenticated_and_serves_jpeg(auth, client):
    body = _create(_with_key(auth)).json()
    pid = body["pages"][0]["id"]
    r = auth.get(f"/api/pages/{pid}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    client.cookies.clear()
    assert client.get(f"/api/pages/{pid}").status_code == 401


def test_retry_only_when_failed(auth, app):
    body = _create(_with_key(auth)).json()
    assert auth.post(f"/api/submissions/{body['id']}/retry").status_code == 409
    app.state.db.execute("UPDATE jobs SET status = 'failed'"); app.state.db.execute("UPDATE submissions SET status = 'failed'")
    assert auth.post(f"/api/submissions/{body['id']}/retry").status_code == 202
    assert auth.get(f"/api/submissions/{body['id']}").json()["status"] == "queued"


def test_detail_after_run_includes_marks_escalations_feedback(auth, app):
    body = _create(_with_key(auth)).json()
    sid = body["id"]
    db = app.state.db
    final = {"marks": [{"q_id": "q1", "criterion_scores": [2, 3], "total": 5, "confidence": 0.9, "rationale": "r", "evidence": "e"},
                       {"q_id": "q2", "criterion_scores": [1, 1], "total": 2, "confidence": 0.3, "rationale": "r2", "evidence": "e2"}]}
    feedback = {"summary": "s", "strengths": ["a"], "per_question_comments": [], "improvement_plan": [], "next_steps": []}
    db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, marks_json, final_marks_json, feedback_json, "
               "reviewed_json, submission_id, final_status) VALUES ('r1', 'complete', 'math', ?, ?, ?, ?, ?, ?, 'escalated')",
               (json.dumps(RUBRIC), json.dumps(final), json.dumps(final), json.dumps(feedback),
                json.dumps({"verdicts": [{"q_id": "q2", "verdict": "ESCALATE", "reviewer_note": "unsure"}], "final_marks": [], "disagreement_flags": []}), sid))
    db.execute("INSERT INTO teacher_queue (run_id, q_id, reason, status, submission_id) VALUES ('r1', 'q2', 'low marker confidence', 'pending', ?)", (sid,))
    db.execute("UPDATE submissions SET status = 'needs_you', run_id = 'r1' WHERE id = ?", (sid,))
    d = auth.get(f"/api/submissions/{sid}").json()
    assert d["status"] == "needs_you" and d["feedback"]["summary"] == "s"
    q2 = next(m for m in d["marks"] if m["q_id"] == "q2")
    assert q2["escalated"] and q2["reason"] == "low marker confidence" and q2["queue_id"] and q2["max"] == 5
    assert d["totals"] == {"total": 7, "total_upper": 10, "total_max": 10}
    lst = auth.get("/api/submissions").json()[0]
    assert lst["total"] == 7 and lst["total_upper"] == 10 and lst["needs_you_qids"] == ["q2"]


def test_compute_totals_pure():
    rubric = Rubric(criterion_defs=[RubricCriterion(id="c1", description="d", max_score=2),
                                    RubricCriterion(id="c2", description="d", max_score=3)])
    final = [{"q_id": "q1", "total": 4}, {"q_id": "q2", "total": 1}]
    t = compute_totals(rubric, final, pending_qids={"q2"}, corrections={})
    assert t == {"total": 5, "total_upper": 9, "total_max": 10}
    t = compute_totals(rubric, final, pending_qids=set(), corrections={"q2": [2, 2]})
    assert t == {"total": 8, "total_upper": 8, "total_max": 10}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/web/test_submissions_api.py -q`
Expected: FAIL with import error.

- [ ] **Step 3: Implement the service**

`src/sms/web/services/__init__.py`: empty.

`src/sms/web/services/submissions.py`:

```python
import json
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from pydantic import ValidationError

from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.schemas.marking import Rubric
from sms.storage import PageStorage, UploadError, process_uploads
from sms.web.errors import ApiError
from sms.worker.jobs import JobStore


def parse_rubric(rubric_json: str) -> Rubric:
    try:
        rubric = Rubric.model_validate_json(rubric_json)
    except ValidationError as e:
        raise ApiError(400, "bad_rubric", f"Rubric is not valid: {e.errors()[0]['msg']}")
    if not rubric.criterion_defs:
        raise ApiError(400, "bad_rubric", "Add at least one criterion")
    return rubric


def create_submission(db: Database, storage: PageStorage, jobs: JobStore, *, label: str, subject: str,
                      context: str, rubric_json: str, files: List[Tuple[str, bytes]]) -> Dict[str, Any]:
    label = label.strip()
    if not label:
        raise ApiError(400, "bad_label", "Give the script a label")
    try:
        subject = SubjectRouter().resolve(subject)
    except KeyError:
        raise ApiError(400, "bad_subject", "Subject must be math, language or science")
    rubric = parse_rubric(rubric_json)
    if not files:
        raise ApiError(400, "no_files", "Add at least one page")
    try:
        pages = process_uploads(files, storage)
    except UploadError as e:
        raise ApiError(400, "bad_upload", str(e))
    with db.transaction() as tx:
        sid = tx.insert(
            "INSERT INTO submissions (label, subject, context, rubric_json, status) "
            "VALUES (:label, :subject, :context, :rubric, 'uploaded') RETURNING id",
            {"label": label, "subject": subject, "context": context.strip(), "rubric": rubric.model_dump_json()},
        )
        page_rows = []
        for i, p in enumerate(pages):
            pid = tx.insert(
                "INSERT INTO pages (submission_id, page_index, sha256, storage_path, source_filename, width, height) "
                "VALUES (:s, :i, :h, :p, :f, :w, :ht) RETURNING id",
                {"s": sid, "i": i, "h": p.sha256, "p": p.storage_path, "f": p.source_filename, "w": p.width, "ht": p.height},
            )
            page_rows.append({"id": pid, "page_index": i, "width": p.width, "height": p.height})
    jobs.enqueue("mark", sid)
    return {"id": sid, "status": "queued", "pages": page_rows}


def compute_totals(rubric: Rubric, final_marks: Iterable[dict], pending_qids: Set[str],
                   corrections: Dict[str, List[int]]) -> Dict[str, int]:
    per_q_max = sum(c.max_score for c in rubric.criterion_defs)
    total = upper = 0
    n = 0
    for m in final_marks:
        n += 1
        q = m["q_id"]
        if q in corrections:
            t = sum(corrections[q]); total += t; upper += t
        elif q in pending_qids:
            total += int(m["total"]); upper += per_q_max
        else:
            total += int(m["total"]); upper += int(m["total"])
    return {"total": total, "total_upper": upper, "total_max": per_q_max * n}


def _run_row(db: Database, run_id: Optional[str]) -> Optional[dict]:
    if not run_id:
        return None
    rows = db.query("SELECT * FROM marking_runs WHERE run_id = :r ORDER BY id DESC LIMIT 1", {"r": run_id})
    return rows[0] if rows else None


def _pending(db: Database, submission_id: int) -> Dict[str, dict]:
    rows = db.query("SELECT id, q_id, reason FROM teacher_queue WHERE submission_id = :s AND status = 'pending'",
                    {"s": submission_id})
    return {r["q_id"]: r for r in rows}


def _corrections(db: Database, run_id: Optional[str]) -> Dict[str, List[int]]:
    if not run_id:
        return {}
    rows = db.query("SELECT q_id, criterion_scores_json, teacher_mark FROM teacher_corrections WHERE run_id = :r ORDER BY id",
                    {"r": run_id})
    out: Dict[str, List[int]] = {}
    for r in rows:
        if r["criterion_scores_json"]:
            out[r["q_id"]] = json.loads(r["criterion_scores_json"])
        elif r["teacher_mark"] is not None:
            out[r["q_id"]] = [int(r["teacher_mark"])]
    return out


def list_submissions(db: Database) -> List[Dict[str, Any]]:
    subs = db.query("SELECT s.*, (SELECT COUNT(*) FROM pages p WHERE p.submission_id = s.id) AS page_count "
                    "FROM submissions s ORDER BY s.id DESC")
    out = []
    for s in subs:
        rubric = Rubric.model_validate_json(s["rubric_json"])
        run = _run_row(db, s["run_id"])
        pending = _pending(db, s["id"])
        final = json.loads(run["final_marks_json"])["marks"] if run and run["final_marks_json"] else []
        totals = compute_totals(rubric, final, set(pending), _corrections(db, s["run_id"])) if final else None
        out.append({
            "id": s["id"], "label": s["label"], "subject": s["subject"], "page_count": s["page_count"],
            "status": s["status"], "created_at": str(s["created_at"]),
            "total": totals["total"] if totals else None,
            "total_upper": totals["total_upper"] if totals else None,
            "total_max": totals["total_max"] if totals else None,
            "needs_you_qids": sorted(pending),
        })
    return out


def get_submission(db: Database, jobs: JobStore, submission_id: int) -> Optional[Dict[str, Any]]:
    rows = db.query("SELECT * FROM submissions WHERE id = :id", {"id": submission_id})
    if not rows:
        return None
    s = rows[0]
    rubric = Rubric.model_validate_json(s["rubric_json"])
    pages = db.query("SELECT id, page_index, width, height FROM pages WHERE submission_id = :id ORDER BY page_index",
                     {"id": submission_id})
    run = _run_row(db, s["run_id"])
    pending = _pending(db, submission_id)
    corrections = _corrections(db, s["run_id"])
    per_q_max = sum(c.max_score for c in rubric.criterion_defs)
    marks: List[dict] = []
    feedback = None
    if run:
        final = json.loads(run["final_marks_json"])["marks"] if run["final_marks_json"] else []
        for m in final:
            q = m["q_id"]
            marks.append({
                "q_id": q, "criterion_scores": m["criterion_scores"], "total": m["total"], "max": per_q_max,
                "confidence": m.get("confidence"), "evidence": m.get("evidence", ""), "rationale": m.get("rationale", ""),
                "escalated": q in pending, "reason": pending[q]["reason"] if q in pending else None,
                "queue_id": pending[q]["id"] if q in pending else None,
                "teacher_scores": corrections.get(q),
            })
        feedback = json.loads(run["feedback_json"]) if run["feedback_json"] else None
    job = jobs.job_for_submission(submission_id)
    return {
        "id": s["id"], "label": s["label"], "subject": s["subject"], "context": s["context"], "status": s["status"],
        "created_at": str(s["created_at"]), "rubric": rubric.model_dump(), "pages": pages, "marks": marks,
        "totals": compute_totals(rubric, marks, set(pending), corrections) if marks else None,
        "feedback": feedback,
        "job": {"status": job["status"], "attempts": job["attempts"], "error": job["error"],
                "started_at": str(job["started_at"]) if job["started_at"] else None,
                "finished_at": str(job["finished_at"]) if job["finished_at"] else None} if job else None,
    }
```

- [ ] **Step 4: Implement the routers**

`src/sms/web/routers/submissions.py`:

```python
from typing import List

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from sms.web.deps import get_db, get_jobs, get_settings_store, get_storage, require_teacher
from sms.web.errors import ApiError
from sms.web.services.submissions import create_submission, get_submission, list_submissions

router = APIRouter(prefix="/api/submissions", tags=["submissions"], dependencies=[Depends(require_teacher)])


@router.post("", status_code=202)
async def create(label: str = Form(...), subject: str = Form("math"), context: str = Form(""),
                 rubric: str = Form(...), files: List[UploadFile] = File(...),
                 db=Depends(get_db), storage=Depends(get_storage), jobs=Depends(get_jobs),
                 settings=Depends(get_settings_store)):
    if not settings.load().has_key:
        raise ApiError(400, "no_key", "Add an API key under Settings before marking")
    payload = [(f.filename or "upload", await f.read()) for f in files]
    return create_submission(db, storage, jobs, label=label, subject=subject, context=context,
                             rubric_json=rubric, files=payload)


@router.get("")
def index(db=Depends(get_db)):
    return list_submissions(db)


@router.get("/{submission_id}")
def detail(submission_id: int, db=Depends(get_db), jobs=Depends(get_jobs)):
    sub = get_submission(db, jobs, submission_id)
    if sub is None:
        raise ApiError(404, "not_found", "No such submission")
    return sub


@router.post("/{submission_id}/retry", status_code=202)
def retry(submission_id: int, db=Depends(get_db), jobs=Depends(get_jobs)):
    job = jobs.job_for_submission(submission_id)
    if job is None:
        raise ApiError(404, "not_found", "No such submission")
    if job["status"] != "failed":
        raise ApiError(409, "not_failed", "Only failed submissions can be retried")
    jobs.enqueue("mark", submission_id)
    return JSONResponse(status_code=202, content={"id": submission_id, "status": "queued"})
```

`src/sms/web/routers/pages.py`:

```python
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from sms.web.deps import get_db, get_storage, require_teacher
from sms.web.errors import ApiError

router = APIRouter(prefix="/api/pages", tags=["pages"], dependencies=[Depends(require_teacher)])


@router.get("/{page_id}")
def page(page_id: int, db=Depends(get_db), storage=Depends(get_storage)):
    rows = db.query("SELECT storage_path FROM pages WHERE id = :id", {"id": page_id})
    if not rows:
        raise ApiError(404, "not_found", "No such page")
    return FileResponse(storage.abs(rows[0]["storage_path"]), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})
```

In `src/sms/web/app.py`: import `pages, submissions` and include both routers after `settings`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/web -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sms/web tests/web/test_submissions_api.py
git commit -m "feat: submissions and pages API with upload processing and job enqueue

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: Review queue and learning API

**Files:**
- Create: `src/sms/web/services/queue.py`, `src/sms/web/routers/queue.py`, `src/sms/web/routers/learning.py`
- Modify: `src/sms/web/app.py`
- Test: `tests/web/test_queue_api.py`

**Interfaces:**
- Produces: `list_queue(db) -> list[dict]`, `resolve_queue_item(db, item_id, criterion_scores, reason) -> dict` (raises `ApiError(404)`); routes `GET /api/queue`, `POST /api/queue/{id}/resolve`, `GET /api/notes`, `POST /api/notes/{id}/approve`, `GET /api/exemplars`, `POST /api/exemplars/{id}/approve`, `GET /api/stats`.

Queue item shape:

```json
{"id": 4, "submission_id": 1, "submission_label": "Tan Wei Ling", "q_id": "q2", "reason": "low marker confidence",
 "transcription": "…", "workings": "…", "proposed_criterion_scores": [1, 1], "proposed_total": 2,
 "evidence": "…", "rationale": "…", "reviewer_note": "…", "criterion_defs": [...], "page_ids": [1, 2], "created_at": "…"}
```

- [ ] **Step 1: Write the failing tests**

`tests/web/test_queue_api.py`:

```python
import json

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2},
                              {"id": "c2", "description": "answer", "max_score": 3}]}


def _seed(app):
    db = app.state.db
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status, run_id) "
                    "VALUES ('Tan', 'math', '', :r, 'needs_you', 'r1') RETURNING id", {"r": json.dumps(RUBRIC)})
    db.execute("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height) VALUES (?, 0, 'h', 'pages/h.jpg', 1, 1)", (sid,))
    marks = {"marks": [{"q_id": "q2", "criterion_scores": [1, 1], "total": 2, "confidence": 0.3, "rationale": "hmm", "evidence": "x=2"}]}
    extracted = {"questions": [{"q_id": "q2", "transcribed_answer": "x = 2", "workings": "2x=4", "confidence": 0.5, "needs_human_transcription": False}]}
    reviewed = {"verdicts": [{"q_id": "q2", "verdict": "ESCALATE", "reviewer_note": "method unclear"}], "final_marks": [], "disagreement_flags": []}
    db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, marks_json, final_marks_json, reviewed_json, submission_id, final_status) "
               "VALUES ('r1', 'complete', 'math', ?, ?, ?, ?, ?, ?, 'escalated')",
               (json.dumps(RUBRIC), json.dumps(extracted), json.dumps(marks), json.dumps(marks), json.dumps(reviewed), sid))
    qid = db.insert("INSERT INTO teacher_queue (run_id, q_id, reason, status, submission_id) VALUES ('r1', 'q2', 'reviewer escalated', 'pending', :s) RETURNING id", {"s": sid})
    return sid, qid


def test_queue_requires_auth(client):
    assert client.get("/api/queue").status_code == 401


def test_queue_lists_joined_item(auth, app):
    sid, qid = _seed(app)
    items = auth.get("/api/queue").json()
    assert len(items) == 1
    it = items[0]
    assert it["id"] == qid and it["submission_label"] == "Tan" and it["transcription"] == "x = 2"
    assert it["proposed_criterion_scores"] == [1, 1] and it["reviewer_note"] == "method unclear"
    assert it["criterion_defs"][0]["id"] == "c1" and it["page_ids"] and it["reason"] == "reviewer escalated"


def test_resolve_records_correction_and_flips_submission(auth, app):
    sid, qid = _seed(app)
    r = auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [2, 2], "reason": "method fine"})
    assert r.status_code == 200 and r.json()["submission_status"] == "done"
    db = app.state.db
    c = db.query("SELECT agent_mark, teacher_mark, criterion_scores_json, reason FROM teacher_corrections")[0]
    assert (c["agent_mark"], c["teacher_mark"], c["reason"]) == (2, 4, "method fine")
    assert json.loads(c["criterion_scores_json"]) == [2, 2]
    assert db.query("SELECT status FROM teacher_queue")[0]["status"] == "resolved"
    assert auth.get("/api/queue").json() == []
    d = auth.get(f"/api/submissions/{sid}").json()
    assert d["marks"][0]["teacher_scores"] == [2, 2] and d["totals"]["total"] == 4


def test_resolve_validates_scores(auth, app):
    _, qid = _seed(app)
    assert auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [9, 0], "reason": ""}).status_code == 400
    assert auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [1], "reason": ""}).status_code == 400


def test_resolve_twice_404(auth, app):
    _, qid = _seed(app)
    auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [1, 1], "reason": ""})
    assert auth.post(f"/api/queue/{qid}/resolve", json={"criterion_scores": [1, 1], "reason": ""}).status_code == 404


def test_learning_endpoints(auth, app):
    db = app.state.db
    nid = db.insert("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'units matter', 'draft') RETURNING id")
    eid = db.insert("INSERT INTO exemplar_cases (subject, topic, q_id, answer_text, awarded, max_score, why_it_matters, status) "
                    "VALUES ('math', 'algebra', 'q1', 'x=3', 2, 2, 'clean', 'draft') RETURNING id")
    assert auth.get("/api/notes").json()[0]["status"] == "draft"
    assert auth.post(f"/api/notes/{nid}/approve").json()["status"] == "active"
    assert auth.post(f"/api/exemplars/{eid}/approve").json()["status"] == "active"
    assert auth.get("/api/exemplars").json()[0]["status"] == "active"
    stats = auth.get("/api/stats").json()
    assert set(stats) == {"extractor", "marker", "reviewer", "feedback", "reflection"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/web/test_queue_api.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement the queue service**

`src/sms/web/services/queue.py`:

```python
import json
from typing import Any, Dict, List

from sms.memory.db import Database
from sms.schemas.marking import Rubric
from sms.web.errors import ApiError


def list_queue(db: Database) -> List[Dict[str, Any]]:
    rows = db.query(
        "SELECT q.id, q.submission_id, q.q_id, q.reason, q.created_at, q.run_id, s.label AS submission_label, "
        "mr.rubric_json, mr.extracted_json, mr.marks_json, mr.reviewed_json "
        "FROM teacher_queue q JOIN marking_runs mr ON mr.run_id = q.run_id "
        "LEFT JOIN submissions s ON s.id = q.submission_id "
        "WHERE q.status = 'pending' ORDER BY q.id"
    )
    out = []
    for r in rows:
        q = r["q_id"]
        extracted = json.loads(r["extracted_json"] or '{"questions": []}')
        marks = json.loads(r["marks_json"] or '{"marks": []}')
        reviewed = json.loads(r["reviewed_json"] or '{"verdicts": []}')
        eq = next((x for x in extracted.get("questions", []) if x["q_id"] == q), {})
        mq = next((x for x in marks.get("marks", []) if x["q_id"] == q), {})
        rv = next((x for x in reviewed.get("verdicts", []) if x["q_id"] == q), {})
        page_ids = [p["id"] for p in db.query(
            "SELECT id FROM pages WHERE submission_id = :s ORDER BY page_index", {"s": r["submission_id"]})] \
            if r["submission_id"] else []
        out.append({
            "id": r["id"], "submission_id": r["submission_id"], "submission_label": r["submission_label"] or r["run_id"],
            "q_id": q, "reason": r["reason"], "created_at": str(r["created_at"]),
            "transcription": eq.get("transcribed_answer", ""), "workings": eq.get("workings", ""),
            "proposed_criterion_scores": mq.get("criterion_scores", []), "proposed_total": mq.get("total"),
            "evidence": mq.get("evidence", ""), "rationale": mq.get("rationale", ""),
            "reviewer_note": rv.get("reviewer_note", ""),
            "criterion_defs": Rubric.model_validate_json(r["rubric_json"]).model_dump()["criterion_defs"],
            "page_ids": page_ids,
        })
    return out


def resolve_queue_item(db: Database, item_id: int, criterion_scores: List[int], reason: str) -> Dict[str, Any]:
    rows = db.query("SELECT q.run_id, q.q_id, q.submission_id, mr.rubric_json, mr.marks_json FROM teacher_queue q "
                    "JOIN marking_runs mr ON mr.run_id = q.run_id WHERE q.id = :id AND q.status = 'pending'",
                    {"id": item_id})
    if not rows:
        raise ApiError(404, "not_found", "That question is not waiting for you")
    r = rows[0]
    rubric = Rubric.model_validate_json(r["rubric_json"])
    if len(criterion_scores) != len(rubric.criterion_defs):
        raise ApiError(400, "bad_scores", f"Give one mark per criterion ({len(rubric.criterion_defs)})")
    for score, c in zip(criterion_scores, rubric.criterion_defs):
        if score < 0 or score > c.max_score:
            raise ApiError(400, "bad_scores", f"{c.description}: mark must be between 0 and {c.max_score}")
    marks = json.loads(r["marks_json"] or '{"marks": []}')
    agent_mark = next((m["total"] for m in marks.get("marks", []) if m["q_id"] == r["q_id"]), None)
    with db.transaction() as tx:
        tx.execute("UPDATE teacher_queue SET status = 'resolved' WHERE id = :id", {"id": item_id})
        tx.execute(
            "INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason, criterion_scores_json) "
            "VALUES (:run_id, :q_id, :agent, :teacher, :reason, :scores)",
            {"run_id": r["run_id"], "q_id": r["q_id"], "agent": agent_mark, "teacher": sum(criterion_scores),
             "reason": reason, "scores": json.dumps(criterion_scores)},
        )
        status = None
        if r["submission_id"] is not None:
            remaining = tx.query("SELECT COUNT(*) AS c FROM teacher_queue WHERE submission_id = :s AND status = 'pending'",
                                 {"s": r["submission_id"]})[0]["c"]
            status = "needs_you" if remaining else "done"
            tx.execute("UPDATE submissions SET status = :st, updated_at = CURRENT_TIMESTAMP WHERE id = :s",
                       {"st": status, "s": r["submission_id"]})
    return {"id": item_id, "submission_id": r["submission_id"], "submission_status": status}
```

- [ ] **Step 4: Implement the routers**

`src/sms/web/routers/queue.py`:

```python
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sms.web.deps import get_db, require_teacher
from sms.web.services.queue import list_queue, resolve_queue_item

router = APIRouter(prefix="/api/queue", tags=["queue"], dependencies=[Depends(require_teacher)])


class ResolveBody(BaseModel):
    criterion_scores: List[int]
    reason: str = ""


@router.get("")
def index(db=Depends(get_db)):
    return list_queue(db)


@router.post("/{item_id}/resolve")
def resolve(item_id: int, body: ResolveBody, db=Depends(get_db)):
    return resolve_queue_item(db, item_id, body.criterion_scores, body.reason.strip())
```

`src/sms/web/routers/learning.py`:

```python
from fastapi import APIRouter, Depends

from sms.learning.reflection_job import activate_exemplar, activate_note
from sms.memory.metrics import MetricsSummary
from sms.web.deps import get_db, require_teacher
from sms.web.errors import ApiError

router = APIRouter(prefix="/api", tags=["learning"], dependencies=[Depends(require_teacher)])


@router.get("/notes")
def notes(db=Depends(get_db)):
    return db.query("SELECT id, subject, note, status, created_at FROM rubric_notes ORDER BY id DESC")


@router.post("/notes/{note_id}/approve")
def approve_note(note_id: int, db=Depends(get_db)):
    if not db.query("SELECT id FROM rubric_notes WHERE id = :id", {"id": note_id}):
        raise ApiError(404, "not_found", "No such note")
    activate_note(db, note_id)
    return db.query("SELECT id, subject, note, status FROM rubric_notes WHERE id = :id", {"id": note_id})[0]


@router.get("/exemplars")
def exemplars(db=Depends(get_db)):
    return db.query("SELECT id, subject, topic, q_id, answer_text, awarded, max_score, why_it_matters, status, created_at "
                    "FROM exemplar_cases ORDER BY id DESC")


@router.post("/exemplars/{exemplar_id}/approve")
def approve_exemplar(exemplar_id: int, db=Depends(get_db)):
    if not db.query("SELECT id FROM exemplar_cases WHERE id = :id", {"id": exemplar_id}):
        raise ApiError(404, "not_found", "No such exemplar")
    activate_exemplar(db, exemplar_id)
    return db.query("SELECT id, subject, topic, status FROM exemplar_cases WHERE id = :id", {"id": exemplar_id})[0]


@router.get("/stats")
def stats(db=Depends(get_db)):
    ms = MetricsSummary(db)
    return {role: ms.summarize(agent_role=role) for role in ("extractor", "marker", "reviewer", "feedback", "reflection")}
```

Datetime values from SQLAlchemy may be `datetime` objects on Postgres; FastAPI serialises them. In `app.py` include `queue.router` and `learning.router`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/sms/web tests/web/test_queue_api.py
git commit -m "feat: review queue resolve API and learning endpoints

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 13: CLI — `serve`, `worker`, provider-based client

**Files:**
- Modify: `src/sms/cli.py`
- Test: `tests/integration/test_cli.py` (append)

**Interfaces:**
- Produces: `sms serve [--host 0.0.0.0] [--port 8000]` (runs migrations via `Database`, starts uvicorn with the embedded worker); `sms worker` (standalone worker loop); `sms mark … [--provider ID] [--api-key KEY]` uses `build_client` (falls back to env `LLM_API_KEY`, then `OPENAI_API_KEY` for provider `openai`); every command's `--db` accepts a path **or** a URL.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_cli.py`:

```python
def test_parser_has_serve_and_worker():
    from sms.cli import build_parser
    p = build_parser()
    args = p.parse_args(["serve", "--port", "9000"])
    assert args.command == "serve" and args.port == 9000
    assert p.parse_args(["worker"]).command == "worker"


def test_mark_parser_accepts_provider(tmp_path):
    from sms.cli import build_parser
    args = build_parser().parse_args(["mark", "x.png", "--rubric", "r.json", "--provider", "anthropic", "--api-key", "k"])
    assert args.provider == "anthropic" and args.api_key == "k"


def test_db_arg_accepts_url(tmp_path):
    from sms.cli import _open_db
    db = _open_db(f"sqlite:///{tmp_path / 'u.db'}")
    assert db.is_sqlite
    db2 = _open_db(str(tmp_path / "p.db"))
    assert db2.is_sqlite
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_cli.py -q`
Expected: FAIL (`unrecognized arguments: serve`, no `_open_db`).

- [ ] **Step 3: Implement**

In `src/sms/cli.py`:

Replace `_client()` and add `_open_db`:

```python
from sms.providers.client import build_client
from sms.providers.registry import get_provider


def _open_db(db_arg: str) -> Database:
    if "://" in db_arg:
        return Database(url=db_arg)
    return Database(path=db_arg)


def _provider_id(args) -> str:
    return getattr(args, "provider", None) or os.environ.get("LLM_PROVIDER") or "openai"


def _client(args):
    key = getattr(args, "api_key", None) or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "missing"
    return build_client(_provider_id(args), key)


def _api_params(args):
    return get_provider(_provider_id(args)).api_params
```

(import `get_provider` from `sms.providers.registry`.) Replace every `Database(path=args.db)` with `_open_db(args.db)` and every `_client()` with `_client(args)`, and pass `model_api_parameters=_api_params(args)` to every `build_*` call in `_mark` and `_reflect`.

Add the two commands:

```python
def _serve(args) -> int:
    import uvicorn
    from sms.web.app import app_from_env
    os.environ.setdefault("SMS_EMBEDDED_WORKER", "1")
    uvicorn.run(app_from_env(), host=args.host, port=args.port, log_level="info")
    return 0


def _worker(args) -> int:
    import threading
    from sms.providers.crypto import KeyCipher
    from sms.providers.settings import SettingsStore
    from sms.storage import PageStorage
    from sms.worker.worker import Worker
    from sms.web.config import AppConfig
    cfg = AppConfig.from_env()
    db = Database(url=cfg.database_url)
    store = SettingsStore(db, KeyCipher(cfg.secret_key))
    store.ensure_seeded(cfg.env)
    Worker(db, PageStorage(cfg.storage_dir), store).run_forever(threading.Event())
    return 0
```

In `build_parser()` add `--provider` and `--api-key` to `p_mark` and `p_reflect`:

```python
    p_mark.add_argument("--provider", default=None, help="tokenrouter | openrouter | openai | anthropic | moonshot | qwen")
    p_mark.add_argument("--api-key", default=None)
```

(same two lines for `p_reflect`), and:

```python
    p_serve = sub.add_parser("serve", help="Run the web app (API + SPA + embedded worker)")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p_serve.set_defaults(func=_serve)

    p_worker = sub.add_parser("worker", help="Run a standalone marking worker")
    p_worker.set_defaults(func=_worker)
```

- [ ] **Step 4: Run the suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 5: Smoke-run the server locally (API only, no SPA yet)**

```bash
SECRET_KEY=dev TEACHER_PASSWORD=dev DATABASE_URL=sqlite:///dev.db STORAGE_DIR=./data uv run sms serve --port 8010 &
sleep 2; curl -s localhost:8010/api/health; kill %1
```

Expected: `{"db":"ok","worker_last_seen":"…"}`.

- [ ] **Step 6: Commit**

```bash
git add src/sms/cli.py tests/integration/test_cli.py
git commit -m "feat: sms serve/worker commands and provider-aware CLI client

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 14: Frontend scaffold — Vite, tokens, API client, auth gate, nav, shared components

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`, `web/vitest.setup.ts`, `web/.gitignore`
- Create: `web/src/main.tsx`, `web/src/App.tsx`, `web/src/styles/tokens.css`, `web/src/styles/app.css`
- Create: `web/src/api/client.ts`, `web/src/api/types.ts`, `web/src/lib/format.ts`, `web/src/lib/marks.ts`, `web/src/lib/rubric.ts`
- Create: `web/src/components/{Nav,Button,StatusPill,Notice,EmptyState,MarkDisplay,CriteriaTable,PageCard,PagePager,DropZone,Dialog}.tsx`
- Create: `web/src/pages/SignIn.tsx` (the other pages are stubs in this task and filled in Tasks 15–18)
- Test: `web/src/lib/__tests__/rubric.test.ts`, `web/src/lib/__tests__/marks.test.ts`, `web/src/components/__tests__/StatusPill.test.tsx`, `web/src/components/__tests__/MarkDisplay.test.tsx`

**Interfaces:**
- Produces: `api.get/post/put/postForm<T>(path, body?)` throwing `ApiError {status, code, message}`; types in `types.ts` mirroring the backend JSON; `rubricToJson(rows) / jsonToRubric(json)`; `totalLabel(t)`; `fmtDate(iso)`; components listed above with the props given below.

- [ ] **Step 1: Scaffold**

```bash
cd web && npm init -y >/dev/null
npm install react@18 react-dom@18 react-router-dom@6 lucide-react
npm install -D typescript vite @vitejs/plugin-react @types/react @types/react-dom vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

`web/package.json` — set these fields (keep the generated deps):

```json
{
  "name": "smart-marking-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  }
}
```

`web/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  build: { outDir: "dist", emptyOutDir: true },
  test: { environment: "jsdom", setupFiles: ["./vitest.setup.ts"], globals: true },
});
```

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022", "lib": ["ES2022", "DOM", "DOM.Iterable"], "module": "ESNext",
    "moduleResolution": "Bundler", "jsx": "react-jsx", "strict": true, "skipLibCheck": true,
    "noEmit": true, "resolveJsonModule": true, "isolatedModules": true, "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vitest.setup.ts", "vite.config.ts"]
}
```

`web/vitest.setup.ts`: `import "@testing-library/jest-dom/vitest";`

`web/.gitignore`: `node_modules\ndist\n`

`web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Smart Marking</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Copy the design tokens verbatim and add product CSS**

```bash
cp "docs/design-handoff/_ds/modernist-74c12b6c-c14e-4137-a9d0-95bc689f713c/styles.css" web/src/styles/tokens.css
```

`web/src/styles/app.css` (product-specific classes; values from `docs/design-handoff/README.md` "Colour roles" and "Shared chrome"):

```css
:root {
  --ink: var(--color-text);
  --muted: #5c5958;
  --tertiary: #7d7979;
  --amber-fill: oklch(0.96 0.05 85);
  --amber-border: oklch(0.80 0.12 80);
  --amber-text: oklch(0.40 0.09 70);
  --amber-stripe: oklch(0.72 0.15 75);
  --gutter: 48px;
}
@media (max-width: 1100px) { :root { --gutter: 32px; } }
@media (max-width: 640px) { :root { --gutter: 16px; } }

.page { padding: 32px var(--gutter) 64px; }
.page-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; flex-wrap: wrap; margin-bottom: 24px; }
.page-header h1 { font-size: 34px; margin: 0; }
.breadcrumb { font-size: 13px; display: inline-block; margin-bottom: 8px; }
.meta { color: var(--muted); font-size: 15px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.rule-2 { border: 0; border-top: 2px solid var(--color-divider); margin: 0; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.tabular { font-variant-numeric: tabular-nums; }
.muted { color: var(--muted); }
.tertiary { color: var(--tertiary); }
.label-caps { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: color-mix(in srgb, var(--ink) 60%, transparent); font-weight: 600; }

/* nav — README "Shared chrome" */
.nav { display: flex; align-items: center; justify-content: space-between; padding: 14px var(--gutter); border-bottom: 2px solid var(--color-divider); }
.nav-brand { font-family: var(--font-heading); font-weight: 800; font-size: 18px; color: var(--ink); text-decoration: none; }
.nav-links { display: flex; gap: 24px; align-items: center; }
.nav-links a { color: var(--ink); text-decoration: none; font-size: 14px; display: inline-flex; gap: 6px; align-items: center; min-height: 44px; }
.nav-links a[aria-current="page"] { color: var(--color-accent); }

/* buttons: min-height 44, labels flush left in wide buttons */
.btn { min-height: 44px; padding: 0 16px; font-size: 14px; }
.btn-lg { min-height: 48px; font-size: 15px; }
.btn-sm { min-height: 40px; }
.btn-wide { justify-content: flex-start; flex: 1; }
.btn-primary:disabled { opacity: 0.45; }
.key { font-size: 11px; font-weight: 600; border: 1px solid var(--color-divider); padding: 3px 6px; min-width: 22px; text-align: center; margin-left: auto; }
.btn-primary .key { color: #fff; border-color: rgba(255,255,255,0.5); }

/* status pill — inline-flex, 12px, 3px 10px, leading 8×8 square swatch */
.pill { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; padding: 3px 10px; border: 1px solid transparent; white-space: nowrap; }
.pill::before { content: ""; width: 8px; height: 8px; background: currentColor; flex: none; }
.pill-neutral { background: var(--color-neutral-200); color: var(--ink); }
.pill-ink { background: var(--ink); color: var(--color-bg); }
.pill-outline { border-color: var(--color-divider); color: var(--ink); }
.pill-open { border-color: var(--color-accent); color: var(--color-accent-700); }
.pill-amber { background: var(--amber-fill); border-color: var(--amber-border); color: var(--amber-text); }
.pill-amber::before { display: none; }
.pill-failed { border-color: var(--color-accent-700); color: var(--color-accent-700); }

/* amber notice */
.notice { display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; background: var(--amber-fill); border: 1px solid var(--amber-border); color: var(--amber-text); font-size: 14px; }
.notice-ok { background: var(--color-neutral-100); border-color: var(--color-divider); color: var(--ink); }
.notice-error { background: var(--color-accent-100); border-color: var(--color-accent-700); color: var(--color-accent-700); }

/* table — README: th 11px uppercase 0.08em 60% ink, 2px bottom rule; td 8px, 1px rules; hover 4% ink */
.table { width: 100%; border-collapse: collapse; font-size: 14px; }
.table th { text-align: left; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: color-mix(in srgb, var(--ink) 60%, transparent); padding: 8px; border-bottom: 2px solid var(--color-divider); font-weight: 600; }
.table td { padding: 8px; border-bottom: 1px solid var(--color-divider); vertical-align: middle; }
.table.tall td { padding: 16px 8px; }
.table tbody tr:hover { background: color-mix(in srgb, var(--ink) 4%, transparent); }
.table td.num, .table th.num { text-align: right; font-variant-numeric: tabular-nums; }
.table tr.row-link { cursor: pointer; }

/* forms */
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 20px; }
.field > label { font-size: 13px; font-weight: 600; }
.input, select.input, textarea.input { min-height: 44px; font-size: 15px; padding: 8px 12px; background: var(--color-surface); border: 1px solid var(--color-divider); color: var(--ink); font-family: var(--font-body); width: 100%; }
textarea.input { min-height: 72px; resize: vertical; }
.help { font-size: 13px; color: var(--muted); }
.seg { display: inline-flex; border: 1px solid var(--color-divider); width: 100%; }
.seg-opt { flex: 1; padding: 10px 12px; text-align: center; font-size: 14px; cursor: pointer; min-height: 44px; display: flex; align-items: center; justify-content: center; }
.seg-opt input { position: absolute; opacity: 0; width: 0; height: 0; }
.seg-opt + .seg-opt { border-left: 1px solid var(--color-divider); }
.seg-opt.on { background: var(--color-accent); color: var(--color-bg); }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
@media (max-width: 800px) { .grid-2 { grid-template-columns: 1fr; } }

/* criteria table (authoring / review / reading) */
.criteria .input { min-height: 40px; }
.criteria td.num .input { width: 72px; text-align: right; }
.criteria tfoot td { font-weight: 600; border-bottom: 0; padding-top: 12px; }
.criteria tr.uncertain td { background: oklch(0.97 0.03 85); }
.criteria .evidence { font-size: 13px; color: var(--muted); }
.criteria .input.needs { border-color: var(--color-accent); }

/* mark display: number + 10px squares */
.mark { display: inline-flex; align-items: center; gap: 10px; font-variant-numeric: tabular-nums; font-weight: 600; }
.mark .sq { display: inline-flex; gap: 3px; flex-wrap: wrap; }
.mark .sq i { width: 10px; height: 10px; border: 1px solid var(--ink); display: block; }
.mark .sq i.on { background: var(--ink); }
.mark .upper { color: var(--tertiary); font-weight: 400; }

/* page cards, strips, pager */
.pg-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 14px 12px; }
.pg { position: relative; }
.pg img { width: 100%; height: 116px; object-fit: cover; border: 1px solid var(--color-divider); background: #fff; }
.pg .tag-n { position: absolute; top: 0; left: 0; background: var(--ink); color: var(--color-bg); font-size: 11px; padding: 2px 6px; font-weight: 600; }
.pg.dragging { transform: rotate(-2deg); outline: 2px solid var(--color-accent); box-shadow: var(--shadow-md); }
.pg .pg-actions { display: flex; }
.pg .pg-actions .btn { flex: 1; padding: 0; }
.pager { display: inline-flex; gap: 4px; }
.pager button { min-width: 36px; min-height: 36px; border: 1px solid var(--color-divider); background: transparent; font: inherit; cursor: pointer; }
.pager button.on { background: var(--ink); color: var(--color-bg); }
.page-view { border: 1px solid var(--color-divider); background: #fff; }
.page-view img { width: 100%; height: auto; }

/* drop zone */
.drop { border: 2px dashed var(--color-divider); min-height: 200px; padding: 24px; display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.drop.over { border-color: var(--color-accent); background: var(--color-accent-100); }
.drop h3 { font-size: 18px; margin: 0; }

/* dialog */
.dialog-backdrop { position: fixed; inset: 0; background: color-mix(in srgb, var(--color-neutral-900) 50%, transparent); display: flex; align-items: flex-start; justify-content: center; padding-top: 120px; z-index: 10; }
.dialog { background: var(--color-bg); width: min(760px, calc(100% - 32px)); padding: 28px; box-shadow: var(--shadow-lg); }
.dialog h2 { font-size: 24px; }
.dialog-footer { display: flex; gap: 8px; justify-content: flex-end; margin-top: 24px; }

/* progress / toolbar / two-column review */
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px var(--gutter); border-bottom: 2px solid var(--color-divider); flex-wrap: wrap; }
.cols { display: grid; grid-template-columns: 1fr 1fr; }
.cols > * { padding: 24px var(--gutter); }
.cols > * + * { border-left: 2px solid var(--color-divider); }
@media (max-width: 900px) { .cols { grid-template-columns: 1fr; } .cols > * + * { border-left: 0; border-top: 2px solid var(--color-divider); } }
.empty { padding: 48px 0; max-width: 520px; }
.empty h2 { font-size: 26px; }
.sign-in { display: grid; grid-template-columns: 560px 1fr; min-height: 100vh; }
.sign-in .form { padding: 32px 48px; border-right: 2px solid var(--color-divider); display: flex; flex-direction: column; }
.sign-in .form .center { margin: auto 0; max-width: 400px; }
.sign-in .hero { padding: 56px 64px; }
.sign-in .hero .photo { height: 420px; background: var(--color-neutral-300); }
.sign-in .hero p { font-size: 22px; font-weight: 600; margin-top: 24px; }
@media (max-width: 900px) { .sign-in { grid-template-columns: 1fr; } .sign-in .hero { display: none; } .sign-in .form { border-right: 0; } }
.qrow { display: flex; align-items: center; justify-content: space-between; padding: 14px 0; border-bottom: 1px solid var(--color-divider); gap: 16px; }
.qrow button { all: unset; cursor: pointer; display: flex; align-items: center; justify-content: space-between; width: 100%; min-height: 44px; }
.qrow-body { padding: 8px 0 20px; }
.callout { background: #fff; border-left: 2px solid var(--ink); padding: 10px 12px; margin: 8px 0; }
```

- [ ] **Step 3: API client and types**

`web/src/api/client.ts`:

```ts
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function parse(res: Response) {
  if (res.status === 204) return null;
  const text = await res.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = null; }
  if (!res.ok) {
    const err = body?.error ?? { code: "http_" + res.status, message: text || res.statusText };
    throw new ApiError(res.status, err.code, err.message);
  }
  return body;
}

const json = (method: string) => async <T>(path: string, body?: unknown): Promise<T> =>
  parse(await fetch(path, { method, headers: body === undefined ? {} : { "Content-Type": "application/json" },
                            body: body === undefined ? undefined : JSON.stringify(body), credentials: "same-origin" }));

export const api = {
  get: json("GET"),
  post: json("POST"),
  put: json("PUT"),
  async postForm<T>(path: string, form: FormData): Promise<T> {
    return parse(await fetch(path, { method: "POST", body: form, credentials: "same-origin" }));
  },
};
```

`web/src/api/types.ts`:

```ts
export type Subject = "math" | "language" | "science";
export type SubmissionStatus = "uploaded" | "queued" | "marking" | "needs_you" | "done" | "failed";

export interface ModelSpec { id: string; label: string; vision: boolean }
export interface ProviderSpec {
  id: string; label: string; transport: string; base_url: string | null; mode: string;
  default_model: string; default_rpm: number; models: ModelSpec[]; key_url: string; note: string; base_url_editable: boolean;
}
export interface Settings {
  provider: string; model: string; base_url: string | null; extractor_model: string | null;
  rpm_limit: number; confidence_threshold: number; has_key: boolean; key_hint: string;
}
export interface Check { ok: boolean; latency_ms: number; error: string | null }
export interface ProbeResult { text: Check; vision: Check }

export interface Criterion { id: string; description: string; max_score: number }
export interface Rubric { criterion_defs: Criterion[] }

export interface SubmissionRow {
  id: number; label: string; subject: Subject; page_count: number; status: SubmissionStatus; created_at: string;
  total: number | null; total_upper: number | null; total_max: number | null; needs_you_qids: string[];
}
export interface Page { id: number; page_index: number; width: number; height: number }
export interface Mark {
  q_id: string; criterion_scores: number[]; total: number; max: number; confidence: number | null;
  evidence: string; rationale: string; escalated: boolean; reason: string | null; queue_id: number | null;
  teacher_scores: number[] | null;
}
export interface Feedback {
  summary: string; strengths: string[];
  per_question_comments: { q_id: string; comment: string; suggested_action: string }[];
  improvement_plan: string[]; next_steps: string[];
}
export interface Job { status: "queued" | "running" | "done" | "failed"; attempts: number; error: string | null; started_at: string | null; finished_at: string | null }
export interface SubmissionDetail {
  id: number; label: string; subject: Subject; context: string; status: SubmissionStatus; created_at: string;
  rubric: Rubric; pages: Page[]; marks: Mark[]; totals: { total: number; total_upper: number; total_max: number } | null;
  feedback: Feedback | null; job: Job | null;
}
export interface QueueItem {
  id: number; submission_id: number; submission_label: string; q_id: string; reason: string; created_at: string;
  transcription: string; workings: string; proposed_criterion_scores: number[]; proposed_total: number | null;
  evidence: string; rationale: string; reviewer_note: string; criterion_defs: Criterion[]; page_ids: number[];
}
export interface Note { id: number; subject: string; note: string; status: string; created_at?: string }
export interface Exemplar { id: number; subject: string; topic: string; q_id: string; answer_text: string; awarded: number; max_score: number; why_it_matters: string; status: string }
export type Stats = Record<string, { count: number; mean_latency_ms: number; total_tokens_in: number; total_tokens_out: number }>;
```

- [ ] **Step 4: Write the failing lib tests**

`web/src/lib/__tests__/rubric.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { emptyRow, jsonToRows, rowsToRubricJson, rubricTotal, validateRows } from "../rubric";

describe("rubric", () => {
  it("round-trips rows and json", () => {
    const rows = [{ id: "c1", description: "Method", max_score: 2 }, { id: "c2", description: "Answer", max_score: 3 }];
    const json = rowsToRubricJson(rows);
    expect(JSON.parse(json)).toEqual({ criterion_defs: rows });
    expect(jsonToRows(json)).toEqual(rows);
  });
  it("assigns ids when blank and totals", () => {
    const rows = [{ ...emptyRow(), description: "A", max_score: 4 }, { ...emptyRow(), description: "B", max_score: 1 }];
    expect(JSON.parse(rowsToRubricJson(rows)).criterion_defs.map((c: any) => c.id)).toEqual(["c1", "c2"]);
    expect(rubricTotal(rows)).toBe(5);
  });
  it("validates", () => {
    expect(validateRows([])).toMatch(/at least one/);
    expect(validateRows([{ id: "", description: "", max_score: 1 }])).toMatch(/description/i);
    expect(validateRows([{ id: "", description: "x", max_score: 0 }])).toMatch(/marks/i);
    expect(validateRows([{ id: "", description: "x", max_score: 2 }])).toBeNull();
  });
  it("rejects bad json", () => {
    expect(() => jsonToRows("{}")).toThrow();
  });
});
```

`web/src/lib/__tests__/marks.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { statusLabel, totalLabel } from "../marks";

describe("marks", () => {
  it("formats totals and ranges", () => {
    expect(totalLabel({ total: 18, total_upper: 18, total_max: 25 })).toBe("18 / 25");
    expect(totalLabel({ total: 15, total_upper: 17, total_max: 25 })).toBe("15–17 / 25");
    expect(totalLabel(null)).toBe("—");
  });
  it("labels statuses in plain words", () => {
    expect(statusLabel("needs_you", ["q3"])).toBe("Needs you · Q3");
    expect(statusLabel("marking", [])).toBe("Marking");
    expect(statusLabel("done", [])).toBe("Done");
  });
});
```

Run: `cd web && npx vitest run` → FAIL (modules missing).

- [ ] **Step 5: Implement libs**

`web/src/lib/rubric.ts`:

```ts
import type { Criterion } from "../api/types";

export type Row = Criterion;

export const emptyRow = (): Row => ({ id: "", description: "", max_score: 1 });

export function rubricTotal(rows: Row[]): number {
  return rows.reduce((s, r) => s + (Number(r.max_score) || 0), 0);
}

export function validateRows(rows: Row[]): string | null {
  if (rows.length === 0) return "Add at least one criterion.";
  for (const r of rows) {
    if (!r.description.trim()) return "Every criterion needs a description.";
    if (!Number.isInteger(r.max_score) || r.max_score < 1) return "Max marks must be a whole number of 1 or more.";
  }
  return null;
}

export function rowsToRubricJson(rows: Row[]): string {
  const criterion_defs = rows.map((r, i) => ({ id: r.id.trim() || `c${i + 1}`, description: r.description.trim(), max_score: Number(r.max_score) }));
  return JSON.stringify({ criterion_defs });
}

export function jsonToRows(json: string): Row[] {
  const parsed = JSON.parse(json);
  if (!parsed || !Array.isArray(parsed.criterion_defs)) throw new Error("Expected {\"criterion_defs\": [...]}");
  return parsed.criterion_defs.map((c: any, i: number) => ({
    id: String(c.id ?? `c${i + 1}`), description: String(c.description ?? ""), max_score: Number(c.max_score ?? 0),
  }));
}
```

`web/src/lib/marks.ts`:

```ts
import type { SubmissionStatus } from "../api/types";

export function totalLabel(t: { total: number; total_upper: number; total_max: number } | null | undefined): string {
  if (!t) return "—";
  return t.total === t.total_upper ? `${t.total} / ${t.total_max}` : `${t.total}–${t.total_upper} / ${t.total_max}`;
}

export function qLabel(qId: string): string {
  return qId.replace(/^q/i, "Q");
}

export function statusLabel(status: SubmissionStatus, needsYou: string[]): string {
  switch (status) {
    case "uploaded": return "Uploaded";
    case "queued": return "Waiting to mark";
    case "marking": return "Marking";
    case "needs_you": return needsYou.length ? `Needs you · ${needsYou.map(qLabel).join(", ")}` : "Needs you";
    case "done": return "Done";
    case "failed": return "Failed";
  }
}

export const pillClass: Record<SubmissionStatus, string> = {
  uploaded: "pill-outline", queued: "pill-neutral", marking: "pill-neutral", needs_you: "pill-amber", done: "pill-ink", failed: "pill-failed",
};
```

`web/src/lib/format.ts`:

```ts
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-SG", { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export function elapsed(iso: string | null | undefined): string {
  if (!iso) return "";
  const start = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z").getTime();
  const s = Math.max(0, Math.floor((Date.now() - start) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export const subjectLabel: Record<string, string> = { math: "Maths", language: "English", science: "Science" };
```

- [ ] **Step 6: Shared components**

`web/src/components/Button.tsx`:

```tsx
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost"; size?: "sm" | "md" | "lg"; wide?: boolean; keyHint?: string; icon?: ReactNode;
};

export function Button({ variant = "secondary", size = "md", wide, keyHint, icon, className = "", children, ...rest }: Props) {
  const cls = ["btn", `btn-${variant}`, size === "lg" ? "btn-lg" : size === "sm" ? "btn-sm" : "", wide ? "btn-wide" : "", className].join(" ");
  return (
    <button className={cls} {...rest}>
      {icon}{children}{keyHint && <span className="key">{keyHint}</span>}
    </button>
  );
}
```

`web/src/components/StatusPill.tsx`:

```tsx
import { TriangleAlert } from "lucide-react";
import type { SubmissionStatus } from "../api/types";
import { pillClass, statusLabel } from "../lib/marks";

export function StatusPill({ status, needsYou = [] }: { status: SubmissionStatus; needsYou?: string[] }) {
  return (
    <span className={`pill ${pillClass[status]}`} data-status={status}>
      {status === "needs_you" && <TriangleAlert size={14} strokeWidth={2.5} aria-hidden />}
      {statusLabel(status, needsYou)}
    </span>
  );
}
```

`web/src/components/Notice.tsx`:

```tsx
import { Check, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

export function Notice({ kind = "amber", children }: { kind?: "amber" | "ok" | "error"; children: ReactNode }) {
  return (
    <div className={`notice ${kind === "ok" ? "notice-ok" : kind === "error" ? "notice-error" : ""}`} role={kind === "ok" ? "status" : "alert"}>
      {kind === "ok" ? <Check size={18} strokeWidth={2.5} aria-hidden /> : <TriangleAlert size={18} strokeWidth={2.5} aria-hidden />}
      <div>{children}</div>
    </div>
  );
}
```

`web/src/components/EmptyState.tsx`:

```tsx
import type { ReactNode } from "react";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><h2>{title}</h2>{children}</div>;
}
```

`web/src/components/MarkDisplay.tsx`:

```tsx
export function MarkDisplay({ earned, max, upper, squares = true }: { earned: number; max: number; upper?: number; squares?: boolean }) {
  const hi = upper ?? earned;
  return (
    <span className="mark" aria-label={`${earned}${hi !== earned ? ` to ${hi}` : ""} out of ${max}`}>
      {squares && max <= 30 && (
        <span className="sq" aria-hidden>
          {Array.from({ length: max }, (_, i) => <i key={i} className={i < earned ? "on" : ""} />)}
        </span>
      )}
      <span>{earned}{hi !== earned && <span className="upper">–{hi}</span>} / {max}</span>
    </span>
  );
}
```

`web/src/components/CriteriaTable.tsx` — three modes:

```tsx
import { X } from "lucide-react";
import type { Criterion } from "../api/types";
import { rubricTotal, type Row } from "../lib/rubric";

export function CriteriaEditor({ rows, onChange }: { rows: Row[]; onChange: (rows: Row[]) => void }) {
  const set = (i: number, patch: Partial<Row>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <table className="table criteria">
      <thead><tr><th>Criterion</th><th>Description</th><th className="num">Max</th><th /></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td><input className="input" aria-label={`Criterion ${i + 1} id`} placeholder={`c${i + 1}`} value={r.id} onChange={(e) => set(i, { id: e.target.value })} /></td>
            <td><input className="input" aria-label={`Criterion ${i + 1} description`} placeholder="Correct method" value={r.description} onChange={(e) => set(i, { description: e.target.value })} /></td>
            <td className="num"><input className="input" type="number" min={1} aria-label={`Criterion ${i + 1} max marks`} value={r.max_score} onChange={(e) => set(i, { max_score: Number(e.target.value) })} /></td>
            <td><button type="button" className="btn btn-ghost btn-sm" aria-label={`Remove criterion ${i + 1}`} onClick={() => onChange(rows.filter((_, j) => j !== i))}><X size={16} /></button></td>
          </tr>
        ))}
      </tbody>
      <tfoot><tr><td colSpan={2}><button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange([...rows, { id: "", description: "", max_score: 1 }])}>+ Add criterion</button></td><td className="num">{rubricTotal(rows)}</td><td /></tr></tfoot>
    </table>
  );
}

export function CriteriaReview({ defs, proposed, evidence, values, onChange }:
  { defs: Criterion[]; proposed: number[]; evidence?: string; values: (number | "")[]; onChange: (v: (number | "")[]) => void }) {
  const total = values.reduce<number>((s, v) => s + (v === "" ? 0 : v), 0);
  const max = defs.reduce((s, d) => s + d.max_score, 0);
  return (
    <table className="table criteria">
      <thead><tr><th>Criterion</th><th className="num">Proposed</th><th className="num" style={{ width: 88 }}>Your mark</th></tr></thead>
      <tbody>
        {defs.map((d, i) => (
          <tr key={d.id} className={values[i] === "" ? "uncertain" : ""}>
            <td><strong>{d.description}</strong>{i === 0 && evidence && <div className="evidence">“{evidence}”</div>}</td>
            <td className="num">{proposed[i] ?? "?"} / {d.max_score}</td>
            <td className="num"><input className={`input ${values[i] === "" ? "needs" : ""}`} type="number" min={0} max={d.max_score} placeholder="?" aria-label={`Your mark for ${d.description}`} value={values[i]} data-criterion={i}
              onChange={(e) => onChange(values.map((v, j) => (j === i ? (e.target.value === "" ? "" : Math.max(0, Math.min(d.max_score, Number(e.target.value)))) : v)))} /></td>
          </tr>
        ))}
      </tbody>
      <tfoot><tr><td>Question total</td><td className="num">{proposed.reduce((s, p) => s + p, 0)} / {max}</td><td className="num" style={{ fontSize: 18 }}>{total} / {max}</td></tr></tfoot>
    </table>
  );
}

export function CriteriaReading({ defs, scores }: { defs: Criterion[]; scores: number[] }) {
  return (
    <table className="table criteria">
      <tbody>{defs.map((d, i) => <tr key={d.id}><td>{d.description}</td><td className="num">{scores[i] ?? "—"} / {d.max_score}</td></tr>)}</tbody>
    </table>
  );
}
```

`web/src/components/PageCard.tsx`:

```tsx
export function PageCard({ src, index, onRemove, onMoveLeft, onMoveRight }:
  { src: string; index: number; onRemove?: () => void; onMoveLeft?: () => void; onMoveRight?: () => void }) {
  return (
    <div className="pg">
      <img src={src} alt={`Page ${index + 1}`} className="grayscale" />
      <span className="tag-n">{index + 1}</span>
      {(onRemove || onMoveLeft || onMoveRight) && (
        <div className="pg-actions">
          {onMoveLeft && <button type="button" className="btn btn-ghost btn-sm" onClick={onMoveLeft} aria-label={`Move page ${index + 1} earlier`}>←</button>}
          {onMoveRight && <button type="button" className="btn btn-ghost btn-sm" onClick={onMoveRight} aria-label={`Move page ${index + 1} later`}>→</button>}
          {onRemove && <button type="button" className="btn btn-ghost btn-sm" onClick={onRemove}>Delete</button>}
        </div>
      )}
    </div>
  );
}
```

`web/src/components/PagePager.tsx`:

```tsx
export function PagePager({ count, current, onSelect }: { count: number; current: number; onSelect: (i: number) => void }) {
  return (
    <div className="pager" role="tablist" aria-label="Pages">
      {Array.from({ length: count }, (_, i) => (
        <button key={i} role="tab" aria-selected={i === current} className={i === current ? "on" : ""} onClick={() => onSelect(i)}>{i + 1}</button>
      ))}
    </div>
  );
}
```

`web/src/components/DropZone.tsx`:

```tsx
import { Upload } from "lucide-react";
import { useRef, useState } from "react";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.heic,.heif,image/*,application/pdf";

export function DropZone({ onFiles, title = "Drop pages here", hint = "PDF, JPG, PNG or HEIC — up to 50 MB" }:
  { onFiles: (files: File[]) => void; title?: string; hint?: string }) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className={`drop ${over ? "over" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFiles(Array.from(e.dataTransfer.files)); }}>
      <Upload size={32} aria-hidden />
      <h3>{title}</h3>
      <p className="help">{hint}</p>
      <button type="button" className="btn btn-secondary" onClick={() => input.current?.click()}>Choose files</button>
      <input ref={input} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { onFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
    </div>
  );
}
```

`web/src/components/Dialog.tsx`:

```tsx
import type { ReactNode } from "react";

export function Dialog({ title, children, footer, onClose }: { title: string; children: ReactNode; footer: ReactNode; onClose: () => void }) {
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="dlg-title">{title}</h2>
        {children}
        <div className="dialog-footer">{footer}</div>
      </div>
    </div>
  );
}
```

`web/src/components/Nav.tsx`:

```tsx
import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../api/client";

export function Nav({ needsYou }: { needsYou: number }) {
  const nav = useNavigate();
  // NavLink sets aria-current="page" on the active link by itself; app.css styles [aria-current="page"].
  return (
    <nav className="nav">
      <NavLink to="/submissions" className="nav-brand" end>Smart Marking</NavLink>
      <div className="nav-links">
        <NavLink to="/submissions">Submissions</NavLink>
        <NavLink to="/review">Review {needsYou > 0 && <span className="key">{needsYou}</span>}</NavLink>
        <NavLink to="/learning">Learning</NavLink>
        <NavLink to="/settings">Settings</NavLink>
        <a href="#" onClick={async (e) => { e.preventDefault(); await api.post("/api/auth/logout"); nav("/sign-in"); }}>Sign out</a>
      </div>
    </nav>
  );
}
```

- [ ] **Step 7: Component tests**

`web/src/components/__tests__/StatusPill.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { StatusPill } from "../StatusPill";

it("renders the plain-words label and amber class for needs_you", () => {
  render(<StatusPill status="needs_you" needsYou={["q2", "q5"]} />);
  const el = screen.getByText("Needs you · Q2, Q5");
  expect(el.closest(".pill")).toHaveClass("pill-amber");
});
```

`web/src/components/__tests__/MarkDisplay.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MarkDisplay } from "../MarkDisplay";

it("shows a range and an accessible label", () => {
  render(<MarkDisplay earned={15} max={25} upper={17} />);
  expect(screen.getByLabelText("15 to 17 out of 25")).toBeInTheDocument();
  expect(document.querySelectorAll(".sq i.on")).toHaveLength(15);
});
```

- [ ] **Step 8: App shell, auth gate, sign-in page, stubs**

`web/src/main.tsx`:

```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./styles/tokens.css";
import "./styles/app.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode><BrowserRouter><App /></BrowserRouter></React.StrictMode>,
);
```

`web/src/App.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { api, ApiError } from "./api/client";
import type { QueueItem } from "./api/types";
import { Nav } from "./components/Nav";
import { Learning } from "./pages/Learning";
import { NewSubmission } from "./pages/NewSubmission";
import { Review } from "./pages/Review";
import { Settings } from "./pages/Settings";
import { SignIn } from "./pages/SignIn";
import { SubmissionDetail } from "./pages/SubmissionDetail";
import { Submissions } from "./pages/Submissions";

function Shell() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [needsYou, setNeedsYou] = useState(0);
  const loc = useLocation();
  const refreshQueue = useCallback(async () => {
    try { setNeedsYou((await api.get<QueueItem[]>("/api/queue")).length); } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    api.get("/api/auth/me").then(() => setAuthed(true)).catch((e) => setAuthed(!(e instanceof ApiError && e.status === 401)));
  }, []);
  useEffect(() => { if (authed) refreshQueue(); }, [authed, loc.pathname, refreshQueue]);
  if (authed === null) return <p className="page muted">Loading…</p>;
  if (!authed) return <Navigate to="/sign-in" replace state={{ from: loc.pathname }} />;
  return <><Nav needsYou={needsYou} /><Outlet context={{ refreshQueue }} /></>;
}

export function App() {
  return (
    <Routes>
      <Route path="/sign-in" element={<SignIn />} />
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/submissions" replace />} />
        <Route path="/submissions" element={<Submissions />} />
        <Route path="/submissions/new" element={<NewSubmission />} />
        <Route path="/submissions/:id" element={<SubmissionDetail />} />
        <Route path="/review" element={<Review />} />
        <Route path="/learning" element={<Learning />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/submissions" replace />} />
    </Routes>
  );
}
```

`web/src/pages/SignIn.tsx` (T1 without Google/email):

```tsx
import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Button } from "../components/Button";
import { Notice } from "../components/Notice";

export function SignIn() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const from = (useLocation().state as any)?.from ?? "/submissions";
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null);
    try { await api.post("/api/auth/login", { password }); nav(from, { replace: true }); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Could not sign in"); }
    finally { setBusy(false); }
  };
  return (
    <div className="sign-in">
      <div className="form">
        <span className="nav-brand">Smart Marking</span>
        <form className="center" onSubmit={submit}>
          <h1 style={{ fontSize: 36 }}>Sign in</h1>
          <p className="meta">Teachers only. Enter the password your school set when it deployed Smart Marking.</p>
          {error && <Notice>{error}</Notice>}
          <div className="field" style={{ marginTop: 20 }}>
            <label htmlFor="pw">Password</label>
            <input id="pw" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <Button type="submit" variant="primary" size="lg" wide disabled={busy || !password}>{busy ? "Signing in…" : "Sign in"}</Button>
        </form>
        <p className="tertiary" style={{ fontSize: 12 }}>Smart Marking · self-hosted on Railway</p>
      </div>
      <div className="hero">
        <div className="photo grayscale" aria-hidden />
        <p>Handwritten scripts marked against your rubric. You check the doubtful ones, then release.</p>
      </div>
    </div>
  );
}
```

Create stubs so the app compiles (each replaced in Tasks 15–18):

```tsx
// web/src/pages/Settings.tsx, Submissions.tsx, NewSubmission.tsx, SubmissionDetail.tsx, Review.tsx, Learning.tsx
export function Settings() { return <div className="page"><h1>Settings</h1></div>; }
// …same one-liner per file with its own export name
```

- [ ] **Step 9: Run tests and build**

```bash
cd web && npx vitest run && npm run build
```

Expected: 4 test files pass; `dist/index.html` exists. Then, from the repo root, run the API and open the built SPA:

```bash
SECRET_KEY=dev TEACHER_PASSWORD=dev DATABASE_URL=sqlite:///dev.db STORAGE_DIR=./data uv run sms serve --port 8010
```

Open `http://localhost:8010` in the in-app browser: sign-in page renders in the Modernist style, wrong password shows the amber notice, correct password lands on `/submissions` with the nav. Compare against `docs/design-handoff/screenshots/T1-sign-in.png`.

- [ ] **Step 10: Commit**

```bash
git add web
git commit -m "feat(web): Vite + React scaffold, Modernist tokens, shared components, sign-in

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 15: Settings page

**Files:**
- Modify: `web/src/pages/Settings.tsx`

**Interfaces:**
- Consumes: `GET /api/providers`, `GET/PUT /api/settings`, `POST /api/settings/test`.

- [ ] **Step 1: Implement**

`web/src/pages/Settings.tsx`:

```tsx
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { ProbeResult, ProviderSpec, Settings as S } from "../api/types";
import { Button } from "../components/Button";
import { Notice } from "../components/Notice";

type Form = { provider: string; model: string; custom_model: string; api_key: string; base_url: string; extractor_model: string; rpm_limit: number; confidence_threshold: number };

export function Settings() {
  const [providers, setProviders] = useState<ProviderSpec[]>([]);
  const [saved, setSaved] = useState<S | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [busy, setBusy] = useState<"test" | "save" | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  useEffect(() => {
    Promise.all([api.get<ProviderSpec[]>("/api/providers"), api.get<S>("/api/settings")]).then(([p, s]) => {
      setProviders(p); setSaved(s);
      const spec = p.find((x) => x.id === s.provider)!;
      const listed = spec.models.some((m) => m.id === s.model);
      setForm({ provider: s.provider, model: listed ? s.model : "__custom__", custom_model: listed ? "" : s.model, api_key: "",
                base_url: s.base_url ?? "", extractor_model: s.extractor_model ?? "", rpm_limit: s.rpm_limit, confidence_threshold: s.confidence_threshold });
    }).catch((e) => setMsg({ kind: "error", text: e.message }));
  }, []);

  const spec = useMemo(() => providers.find((p) => p.id === form?.provider), [providers, form?.provider]);
  if (!form || !spec || !saved) return <div className="page muted">Loading…</div>;

  const modelId = form.model === "__custom__" ? form.custom_model.trim() : form.model;
  const payload = { provider: form.provider, model: modelId, api_key: form.api_key || undefined, base_url: form.base_url || undefined,
                    extractor_model: form.extractor_model || undefined, rpm_limit: form.rpm_limit, confidence_threshold: form.confidence_threshold };

  const changeProvider = (id: string) => {
    const p = providers.find((x) => x.id === id)!;
    setForm({ ...form, provider: id, model: p.default_model, custom_model: "", base_url: "", rpm_limit: p.default_rpm });
    setProbe(null);
  };

  const test = async () => {
    setBusy("test"); setMsg(null); setProbe(null);
    try { setProbe(await api.post<ProbeResult>("/api/settings/test", payload)); }
    catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not test" }); }
    finally { setBusy(null); }
  };
  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy("save"); setMsg(null);
    try { const s = await api.put<S>("/api/settings", payload); setSaved(s); setForm({ ...form, api_key: "" }); setMsg({ kind: "ok", text: "Saved." }); }
    catch (err) { setMsg({ kind: "error", text: err instanceof ApiError ? err.message : "Could not save" }); }
    finally { setBusy(null); }
  };

  return (
    <div className="page">
      <div className="page-header"><div><h1>AI model</h1><p className="meta">Which model marks your scripts, and the key it uses.</p></div></div>
      <hr className="rule-2" />
      <form onSubmit={save} style={{ maxWidth: 720, marginTop: 24 }}>
        <div className="field">
          <label>Provider</label>
          <div className="seg" role="radiogroup" aria-label="Provider">
            {providers.map((p) => (
              <label key={p.id} className={`seg-opt ${form.provider === p.id ? "on" : ""}`}>
                <input type="radio" name="provider" value={p.id} checked={form.provider === p.id} onChange={() => changeProvider(p.id)} />{p.label}
              </label>
            ))}
          </div>
          {spec.note && <p className="help">{spec.note}</p>}
        </div>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="model">Model</label>
            <select id="model" className="input" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}>
              {spec.models.map((m) => <option key={m.id} value={m.id}>{m.label}{m.vision ? " · reads pages" : " · text only"}</option>)}
              <option value="__custom__">Custom model id…</option>
            </select>
            {form.model === "__custom__" && <input className="input" placeholder="exact model id" aria-label="Custom model id" value={form.custom_model} onChange={(e) => setForm({ ...form, custom_model: e.target.value })} />}
          </div>
          <div className="field">
            <label htmlFor="key">API key</label>
            <input id="key" className="input" type="password" autoComplete="off" placeholder={saved.has_key ? `Saved key ending …${saved.key_hint} — leave blank to keep` : "Paste your key"} value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
            <a className="help" href={spec.key_url} target="_blank" rel="noreferrer">Where to get a {spec.label} key</a>
          </div>
        </div>
        {spec.base_url_editable && (
          <div className="field"><label htmlFor="base">Base URL</label>
            <input id="base" className="input" placeholder={spec.base_url ?? ""} value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} /></div>
        )}
        <div className="grid-2">
          <div className="field"><label htmlFor="ext">Different model for reading pages (optional)</label>
            <input id="ext" className="input" placeholder="leave blank to use the same model" value={form.extractor_model} onChange={(e) => setForm({ ...form, extractor_model: e.target.value })} />
            <span className="help">Use a cheap vision model to transcribe, and a stronger one to mark.</span></div>
          <div className="field"><label htmlFor="rpm">Requests per minute</label>
            <input id="rpm" className="input" type="number" min={0} value={form.rpm_limit} onChange={(e) => setForm({ ...form, rpm_limit: Number(e.target.value) })} />
            <span className="help">0 = no limit. A script needs about 4 requests.</span></div>
        </div>
        <div className="field" style={{ maxWidth: 340 }}><label htmlFor="thr">Ask me when confidence is below</label>
          <input id="thr" className="input" type="number" min={0} max={1} step={0.05} value={form.confidence_threshold} onChange={(e) => setForm({ ...form, confidence_threshold: Number(e.target.value) })} />
          <span className="help">0 turns this off. 0.6 is a sensible start.</span></div>

        {probe && (
          <Notice kind={probe.text.ok && probe.vision.ok ? "ok" : "amber"}>
            <strong>Text {probe.text.ok ? `✓ ${(probe.text.latency_ms / 1000).toFixed(1)} s` : `✗ ${probe.text.error}`}</strong><br />
            <strong>Vision {probe.vision.ok ? `✓ ${(probe.vision.latency_ms / 1000).toFixed(1)} s` : `✗ ${probe.vision.error}`}</strong>
            {!probe.vision.ok && probe.text.ok && <div>This model may not read images. Pick a model marked “reads pages”, or set a different model for reading pages.</div>}
          </Notice>
        )}
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
        <div className="actions" style={{ marginTop: 24 }}>
          <Button type="button" size="lg" onClick={test} disabled={busy !== null || !modelId || (!form.api_key && !saved.has_key)}>{busy === "test" ? "Testing…" : "Test connection"}</Button>
          <Button type="submit" variant="primary" size="lg" disabled={busy !== null || !modelId}>{busy === "save" ? "Saving…" : "Save"}</Button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 2: Verify in the browser**

`cd web && npm run build`, restart `sms serve`, open `/settings`: six providers in the segmented control; switching provider resets the model and RPM; TokenRouter note visible; "Test connection" with a bogus key shows the provider error in an amber notice; Save shows "Saved." and the key placeholder shows the hint. `npx tsc --noEmit` clean.

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/Settings.tsx
git commit -m "feat(web): settings page with provider/model picker and test connection

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 16: Submissions list and "Mark a script" page

**Files:**
- Modify: `web/src/pages/Submissions.tsx`, `web/src/pages/NewSubmission.tsx`

**Interfaces:**
- Consumes: `GET /api/submissions`, `POST /api/submissions` (multipart), `GET /api/settings`.

- [ ] **Step 1: Submissions list (T2 table)**

`web/src/pages/Submissions.tsx`:

```tsx
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { SubmissionRow } from "../api/types";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { StatusPill } from "../components/StatusPill";
import { fmtDate, subjectLabel } from "../lib/format";
import { totalLabel } from "../lib/marks";

export function Submissions() {
  const [rows, setRows] = useState<SubmissionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();
  useEffect(() => {
    let alive = true;
    const load = () => api.get<SubmissionRow[]>("/api/submissions").then((r) => alive && setRows(r)).catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Submissions</h1><p className="meta">Scripts you have uploaded for marking.</p></div>
        <Button variant="primary" icon={<Plus size={18} />} onClick={() => nav("/submissions/new")}>Mark a script</Button>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {rows && rows.length === 0 && (
        <EmptyState title="Nothing marked yet">
          <p>Upload a script’s pages and a rubric. Marking runs in the background; questions the AI is unsure about land under <strong>Review</strong>.</p>
          <Link to="/submissions/new" className="btn btn-primary">Mark a script</Link>
        </EmptyState>
      )}
      {rows && rows.length > 0 && (
        <table className="table tall">
          <thead><tr><th>Script</th><th>Subject</th><th className="num">Pages</th><th>Status</th><th className="num">Total</th><th>Uploaded</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="row-link" onClick={() => nav(`/submissions/${r.id}`)}>
                <td><strong>{r.label}</strong></td>
                <td>{subjectLabel[r.subject]}</td>
                <td className="num">{r.page_count}</td>
                <td><StatusPill status={r.status} needsYou={r.needs_you_qids} /></td>
                <td className="num">{r.total === null ? "—" : totalLabel({ total: r.total, total_upper: r.total_upper!, total_max: r.total_max! })}</td>
                <td className="muted">{fmtDate(r.created_at)}</td>
                <td>→</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Mark a script (T5 form + T3 drop zone + S4 page cards)**

`web/src/pages/NewSubmission.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Settings, Subject } from "../api/types";
import { Button } from "../components/Button";
import { CriteriaEditor } from "../components/CriteriaTable";
import { DropZone } from "../components/DropZone";
import { Notice } from "../components/Notice";
import { PageCard } from "../components/PageCard";
import { emptyRow, jsonToRows, rowsToRubricJson, validateRows, type Row } from "../lib/rubric";

type Picked = { file: File; url: string };

export function NewSubmission() {
  const nav = useNavigate();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [label, setLabel] = useState("");
  const [subject, setSubject] = useState<Subject>("math");
  const [context, setContext] = useState("");
  const [rows, setRows] = useState<Row[]>([{ ...emptyRow(), id: "c1", description: "Correct method", max_score: 2 }, { ...emptyRow(), id: "c2", description: "Correct final answer", max_score: 3 }]);
  const [files, setFiles] = useState<Picked[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get<Settings>("/api/settings").then(setSettings).catch(() => setSettings(null)); }, []);
  const filesRef = useRef<Picked[]>([]);
  filesRef.current = files;
  // Revoke object URLs only when the page unmounts — revoking on every change would blank the remaining thumbnails.
  useEffect(() => () => filesRef.current.forEach((f) => f.url && URL.revokeObjectURL(f.url)), []);

  const add = (picked: File[]) => setFiles((cur) => [...cur, ...picked.map((file) => ({ file, url: file.type.startsWith("image/") ? URL.createObjectURL(file) : "" }))]);
  const remove = (i: number) => setFiles((cur) => { cur[i].url && URL.revokeObjectURL(cur[i].url); return cur.filter((_, j) => j !== i); });
  const move = (i: number, d: -1 | 1) => setFiles((cur) => { const c = [...cur]; const j = i + d; if (j < 0 || j >= c.length) return cur; [c[i], c[j]] = [c[j], c[i]]; return c; });
  const uploadJson = (f: File) => f.text().then((t) => { try { setRows(jsonToRows(t)); setError(null); } catch (e: any) { setError(`Rubric JSON: ${e.message}`); } });

  const problem = useMemo(() => {
    if (!label.trim()) return "Give the script a label, e.g. the student’s name.";
    const v = validateRows(rows); if (v) return v;
    if (files.length === 0) return "Add at least one page.";
    return null;
  }, [label, rows, files]);

  const submit = async () => {
    setBusy(true); setError(null);
    const fd = new FormData();
    fd.set("label", label.trim()); fd.set("subject", subject); fd.set("context", context.trim()); fd.set("rubric", rowsToRubricJson(rows));
    files.forEach((f) => fd.append("files", f.file, f.file.name));
    try { const r = await api.postForm<{ id: number }>("/api/submissions", fd); nav(`/submissions/${r.id}`); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Upload failed — check your connection and try again."); setBusy(false); }
  };

  return (
    <div className="page">
      <Link to="/submissions" className="breadcrumb">← Submissions</Link>
      <div className="page-header"><div><h1>Mark a script</h1><p className="meta">One student’s pages, marked against your criteria.</p></div></div>
      {settings && !settings.has_key && <Notice>No API key yet. <Link to="/settings">Add one under Settings</Link> before marking.</Notice>}
      <div className="grid-2" style={{ marginTop: 24 }}>
        <div>
          <div className="field"><label htmlFor="label">Label</label><input id="label" className="input" placeholder="Tan Wei Ling · Worksheet 3" value={label} onChange={(e) => setLabel(e.target.value)} /></div>
          <div className="grid-2">
            <div className="field"><label>Subject</label>
              <div className="seg" role="radiogroup" aria-label="Subject">
                {(["math", "language", "science"] as Subject[]).map((s) => (
                  <label key={s} className={`seg-opt ${subject === s ? "on" : ""}`}><input type="radio" name="subject" checked={subject === s} onChange={() => setSubject(s)} />{{ math: "Maths", language: "English", science: "Science" }[s]}</label>
                ))}
              </div></div>
            <div className="field"><label htmlFor="ctx">Context (optional)</label><input id="ctx" className="input" placeholder="Sec 4 · Quadratic equations · 5 questions" value={context} onChange={(e) => setContext(e.target.value)} /></div>
          </div>
          <div className="field">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <label>Rubric <span className="help">— applied to every question</span></label>
              <label className="btn btn-ghost btn-sm" style={{ cursor: "pointer" }}>Upload JSON instead<input type="file" accept=".json,application/json" hidden onChange={(e) => e.target.files?.[0] && uploadJson(e.target.files[0])} /></label>
            </div>
            <CriteriaEditor rows={rows} onChange={setRows} />
          </div>
        </div>
        <div>
          <DropZone onFiles={add} />
          {files.length > 0 && (
            <>
              <p className="help" style={{ marginTop: 12 }}>{files.length} file{files.length > 1 ? "s" : ""} · pages are read in this order. PDFs are split into pages.</p>
              <div className="pg-grid">
                {files.map((f, i) => f.url
                  ? <PageCard key={i} src={f.url} index={i} onRemove={() => remove(i)} onMoveLeft={i > 0 ? () => move(i, -1) : undefined} onMoveRight={i < files.length - 1 ? () => move(i, 1) : undefined} />
                  : <div key={i} className="pg"><div className="page-view" style={{ height: 116, padding: 12, fontSize: 13 }}>{f.file.name}</div><span className="tag-n">{i + 1}</span><div className="pg-actions"><button type="button" className="btn btn-ghost btn-sm" onClick={() => remove(i)}>Delete</button></div></div>)}
              </div>
            </>
          )}
        </div>
      </div>
      {error && <div style={{ marginTop: 16 }}><Notice kind="error">{error}</Notice></div>}
      <hr className="rule-2" style={{ marginTop: 24 }} />
      <div className="actions" style={{ marginTop: 16, alignItems: "center" }}>
        <Button variant="primary" size="lg" onClick={submit} disabled={busy || !!problem || !settings?.has_key} title={problem ?? undefined}>{busy ? "Uploading…" : "Start marking"}</Button>
        <span className="help">{problem ?? (settings?.provider === "tokenrouter" ? "Marking takes about 30 s per script on the free tier." : "Marking usually takes under a minute.")}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify in the browser**

Build, restart, open `/submissions/new`: the form matches the T5 side panel (title, segmented subject, criteria table with running total and "+ Add criterion", "Upload JSON instead"), the drop zone accepts a PDF and PNGs, page cards show thumbnails with number tags and reorder arrows, "Start marking" is disabled with the reason shown until label/rubric/pages are set. Submit with a fake key configured → navigates to the detail page (stub for now). `/submissions` shows the row with "Waiting to mark"/"Marking", then "Failed" once the worker hits the bad key — the loop is closed end to end.

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/Submissions.tsx web/src/pages/NewSubmission.tsx
git commit -m "feat(web): submissions list and mark-a-script upload page

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 17: Submission detail page

**Files:**
- Modify: `web/src/pages/SubmissionDetail.tsx`

**Interfaces:**
- Consumes: `GET /api/submissions/{id}`, `POST /api/submissions/{id}/retry`, `GET /api/pages/{id}`.

- [ ] **Step 1: Implement (T9 layout)**

`web/src/pages/SubmissionDetail.tsx`:

```tsx
import { TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { SubmissionDetail as D } from "../api/types";
import { Button } from "../components/Button";
import { CriteriaReading } from "../components/CriteriaTable";
import { MarkDisplay } from "../components/MarkDisplay";
import { Notice } from "../components/Notice";
import { PagePager } from "../components/PagePager";
import { StatusPill } from "../components/StatusPill";
import { elapsed, fmtDate, subjectLabel } from "../lib/format";
import { qLabel } from "../lib/marks";

export function SubmissionDetail() {
  const { id } = useParams();
  const [d, setD] = useState<D | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = () => api.get<D>(`/api/submissions/${id}`).then((r) => { if (alive) { setD(r); setError(null); } }).catch((e) => alive && setError(e instanceof ApiError ? e.message : "Could not load"));
    load();
    const t = setInterval(() => { setTick((x) => x + 1); if (!d || ["uploaded", "queued", "marking"].includes(d.status)) load(); }, 3000);
    return () => { alive = false; clearInterval(t); };
  }, [id, d?.status]);

  if (error) return <div className="page"><Notice kind="error">{error}</Notice></div>;
  if (!d) return <div className="page muted">Loading…</div>;
  const inProgress = ["uploaded", "queued", "marking"].includes(d.status);
  const needsYou = d.marks.filter((m) => m.escalated).map((m) => m.q_id);
  const perQMax = d.rubric.criterion_defs.reduce((s, c) => s + c.max_score, 0);

  const retry = async () => { await api.post(`/api/submissions/${d.id}/retry`); setD({ ...d, status: "queued" }); };

  return (
    <div>
      <div className="page" style={{ paddingBottom: 24 }}>
        <Link to="/submissions" className="breadcrumb">← Submissions</Link>
        <div className="page-header">
          <div>
            <h1>{d.label}</h1>
            <p className="meta">{subjectLabel[d.subject]}{d.context && ` · ${d.context}`} · uploaded {fmtDate(d.created_at)} · {d.pages.length} page{d.pages.length === 1 ? "" : "s"}</p>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="label-caps">Total</div>
            {d.totals ? <div style={{ fontSize: 40, fontWeight: 800, lineHeight: 1 }}><MarkDisplay earned={d.totals.total} upper={d.totals.total_upper} max={d.totals.total_max} squares={false} /></div> : <div className="tertiary" style={{ fontSize: 24 }}>—</div>}
            <div style={{ marginTop: 8 }}><StatusPill status={d.status} needsYou={needsYou} /></div>
          </div>
        </div>
        {inProgress && <Notice kind="ok">Marking… {d.job?.started_at ? `started ${elapsed(d.job.started_at)} ago` : "waiting for the worker"}. This page updates by itself.</Notice>}
        {d.status === "failed" && (
          <Notice>
            <strong>Marking failed.</strong> {d.job?.error ?? "Unknown error"}<div style={{ marginTop: 8 }}><Button size="sm" onClick={retry}>Retry</Button> <Link to="/settings" className="btn btn-ghost btn-sm">Check settings</Link></div>
          </Notice>
        )}
        {needsYou.length > 0 && (
          <Notice><TriangleAlert size={16} aria-hidden /> {needsYou.length} question{needsYou.length > 1 ? "s" : ""} need{needsYou.length > 1 ? "" : "s"} you: {needsYou.map(qLabel).join(", ")}. <Link to="/review">Open the review queue</Link></Notice>
        )}
      </div>
      <div className="cols" style={{ borderTop: "2px solid var(--color-divider)" }}>
        <section>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h4 style={{ margin: 0 }}>Pages</h4>
            <PagePager count={d.pages.length} current={page} onSelect={setPage} />
          </div>
          {d.pages[page] && <div className="page-view"><img className="grayscale" src={`/api/pages/${d.pages[page].id}`} alt={`Page ${page + 1}`} /></div>}
        </section>
        <section>
          <h4>Marks by question</h4>
          {d.marks.length === 0 && <p className="muted">{inProgress ? "Marks appear here when marking finishes." : "No questions were found on these pages."}</p>}
          {d.marks.map((m) => {
            const scores = m.teacher_scores ?? m.criterion_scores;
            const total = scores.reduce((s, x) => s + x, 0);
            return (
              <div className="qrow" key={m.q_id} style={{ display: "block" }}>
                <button type="button" aria-expanded={open === m.q_id} onClick={() => setOpen(open === m.q_id ? null : m.q_id)}>
                  <span><strong>{qLabel(m.q_id)}</strong> {m.escalated && <span className="pill pill-amber" style={{ marginLeft: 8 }}><TriangleAlert size={12} aria-hidden /> Needs you</span>}{m.teacher_scores && <span className="help" style={{ marginLeft: 8 }}>your mark</span>}</span>
                  <MarkDisplay earned={total} max={perQMax} upper={m.escalated && !m.teacher_scores ? perQMax : undefined} />
                </button>
                {open === m.q_id && (
                  <div className="qrow-body">
                    <CriteriaReading defs={d.rubric.criterion_defs} scores={scores} />
                    {m.evidence && <div className="callout"><span className="label-caps">Evidence</span><div>“{m.evidence}”</div></div>}
                    {m.rationale && <p className="help">{m.rationale}</p>}
                    <p className="help">Confidence {m.confidence === null ? "—" : Math.round(m.confidence * 100) + "%"}{m.reason && ` · ${m.reason}`}</p>
                    {m.queue_id && <Link to={`/review?item=${m.queue_id}`} className="btn btn-ghost btn-sm">Resolve in the review queue →</Link>}
                  </div>
                )}
              </div>
            );
          })}
          {d.feedback && (
            <div style={{ marginTop: 32 }}>
              <hr className="rule-2" />
              <h4 style={{ marginTop: 16 }}>Feedback report</h4>
              <p>{d.feedback.summary}</p>
              <h6>What you did well</h6><ul>{d.feedback.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
              <h6>Question by question</h6>
              {d.feedback.per_question_comments.map((c) => <p key={c.q_id}><strong style={{ display: "inline-block", width: 96 }}>{qLabel(c.q_id)}</strong>{c.comment} <em>Try next: {c.suggested_action}</em></p>)}
              <h6>Work on next</h6><ul>{d.feedback.improvement_plan.map((s, i) => <li key={i}>{s}</li>)}</ul>
              <h6>Next steps</h6><ol>{d.feedback.next_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
            </div>
          )}
        </section>
      </div>
      <span hidden>{tick}</span>
    </div>
  );
}
```

- [ ] **Step 2: Verify in the browser**

With a real key (TokenRouter free) configured, mark a real script (a photographed maths page or `docs/design-handoff` isn't a script — use any handwritten sample PDF): the detail page shows the calm "Marking… started 0:12 ago" state, then marks per question with expandable evidence, escalated rows carry the amber pill and the link to review, and the feedback report renders. Without a key, the failed state shows the error and Retry works. Compare against `T9-student-detail.png`.

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/SubmissionDetail.tsx
git commit -m "feat(web): submission detail with pages, marks, escalations and feedback

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 18: Review queue and Learning pages

**Files:**
- Modify: `web/src/pages/Review.tsx`, `web/src/pages/Learning.tsx`

**Interfaces:**
- Consumes: `GET /api/queue`, `POST /api/queue/{id}/resolve`, `GET /api/notes|exemplars|stats`, `POST /api/notes|exemplars/{id}/approve`; `useOutletContext().refreshQueue()`.

- [ ] **Step 1: Review queue (T7)**

`web/src/pages/Review.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { QueueItem } from "../api/types";
import { Button } from "../components/Button";
import { CriteriaReview } from "../components/CriteriaTable";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { PagePager } from "../components/PagePager";
import { qLabel } from "../lib/marks";

export function Review() {
  const { refreshQueue } = useOutletContext<{ refreshQueue: () => void }>();
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [i, setI] = useState(0);
  const [values, setValues] = useState<(number | "")[]>([]);
  const [reason, setReason] = useState("");
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [params] = useSearchParams();

  const load = useCallback(async () => {
    const list = await api.get<QueueItem[]>("/api/queue");
    setItems(list);
    const want = Number(params.get("item"));
    const idx = want ? Math.max(0, list.findIndex((x) => x.id === want)) : 0;
    setI(Math.min(idx, Math.max(0, list.length - 1)));
  }, [params]);
  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  const item = items?.[i];
  useEffect(() => { if (item) { setValues(item.criterion_defs.map(() => "")); setReason(""); setPage(0); } }, [item?.id]);

  const complete = useMemo(() => values.length > 0 && values.every((v) => v !== ""), [values]);
  const acceptProposed = () => item && setValues(item.proposed_criterion_scores.map((v) => v));

  const save = async () => {
    if (!item || !complete) return;
    setBusy(true); setError(null);
    try {
      await api.post(`/api/queue/${item.id}/resolve`, { criterion_scores: values as number[], reason });
      const rest = items!.filter((x) => x.id !== item.id);
      setItems(rest); setI(Math.min(i, Math.max(0, rest.length - 1)));
      refreshQueue();
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not save"); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "TEXTAREA") return;
      if (e.key === "ArrowLeft") setI((x) => Math.max(0, x - 1));
      else if (e.key === "ArrowRight") setI((x) => Math.min((items?.length ?? 1) - 1, x + 1));
      else if (e.key.toLowerCase() === "a" && tag !== "INPUT") acceptProposed();
      else if (e.key === "Enter" && tag !== "INPUT") { e.preventDefault(); save(); }
      else if (/^[0-9]$/.test(e.key) && tag !== "INPUT" && item) {
        const focusIdx = 0; const max = item.criterion_defs[focusIdx].max_score;
        setValues((v) => v.map((x, j) => (j === focusIdx ? Math.min(max, Number(e.key)) : x)));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (error && !items) return <div className="page"><Notice kind="error">{error}</Notice></div>;
  if (!items) return <div className="page muted">Loading…</div>;
  if (!item) return <div className="page"><EmptyState title="Nothing needs you"><p>Every question has a mark. New escalations appear here as scripts are marked.</p><Link to="/submissions" className="btn btn-secondary">Back to submissions</Link></EmptyState></div>;

  return (
    <div>
      <div className="toolbar">
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <Link to={`/submissions/${item.submission_id}`} className="breadcrumb" style={{ margin: 0 }}>← {item.submission_label}</Link>
          <strong>Needs you</strong><span className="muted">{i + 1} of {items.length}</span>
        </div>
        <div className="help" aria-hidden>
          <span className="key">←</span> <span className="key">→</span> move · <span className="key">A</span> accept · <span className="key">1–9</span> first mark · <span className="key">↵</span> save &amp; next
        </div>
      </div>
      <div className="cols">
        <section>
          <div className="label-caps">Student</div>
          <p style={{ fontSize: 18, fontWeight: 600 }}>{item.submission_label}</p>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><div className="label-caps">Page {page + 1}</div><PagePager count={item.page_ids.length} current={page} onSelect={setPage} /></div>
          {item.page_ids[page] && <div className="page-view" style={{ maxHeight: 420, overflow: "auto" }}><img className="grayscale" src={`/api/pages/${item.page_ids[page]}`} alt={`Page ${page + 1}`} /></div>}
          <div className="label-caps" style={{ marginTop: 16 }}>What we read</div>
          <div className="page-view" style={{ padding: 12, fontSize: 15, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{item.transcription || <span className="tertiary">Nothing legible for this question.</span>}{item.workings && <div className="help" style={{ marginTop: 8 }}>Workings: {item.workings}</div>}</div>
          <div style={{ marginTop: 16 }}><Notice><strong>Why this is here</strong> — {item.reason}.{item.reviewer_note && <> Reviewer: “{item.reviewer_note}”.</>}</Notice></div>
        </section>
        <section>
          <div className="label-caps">Question {qLabel(item.q_id).replace("Q", "")}</div>
          {item.rationale && <p className="help">{item.rationale}</p>}
          <CriteriaReview defs={item.criterion_defs} proposed={item.proposed_criterion_scores} evidence={item.evidence} values={values} onChange={setValues} />
          <div className="field" style={{ marginTop: 16 }}>
            <label htmlFor="reason">Reason (kept with your correction)</label>
            <textarea id="reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Method is correct; arithmetic slip in the last line." />
          </div>
          {error && <Notice kind="error">{error}</Notice>}
          <div className="actions" style={{ marginTop: 16, paddingTop: 16, borderTop: "2px solid var(--color-divider)" }}>
            <Button size="lg" onClick={() => setI(Math.max(0, i - 1))} disabled={i === 0}>← Previous</Button>
            <Button size="lg" onClick={acceptProposed} keyHint="A">Accept proposed</Button>
            <Button size="lg" variant="primary" wide onClick={save} disabled={!complete || busy} keyHint="↵">{busy ? "Saving…" : "Save & next"}</Button>
          </div>
        </section>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Learning page**

`web/src/pages/Learning.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Exemplar, Note, Stats } from "../api/types";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";

export function Learning() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [ex, setEx] = useState<Exemplar[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const load = () => Promise.all([api.get<Note[]>("/api/notes"), api.get<Exemplar[]>("/api/exemplars"), api.get<Stats>("/api/stats")]).then(([n, e, s]) => { setNotes(n); setEx(e); setStats(s); });
  useEffect(() => { load(); }, []);
  const approveNote = async (id: number) => { await api.post(`/api/notes/${id}/approve`); load(); };
  const approveEx = async (id: number) => { await api.post(`/api/exemplars/${id}/approve`); load(); };
  return (
    <div className="page">
      <div className="page-header"><div><h1>Learning</h1><p className="meta">What the marker has learned from your corrections. Approve a draft to use it on the next run.</p></div></div>
      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", borderTop: "2px solid var(--color-divider)", borderBottom: "2px solid var(--color-divider)", marginBottom: 32 }}>
          {Object.entries(stats).map(([role, s]) => (
            <div key={role} style={{ padding: "18px 20px 16px", borderRight: "1px solid var(--color-divider)" }}>
              <div style={{ fontSize: 36, fontWeight: 800, lineHeight: 1 }}>{s.count}</div>
              <div className="muted">{role} runs · {s.count ? `${Math.round(s.mean_latency_ms / 1000)} s avg` : "—"}</div>
            </div>
          ))}
        </div>
      )}
      <h4>Rubric notes</h4>
      {notes.length === 0 ? <EmptyState title="No notes yet"><p>Run <code>sms reflect</code> after resolving a few questions to distil notes from your corrections.</p></EmptyState> : (
        <table className="table"><thead><tr><th>Subject</th><th>Note</th><th>Status</th><th /></tr></thead>
          <tbody>{notes.map((n) => <tr key={n.id}><td>{n.subject}</td><td>{n.note}</td><td><span className={`pill ${n.status === "active" ? "pill-ink" : "pill-outline"}`}>{n.status === "active" ? "Active" : "Draft"}</span></td><td>{n.status !== "active" && <Button size="sm" onClick={() => approveNote(n.id)}>Approve</Button>}</td></tr>)}</tbody></table>
      )}
      <h4 style={{ marginTop: 32 }}>Exemplar cases</h4>
      {ex.length === 0 ? <p className="muted">None yet.</p> : (
        <table className="table"><thead><tr><th>Topic</th><th>Answer</th><th className="num">Marks</th><th>Why it matters</th><th>Status</th><th /></tr></thead>
          <tbody>{ex.map((e) => <tr key={e.id}><td>{e.subject} / {e.topic}</td><td>{e.answer_text}</td><td className="num">{e.awarded} / {e.max_score}</td><td className="help">{e.why_it_matters}</td><td><span className={`pill ${e.status === "active" ? "pill-ink" : "pill-outline"}`}>{e.status === "active" ? "Active" : "Draft"}</span></td><td>{e.status !== "active" && <Button size="sm" onClick={() => approveEx(e.id)}>Approve</Button>}</td></tr>)}</tbody></table>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify in the browser**

Build, restart. Create an escalation (either a real low-confidence mark, or set `confidence_threshold` to 1.0 in Settings so every question escalates, then mark a script). `/review` shows the two-column card matching `T7-review-queue.png`: page with pager, transcription, "Why this is here", criteria table with proposed marks and inputs, reason textarea, footer buttons with key badges. Keys: `A` fills proposed, `Enter` saves and advances, `←/→` move. The nav "Review" badge decrements; the submission flips to Done when the last question is resolved. `/learning` renders the stats strip and the empty states.

- [ ] **Step 4: Frontend tests + type check, then commit**

```bash
cd web && npx vitest run && npx tsc --noEmit
git add web/src/pages/Review.tsx web/src/pages/Learning.tsx
git commit -m "feat(web): review queue with keyboard flow, learning page

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 19: Dockerfile, Railway config, README

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `railway.json`
- Modify: `README.md`, `.gitignore`

- [ ] **Step 1: Dockerfile**

`Dockerfile`:

```dockerfile
# --- stage 1: build the SPA ---
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- stage 2: python runtime ---
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    STORAGE_DIR=/data SMS_STATIC_DIR=/app/web/dist
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY --from=web /web/dist ./web/dist
RUN mkdir -p /data
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync sms serve --host 0.0.0.0 --port ${PORT:-8000}"]
```

(`sms serve` constructs `Database`, which runs `alembic upgrade head` before uvicorn starts — no separate migrate step needed.)

`.dockerignore`:

```
.git
.venv
.pytest_cache
__pycache__
*.db
data/
web/node_modules
web/dist
docs/
tests/
```

`railway.json`:

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 120,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5
  }
}
```

Add to `.gitignore`: `data/`, `*.db-wal`, `*.db-shm`, `web/node_modules`, `web/dist`.

- [ ] **Step 2: Build and run the container locally**

```bash
docker build -t sms:local .
docker run --rm -p 8020:8000 -e SECRET_KEY=dev -e TEACHER_PASSWORD=dev -e DATABASE_URL=sqlite:////data/sms.db sms:local &
sleep 8; curl -s localhost:8020/api/health; curl -s -o /dev/null -w "%{http_code}\n" localhost:8020/
```

Expected: health JSON with `"db":"ok"`, and `200` for the SPA. Stop the container. If Docker isn't available locally, skip this step and rely on the Railway build in Task 20 — say so in the task report.

- [ ] **Step 3: README**

Replace the "Quickstart" section's intro and add two sections after it:

```markdown
## Web app

Smart Marking is also a web app: sign in with a shared teacher password, pick an LLM provider
(TokenRouter, OpenRouter, OpenAI, Anthropic, Moonshot/Kimi, Qwen) and enter its API key under
**Settings**, upload a script's pages (PDF, JPG, PNG or HEIC) under **Mark a script**, and resolve the
questions the AI was unsure about under **Review**. The default provider is TokenRouter's free
`z-ai/glm-5.3-free` (8 requests/min — about 30 s per script).

### Run locally

```sh
uv sync
(cd web && npm ci && npm run build)
SECRET_KEY=dev TEACHER_PASSWORD=dev uv run sms serve
# open http://localhost:8000 — uses ./sms.db (SQLite) and ./data for page images
```

Frontend development with hot reload: `cd web && npm run dev` (proxies `/api` to :8000).

### Deploy on Railway

One service (this repo, Dockerfile) + a Postgres database + a volume mounted at `/data`.

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `SECRET_KEY` | a long random string — signs sessions and encrypts stored API keys (changing it invalidates both) |
| `TEACHER_PASSWORD` | the password teachers use to sign in |
| `STORAGE_DIR` | `/data` |
| `LLM_PROVIDER` | optional — `tokenrouter` (default), `openrouter`, `openai`, `anthropic`, `moonshot`, `qwen` |
| `LLM_MODEL` | optional — defaults to the provider's default model |
| `LLM_API_KEY` | optional — pre-seeds the key so the settings page can be skipped |

Health check: `/api/health`. The marking worker runs inside the web service; to run it separately,
add a second service from the same repo with start command `uv run --no-sync sms worker` and set
`SMS_EMBEDDED_WORKER=0` on the web service.
```

Update the CLI table with `sms serve` and `sms worker`, and the `--provider/--api-key` flags on `mark`/`reflect`. Update "Status / roadmap": FastAPI service is done; slices 2–4 listed.

- [ ] **Step 4: Full verification**

```bash
uv run pytest -q && (cd web && npx vitest run && npx tsc --noEmit && npm run build)
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore railway.json README.md .gitignore
git commit -m "feat: Dockerfile, Railway config and deployment docs

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 20: Deploy to Railway and verify live

**Files:** none (operational). Uses the Railway MCP tools (`mcp__be51efe6-…__create-project`, `create-service`, `create-volume`, `set-variables`, `create-deployment`, `get-logs`, `generate-domain`, `list-deployments`).

- [ ] **Step 1: Push the branch**

Confirm the remote and push `master` (or the feature branch) so Railway can build from GitHub. If there is no remote, ask the owner which GitHub repo to push to before continuing.

- [ ] **Step 2: Create the Railway project**

Via the Railway MCP: create project `smart-marking`; add a Postgres database service; add the web service from the GitHub repo (root directory `/`, Dockerfile builder); create a volume mounted at `/data` on the web service; set variables on the web service: `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `SECRET_KEY=<generate: python -c "import secrets;print(secrets.token_urlsafe(32))">`, `TEACHER_PASSWORD=<ask the owner>`, `STORAGE_DIR=/data`, `LLM_PROVIDER=tokenrouter`, `LLM_MODEL=z-ai/glm-5.3-free`; generate a public domain.

- [ ] **Step 3: Verify the deployment**

- `get-logs` shows `alembic` applying `0001` and `0002`, uvicorn listening, and `sms.worker` heartbeat with no tracebacks.
- `curl https://<domain>/api/health` → `{"db":"ok","worker_last_seen":"…"}`.
- Open the domain in the in-app browser: sign in, Settings → enter the owner's TokenRouter key → **Test connection** shows Text ✓ / Vision ✓ (if Vision ✗, record the exact error; that is the go/no-go for the free default and must be reported, not hidden) → Save.
- Mark a real script (a photo of a handwritten maths answer + a 2-criterion rubric): watch the status go Waiting → Marking → Done/Needs you; open the detail; if escalated, resolve it in Review.
- Run the opt-in live test locally against the same key: `SMS_LIVE_TESTS=1 TOKENROUTER_API_KEY=… uv run pytest tests/live -q`.

- [ ] **Step 4: Report**

Tell the owner: the live URL, which variables are set, the probe results for GLM-5.3-free (text + vision latencies), the time one script took at 8 RPM, and the exact steps to publish the project as a template from the Railway dashboard (Project → Settings → "Create template", tick the web service, Postgres and the volume, mark `TEACHER_PASSWORD` as required and `SECRET_KEY` as generated).

---

## Self-review

**Spec coverage**

| Spec section | Tasks |
|---|---|
| 1 Provider layer (registry, client, settings, probe, rate limit/retry) | 3, 4, 5, 6 |
| 2 Data model & storage (SQLAlchemy, Alembic 0001/0002, files) | 1, 2, 7 |
| 3 HTTP API (auth, settings, submissions, pages, queue, learning, health) | 9, 10, 11, 12 |
| 4 Worker & jobs | 8, 9 (lifespan), 13 (`sms worker`) |
| 5 Frontend (7 screens, shared components, tokens) | 14–18 |
| 6 Railway & local dev (Dockerfile, railway.json, template vars, README) | 19, 20 |
| 7 Testing (unit, API, frontend, live) | every task; live in 6 and 20 |
| Base URL override (added after Qwen's workspace-URL change) | 2 (`settings.base_url`), 3, 4, 10, 15 |

**Known deviations from the spec, deliberate:** `settings.base_url` column added (spec §1 table lacks it); `ProviderSpec.api_params` + `model_api_parameters` on the agent factories (Anthropic requires `max_tokens`); Anthropic default is `claude-opus-5` (spec said "current Claude Sonnet" — the claude-api reference makes Opus 5 the default); the rubric criteria table has no "Q" column (see "Rubric note" above).

**Placeholder scan:** no TBD/TODO; every code step has code; `Review` keyboard "1–9" sets the first criterion's mark (spec said "1–5 set focused criterion" — first criterion is the deterministic choice without focus tracking; noted in the toolbar legend).

**Type consistency:** `Database.insert` used with `RETURNING id` throughout; `JobStore.enqueue(kind, submission_id)`, `claim()`, `finish`, `retry_later(job_id, delay_s, error)`, `fail`, `reset_running`, `heartbeat`, `last_heartbeat`, `job_for_submission` match between Task 8 and Tasks 9/11/12/13; `probe(provider, model, api_key, extractor_model=None, base_url=None, client_factory=…)` matches Task 10's call; `ProbeResult.to_dict()` shape matches `types.ts`; `SubmissionDetail` JSON keys match `types.ts` (`totals`, `marks[].teacher_scores`, `job`); `QueueItem` keys match `list_queue`.

# Classes, classlists, student hand-in and feedback (slice 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teachers create classes with a CSV classlist, set bank assignments to a class, and release feedback; students hand in from their phone with a class code + register number and read their feedback.

**Architecture:** Three new tables (`classes`, `students`, `class_assignments`) and four nullable columns on `submissions` link a hand-in to a class assignment and a student; the existing worker, review queue, records and page-deletion code run unchanged. A second signed cookie (`sms_student`) scopes `/api/student/*` to one student. The SPA gains a teacher `Classes` area and a phone-first student area under `/c/:code`, `/join`, `/s/*`.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy Core (`Database` with `:name` params), Alembic migrations (`src/sms/migrations/versions/`), itsdangerous, pytest; React 18 + TypeScript + Vite + react-router 6 + vitest/testing-library, plain CSS (`web/src/styles/tokens.css` + `app.css`).

**Spec:** `docs/superpowers/specs/2026-09-16-classes-and-student-hand-in-design.md`

## Global Constraints

- Class code alphabet is exactly `23456789ABCDEFGHJKMNPQRSTUVWXYZ`, 4 characters, compared upper-cased.
- Student ID text form is `CODE-reg_no` (e.g. `CE4R-12`).
- Student cookie name is `sms_student`; teacher cookie stays `sms_session`. Student routes never accept the teacher cookie and vice versa.
- Student-facing copy never contains the words "escalation", "confidence" or "reviewer"; marks are always text (`3 / 5`).
- Error responses keep the shape `{"error": {"code", "message"}}` via `ApiError(status, code, message)`.
- Timestamps in API responses go through `sms.timeutil.iso_utc`.
- Before every commit: `uv run pytest -q` (no warnings summary) and, for frontend tasks, `cd web && npx vitest run && npx tsc --noEmit && npm run build`.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Never dispatch subagents from a task; never push.

## File structure

| File | Responsibility |
|---|---|
| `src/sms/migrations/versions/0007_classes.py` | tables + submissions columns + partial unique index |
| `src/sms/web/services/classes.py` | class code generator; class CRUD/archive/regenerate |
| `src/sms/web/services/classlist.py` | CSV parsing; classlist replace; student listing |
| `src/sms/web/services/class_assignments.py` | set/list/get/edit/delete class assignments; hand-in + remove; roster + counts; release; marks CSV |
| `src/sms/web/services/student.py` | student lookup, session payload, student-facing assignment/feedback views |
| `src/sms/web/routers/classes.py` | `/api/classes` (classes + students) |
| `src/sms/web/routers/class_assignments.py` | `/api/classes/{class_id}/assignments/...` |
| `src/sms/web/routers/student.py` | `/api/student/...` |
| `src/sms/web/deps.py` | `SessionSigner.issue_student/verify_student`, `STUDENT_COOKIE`, `require_student` |
| `src/sms/web/services/submissions.py` | `create_submission` gains class/student kwargs; `submission_totals` helper; list gains `class_label` |
| `src/sms/web/services/assignments.py` | delete guard counts class assignments |
| `web/src/api/types.ts` | new types |
| `web/src/pages/Classes.tsx`, `ClassPage.tsx`, `ClassAssignmentPage.tsx` | teacher pages |
| `web/src/components/ClasslistImport.tsx`, `ProgressStrip.tsx` | teacher components |
| `web/src/student/StudentLayout.tsx`, `Enter.tsx`, `Confirm.tsx`, `Home.tsx`, `HandIn.tsx`, `AssignmentView.tsx` | student pages |
| `web/src/lib/image.ts` | client-side downscale |
| `web/src/styles/app.css` | `.strip`, `.student-*` rules |

---

### Task 1: Migration 0007 and the classes service/router

**Files:**
- Create: `src/sms/migrations/versions/0007_classes.py`, `src/sms/web/services/classes.py`, `src/sms/web/routers/classes.py`
- Modify: `src/sms/web/app.py` (include router)
- Test: `tests/unit/test_class_code.py`, `tests/web/test_classes_api.py`

**Interfaces:**
- Produces: `CODE_ALPHABET`, `new_code() -> str`, `normalise_code(s) -> str`, `unique_code(db) -> str`, `list_classes(db) -> List[dict]`, `get_class(db, class_id) -> Optional[dict]`, `create_class(db, name) -> dict`, `rename_class(db, class_id, name) -> dict`, `set_archived(db, class_id, archived: bool) -> dict`, `regenerate_code(db, class_id) -> dict`. Class dict keys: `id, name, code, student_count, open_assignments, archived_at, created_at, updated_at`.
- Router object `router` in `routers/classes.py` with prefix `/api/classes` and `dependencies=[Depends(require_teacher)]` — Task 2 adds routes to the same file.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_class_code.py`:
```python
from sms.memory.db import Database
from sms.web.services.classes import CODE_ALPHABET, new_code, normalise_code, unique_code


def test_alphabet_has_no_ambiguous_glyphs():
    assert set("0O1IL").isdisjoint(CODE_ALPHABET) and len(CODE_ALPHABET) == 31


def test_new_code_is_four_chars_from_the_alphabet():
    for _ in range(200):
        c = new_code()
        assert len(c) == 4 and all(ch in CODE_ALPHABET for ch in c)


def test_normalise_code_uppercases_and_strips():
    assert normalise_code(" ce4r ") == "CE4R" and normalise_code(None) == ""


def test_unique_code_retries_on_collision(tmp_path, monkeypatch):
    db = Database(path=str(tmp_path / "c.db"))
    db.execute("INSERT INTO classes (name, code) VALUES ('4E2', 'AAAA')")
    codes = iter(["AAAA", "BBBB"])
    monkeypatch.setattr("sms.web.services.classes.new_code", lambda: next(codes))
    assert unique_code(db) == "BBBB"
```

`tests/web/test_classes_api.py`:
```python
def test_requires_auth(client):
    assert client.get("/api/classes").status_code == 401


def test_create_list_rename_archive_regenerate(auth):
    r = auth.post("/api/classes", json={"name": "4E2 Mathematics"})
    assert r.status_code == 201
    c = r.json()
    assert c["name"] == "4E2 Mathematics" and len(c["code"]) == 4 and c["student_count"] == 0 and c["open_assignments"] == 0
    assert c["archived_at"] is None
    assert auth.post("/api/classes", json={"name": "  "}).json()["error"]["code"] == "bad_name"
    assert [x["id"] for x in auth.get("/api/classes").json()] == [c["id"]]
    assert auth.get(f"/api/classes/{c['id']}").json()["code"] == c["code"]
    assert auth.get("/api/classes/999").status_code == 404
    assert auth.put(f"/api/classes/{c['id']}", json={"name": "4E2 Maths"}).json()["name"] == "4E2 Maths"
    old = c["code"]
    new = auth.post(f"/api/classes/{c['id']}/regenerate-code").json()["code"]
    assert new != old and len(new) == 4
    archived = auth.post(f"/api/classes/{c['id']}/archive").json()
    assert archived["archived_at"] is not None
    # archived classes list last
    d = auth.post("/api/classes", json={"name": "3N1 Science"}).json()
    assert [x["id"] for x in auth.get("/api/classes").json()] == [d["id"], c["id"]]
    assert auth.post(f"/api/classes/{c['id']}/unarchive").json()["archived_at"] is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_class_code.py tests/web/test_classes_api.py -q`
Expected: FAIL — `ModuleNotFoundError: sms.web.services.classes` / 404s.

- [ ] **Step 3: Write the migration**

`src/sms/migrations/versions/0007_classes.py`:
```python
"""classes, students, class assignments; submissions linked to a class assignment and a student

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        # 4 chars from 23456789ABCDEFGHJKMNPQRSTUVWXYZ; the student link is /c/<code>
        sa.Column("code", sa.Text, nullable=False, unique=True),
        sa.Column("archived_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "students",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("class_id", sa.Integer, sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reg_no", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("last_seen_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("class_id", "reg_no", name="uq_students_class_reg"),
    )
    op.create_table(
        "class_assignments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("class_id", sa.Integer, sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        # the bank template; deliberately not a FK so a forced template delete leaves the row (see delete guard)
        sa.Column("template_id", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("due_at", sa.DateTime),
        # draft (invisible to students) -> open (hand-in allowed) -> released (feedback visible)
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("allow_student_uploads", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("released_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    with op.batch_alter_table("submissions") as b:
        b.add_column(sa.Column("class_assignment_id", sa.Integer))
        b.add_column(sa.Column("student_id", sa.Integer))
        b.add_column(sa.Column("handed_in_at", sa.DateTime))
        b.add_column(sa.Column("source", sa.Text, nullable=False, server_default="teacher"))
    # one hand-in per student per class assignment; hand_in relies on this under concurrent taps
    op.create_index("uq_submissions_student_assignment", "submissions", ["class_assignment_id", "student_id"], unique=True,
                    postgresql_where=sa.text("class_assignment_id IS NOT NULL AND student_id IS NOT NULL"),
                    sqlite_where=sa.text("class_assignment_id IS NOT NULL AND student_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("uq_submissions_student_assignment", table_name="submissions")
    with op.batch_alter_table("submissions") as b:
        b.drop_column("source")
        b.drop_column("handed_in_at")
        b.drop_column("student_id")
        b.drop_column("class_assignment_id")
    op.drop_table("class_assignments")
    op.drop_table("students")
    op.drop_table("classes")
```

- [ ] **Step 4: Write the service**

`src/sms/web/services/classes.py`:
```python
"""Classes: a name, a 4-character code students type, and a classlist (see classlist.py)."""
import secrets
from typing import Any, Dict, List, Optional

from sms.memory.db import Database
from sms.timeutil import iso_utc
from sms.web.errors import ApiError

# No 0/O, 1/I/L — the code is read off a projector and typed on a phone.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 4


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalise_code(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def unique_code(db: Database) -> str:
    for _ in range(50):
        code = new_code()
        if not db.query("SELECT 1 FROM classes WHERE code = :c", {"c": code}):
            return code
    raise RuntimeError("could not find an unused class code")


_SELECT = ("SELECT c.*, (SELECT COUNT(*) FROM students s WHERE s.class_id = c.id) AS student_count, "
           "(SELECT COUNT(*) FROM class_assignments a WHERE a.class_id = c.id AND a.status = 'open') AS open_assignments "
           "FROM classes c")


def _row(r: dict) -> Dict[str, Any]:
    return {
        "id": r["id"], "name": r["name"], "code": r["code"],
        "student_count": int(r["student_count"] or 0), "open_assignments": int(r["open_assignments"] or 0),
        "archived_at": iso_utc(r["archived_at"]),
        "created_at": iso_utc(r["created_at"]), "updated_at": iso_utc(r["updated_at"]),
    }


def list_classes(db: Database) -> List[Dict[str, Any]]:
    rows = db.query(_SELECT + " ORDER BY (c.archived_at IS NOT NULL), c.name, c.id")
    return [_row(r) for r in rows]


def get_class(db: Database, class_id: int) -> Optional[Dict[str, Any]]:
    rows = db.query(_SELECT + " WHERE c.id = :id", {"id": class_id})
    return _row(rows[0]) if rows else None


def _require(db: Database, class_id: int) -> Dict[str, Any]:
    c = get_class(db, class_id)
    if c is None:
        raise ApiError(404, "not_found", "No such class")
    return c


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ApiError(400, "bad_name", "Give the class a name")
    return name[:120]


def create_class(db: Database, name: str) -> Dict[str, Any]:
    cid = db.insert("INSERT INTO classes (name, code) VALUES (:n, :c) RETURNING id",
                    {"n": _clean_name(name), "c": unique_code(db)})
    return get_class(db, cid)  # type: ignore[return-value]


def rename_class(db: Database, class_id: int, name: str) -> Dict[str, Any]:
    _require(db, class_id)
    db.execute("UPDATE classes SET name = :n, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
               {"n": _clean_name(name), "id": class_id})
    return get_class(db, class_id)  # type: ignore[return-value]


def set_archived(db: Database, class_id: int, archived: bool) -> Dict[str, Any]:
    _require(db, class_id)
    if archived:
        db.execute("UPDATE classes SET archived_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                   {"id": class_id})
    else:
        db.execute("UPDATE classes SET archived_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = :id", {"id": class_id})
    return get_class(db, class_id)  # type: ignore[return-value]


def regenerate_code(db: Database, class_id: int) -> Dict[str, Any]:
    """New code: the old link stops working; student sessions (which hold ids) keep working."""
    _require(db, class_id)
    db.execute("UPDATE classes SET code = :c, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
               {"c": unique_code(db), "id": class_id})
    return get_class(db, class_id)  # type: ignore[return-value]
```

- [ ] **Step 5: Write the router and register it**

`src/sms/web/routers/classes.py`:
```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sms.web.deps import get_db, require_teacher
from sms.web.errors import ApiError
from sms.web.services.classes import (create_class, get_class, list_classes, regenerate_code, rename_class,
                                      set_archived)

router = APIRouter(prefix="/api/classes", tags=["classes"], dependencies=[Depends(require_teacher)])


class ClassBody(BaseModel):
    name: str


@router.get("")
def index(db=Depends(get_db)):
    return list_classes(db)


@router.post("", status_code=201)
def create(body: ClassBody, db=Depends(get_db)):
    return create_class(db, body.name)


@router.get("/{class_id}")
def show(class_id: int, db=Depends(get_db)):
    c = get_class(db, class_id)
    if c is None:
        raise ApiError(404, "not_found", "No such class")
    return c


@router.put("/{class_id}")
def rename(class_id: int, body: ClassBody, db=Depends(get_db)):
    return rename_class(db, class_id, body.name)


@router.post("/{class_id}/archive")
def archive(class_id: int, db=Depends(get_db)):
    return set_archived(db, class_id, True)


@router.post("/{class_id}/unarchive")
def unarchive(class_id: int, db=Depends(get_db)):
    return set_archived(db, class_id, False)


@router.post("/{class_id}/regenerate-code")
def regenerate(class_id: int, db=Depends(get_db)):
    return regenerate_code(db, class_id)
```

In `src/sms/web/app.py` add `classes` to the routers import and `app.include_router(classes.router)` after `assignments.router`.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/unit/test_class_code.py tests/web/test_classes_api.py -q` → PASS. Then `uv run pytest -q` → all pass.

- [ ] **Step 7: Commit**

```bash
git add src/sms/migrations/versions/0007_classes.py src/sms/web/services/classes.py src/sms/web/routers/classes.py src/sms/web/app.py tests/unit/test_class_code.py tests/web/test_classes_api.py
git commit -m "feat(classes): classes table, 4-char codes, CRUD/archive/regenerate API"
```

---

### Task 2: Classlist CSV — parse, preview, replace, list

**Files:**
- Create: `src/sms/web/services/classlist.py`
- Modify: `src/sms/web/routers/classes.py`
- Test: `tests/unit/test_classlist.py`, `tests/web/test_classes_api.py`

**Interfaces:**
- Produces: `parse_classlist(data: bytes) -> Tuple[List[dict], List[str]]` (rows `{reg_no: int|None, raw_reg_no: str, name: str, issues: List[str]}`, file-level errors); `replace_classlist(db, class_id, rows: List[dict]) -> dict` (`{"students": [...], "kept": [reg_no...]}`); `list_students(db, class_id) -> List[dict]` with keys `id, reg_no, name, submissions, last_seen_at`.
- Routes: `POST /api/classes/{id}/students/preview` (multipart `file`), `PUT /api/classes/{id}/students {rows}`, `GET /api/classes/{id}/students`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_classlist.py`:
```python
from sms.web.services.classlist import parse_classlist


def test_header_variants_and_bom():
    rows, errors = parse_classlist("﻿Reg No,Name\r\n1,Tan Wei Ling\r\n2,Muhammad Danish\r\n".encode())
    assert errors == []
    assert [(r["reg_no"], r["name"], r["issues"]) for r in rows] == [(1, "Tan Wei Ling", []), (2, "Muhammad Danish", [])]


def test_missing_columns_is_a_file_error():
    rows, errors = parse_classlist(b"student,index\nA,1\n")
    assert rows == [] and errors == ["The first row must have the columns name and reg_no"]


def test_row_issues_are_flagged_inline():
    data = b"name,reg_no\nTan,1\n,2\nLim,x\nOng,1\n\n"
    rows, errors = parse_classlist(data)
    assert errors == []
    assert [r["issues"] for r in rows] == [["duplicate_reg_no"], ["missing_name"], ["bad_reg_no"], ["duplicate_reg_no"]]
    assert rows[2]["raw_reg_no"] == "x" and rows[2]["reg_no"] is None


def test_empty_file():
    assert parse_classlist(b"") == ([], ["The file is empty"])
```

Append to `tests/web/test_classes_api.py`:
```python
CSV = b"name,reg_no\nTan Wei Ling,1\nMuhammad Danish,2\nPriya Nair,3\n"


def _class(auth, name="4E2"):
    return auth.post("/api/classes", json={"name": name}).json()


def test_classlist_preview_confirm_and_list(auth):
    c = _class(auth)
    p = auth.post(f"/api/classes/{c['id']}/students/preview", files=[("file", ("list.csv", CSV, "text/csv"))]).json()
    assert p["errors"] == [] and [r["name"] for r in p["rows"]] == ["Tan Wei Ling", "Muhammad Danish", "Priya Nair"]
    assert auth.get(f"/api/classes/{c['id']}/students").json() == []   # preview saves nothing
    r = auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": x["reg_no"], "name": x["name"]} for x in p["rows"]]})
    assert r.status_code == 200 and r.json()["kept"] == []
    students = auth.get(f"/api/classes/{c['id']}/students").json()
    assert [(s["reg_no"], s["name"], s["submissions"], s["last_seen_at"]) for s in students] == \
        [(1, "Tan Wei Ling", 0, None), (2, "Muhammad Danish", 0, None), (3, "Priya Nair", 0, None)]
    assert auth.get(f"/api/classes/{c['id']}").json()["student_count"] == 3


def test_classlist_rejects_rows_with_issues(auth):
    c = _class(auth)
    r = auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 1, "name": "Tan"}, {"reg_no": 1, "name": "Lim"}]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_rows"
    r = auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 0, "name": "Tan"}]})
    assert r.json()["error"]["code"] == "bad_rows"
    r = auth.put(f"/api/classes/{c['id']}/students", json={"rows": []})
    assert r.json()["error"]["code"] == "bad_rows"


def test_replace_classlist_keeps_students_with_submissions(auth, app):
    c = _class(auth)
    auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 1, "name": "Tan"}, {"reg_no": 2, "name": "Lim"}]})
    tan = auth.get(f"/api/classes/{c['id']}/students").json()[0]
    app.state.db.execute("INSERT INTO submissions (label, subject, context, rubric_json, status, student_id) "
                         "VALUES ('#1 Tan', 'math', '', '{}', 'done', :s)", {"s": tan["id"]})
    r = auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": 2, "name": "Lim J H"}, {"reg_no": 3, "name": "Ong"}]}).json()
    assert r["kept"] == [1]
    assert [(s["reg_no"], s["name"], s["submissions"]) for s in r["students"]] == [(1, "Tan", 1), (2, "Lim J H", 0), (3, "Ong", 0)]


def test_preview_reports_file_errors(auth):
    c = _class(auth)
    p = auth.post(f"/api/classes/{c['id']}/students/preview", files=[("file", ("list.csv", b"a,b\n1,2\n", "text/csv"))]).json()
    assert p["rows"] == [] and p["errors"] == ["The first row must have the columns name and reg_no"]
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/unit/test_classlist.py tests/web/test_classes_api.py -q` → FAIL (import error / 404).

- [ ] **Step 3: Write the service**

`src/sms/web/services/classlist.py`:
```python
"""The classlist CSV: two columns, name and reg_no, in any order; header names are matched loosely."""
import csv
import io
import re
from typing import Any, Dict, List, Optional, Tuple

from sms.memory.db import Database
from sms.timeutil import iso_utc
from sms.web.errors import ApiError

_HEADERS = {
    "name": "name", "studentname": "name", "student": "name", "fullname": "name",
    "regno": "reg_no", "registerno": "reg_no", "registernumber": "reg_no", "regnumber": "reg_no",
    "no": "reg_no", "number": "reg_no", "index": "reg_no", "indexno": "reg_no", "id": "reg_no",
}
HEADER_ERROR = "The first row must have the columns name and reg_no"


def _norm_header(h: str) -> Optional[str]:
    return _HEADERS.get(re.sub(r"[^a-z]", "", (h or "").lower()))


def parse_classlist(data: bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Rows with per-row `issues` (missing_name, bad_reg_no, duplicate_reg_no), plus file-level errors."""
    text = data.decode("utf-8-sig", errors="replace")
    lines = [r for r in csv.reader(io.StringIO(text))]
    if not any(any(c.strip() for c in r) for r in lines):
        return [], ["The file is empty"]
    header = [_norm_header(h) for h in lines[0]]
    if "name" not in header or "reg_no" not in header:
        return [], [HEADER_ERROR]
    ni, ri = header.index("name"), header.index("reg_no")
    rows: List[Dict[str, Any]] = []
    for line in lines[1:]:
        if not any(c.strip() for c in line):
            continue
        name = line[ni].strip() if ni < len(line) else ""
        raw = line[ri].strip() if ri < len(line) else ""
        reg = int(raw) if raw.isdigit() and int(raw) > 0 else None
        issues = []
        if reg is None:
            issues.append("bad_reg_no")
        if not name:
            issues.append("missing_name")
        rows.append({"reg_no": reg, "raw_reg_no": raw, "name": name, "issues": issues})
    seen: Dict[int, int] = {}
    for r in rows:
        if r["reg_no"] is not None:
            seen[r["reg_no"]] = seen.get(r["reg_no"], 0) + 1
    for r in rows:
        if r["reg_no"] is not None and seen[r["reg_no"]] > 1:
            r["issues"].append("duplicate_reg_no")
    return rows, []


def list_students(db: Database, class_id: int) -> List[Dict[str, Any]]:
    rows = db.query("SELECT s.*, (SELECT COUNT(*) FROM submissions x WHERE x.student_id = s.id) AS submissions "
                    "FROM students s WHERE s.class_id = :c ORDER BY s.reg_no", {"c": class_id})
    return [{"id": r["id"], "reg_no": int(r["reg_no"]), "name": r["name"], "submissions": int(r["submissions"] or 0),
             "last_seen_at": iso_utc(r["last_seen_at"])} for r in rows]


def replace_classlist(db: Database, class_id: int, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Upsert by reg_no; students missing from the new list are removed unless they have submissions
    (those are kept and reported in `kept`)."""
    if not db.query("SELECT 1 FROM classes WHERE id = :c", {"c": class_id}):
        raise ApiError(404, "not_found", "No such class")
    clean: Dict[int, str] = {}
    for r in rows or []:
        reg, name = r.get("reg_no"), (r.get("name") or "").strip()
        if not isinstance(reg, int) or isinstance(reg, bool) or reg <= 0 or not name or reg in clean:
            raise ApiError(400, "bad_rows", "Every row needs a name and a unique positive register number")
        clean[reg] = name[:120]
    if not clean:
        raise ApiError(400, "bad_rows", "The classlist is empty")
    kept: List[int] = []
    with db.transaction() as tx:
        existing = {int(r["reg_no"]): r for r in tx.query(
            "SELECT s.id, s.reg_no, (SELECT COUNT(*) FROM submissions x WHERE x.student_id = s.id) AS n "
            "FROM students s WHERE s.class_id = :c", {"c": class_id})}
        for reg, name in clean.items():
            if reg in existing:
                tx.execute("UPDATE students SET name = :n WHERE id = :id", {"n": name, "id": existing[reg]["id"]})
            else:
                tx.execute("INSERT INTO students (class_id, reg_no, name) VALUES (:c, :r, :n)", {"c": class_id, "r": reg, "n": name})
        for reg, r in existing.items():
            if reg in clean:
                continue
            if int(r["n"] or 0) > 0:
                kept.append(reg)
            else:
                tx.execute("DELETE FROM students WHERE id = :id", {"id": r["id"]})
        tx.execute("UPDATE classes SET updated_at = CURRENT_TIMESTAMP WHERE id = :c", {"c": class_id})
    return {"students": list_students(db, class_id), "kept": sorted(kept)}
```

- [ ] **Step 4: Add the routes** to `src/sms/web/routers/classes.py`:

```python
from typing import Any, Dict, List

from fastapi import File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from sms.web.services.classlist import list_students, parse_classlist, replace_classlist
from sms.web.uploads import read_upload_files


class ClasslistBody(BaseModel):
    rows: List[Dict[str, Any]]


@router.post("/{class_id}/students/preview")
async def preview_students(class_id: int, request: Request, file: UploadFile = File(...), db=Depends(get_db)):
    if get_class(db, class_id) is None:
        raise ApiError(404, "not_found", "No such class")
    payload = await read_upload_files(request, [file])
    rows, errors = parse_classlist(payload[0][1] if payload else b"")
    return {"rows": rows, "errors": errors}


@router.put("/{class_id}/students")
def put_students(class_id: int, body: ClasslistBody, db=Depends(get_db)):
    return replace_classlist(db, class_id, body.rows)


@router.get("/{class_id}/students")
def students(class_id: int, db=Depends(get_db)):
    if get_class(db, class_id) is None:
        raise ApiError(404, "not_found", "No such class")
    return list_students(db, class_id)
```
(`read_upload_files` returns `[(filename, bytes)]` and enforces the 50 MB cap; a `.csv` is fine — it does not check types.) If `read_upload_files` rejects non-image names, read the file directly instead: `data = await file.read()` capped at 1 MB (`if len(data) > 1_000_000: raise ApiError(413, "too_large", "Classlist is bigger than 1 MB")`). Check `src/sms/web/uploads.py` first and use whichever applies.

- [ ] **Step 5: Run tests** — `uv run pytest tests/unit/test_classlist.py tests/web/test_classes_api.py -q` → PASS; `uv run pytest -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sms/web/services/classlist.py src/sms/web/routers/classes.py tests/unit/test_classlist.py tests/web/test_classes_api.py
git commit -m "feat(classes): classlist CSV preview, confirm and listing"
```

---

### Task 3: Class assignments, hand-in linkage, teacher upload / remove, delete guard

**Files:**
- Create: `src/sms/web/services/class_assignments.py`, `src/sms/web/routers/class_assignments.py`
- Modify: `src/sms/web/services/submissions.py:17-62` (`create_submission`), `src/sms/web/services/assignments.py` (`_COUNTS`, `delete_template` message), `src/sms/web/app.py`
- Test: `tests/web/test_class_assignments_api.py`, `tests/web/test_assignments_api.py`

**Interfaces:**
- `create_submission(..., assignment_id=None, class_assignment_id: Optional[int] = None, student_id: Optional[int] = None, source: str = "teacher")` — when `class_assignment_id` is set, `handed_in_at = CURRENT_TIMESTAMP`.
- `services/class_assignments.py`: `set_assignment(db, class_id, *, template_id, title=None, due_at=None, allow_student_uploads=True) -> dict`; `list_class_assignments(db, class_id) -> List[dict]`; `get_class_assignment(db, class_id, caid) -> Optional[dict]`; `update_class_assignment(db, class_id, caid, *, title, due_at, allow_student_uploads, status) -> dict`; `delete_class_assignment(db, class_id, caid) -> None`; `hand_in(db, storage, jobs, *, ca: dict, student: dict, files, source) -> dict`; `remove_hand_in(db, storage, ca_id, student_id) -> None`; `get_student(db, class_id, student_id) -> Optional[dict]`.
- Class-assignment dict keys: `id, class_id, template_id, title, due_at, status, derived_status, allow_student_uploads, released_at, template_deleted, subject, scheme_kind, submission_count, created_at, updated_at`. `derived_status` = `marking` when `status == "open"` and some submission has status not in (`done`, `needs_you`); otherwise `status`.
- Routes (`/api/classes/{class_id}/assignments`): `GET ""`, `POST ""` (201), `GET /{caid}`, `PUT /{caid}`, `DELETE /{caid}` (204), `POST /{caid}/students/{student_id}/upload` (202, multipart `files`), `DELETE /{caid}/students/{student_id}/submission` (204).
- `assignments.delete_template` 409 message also says "set in N classes" and the template dict gains `class_assignment_count`.

- [ ] **Step 1: Write the failing tests**

`tests/web/test_class_assignments_api.py`:
```python
import io

from PIL import Image

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]}
SCHEME = [{"q_id": "1a", "answer": "x = 3", "marks": [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 1}], "notes": ""}]
QUESTIONS = [{"q_id": "1a", "text": "Solve 3x = 9", "max_marks": 2}]


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def _with_key(auth):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x", "rpm_limit": 60,
                                    "confidence_threshold": 0})


def _template(auth, **over):
    body = {"title": "Quadratics — Worksheet 3", "subject": "math", "context": "", "rubric": RUBRIC,
            "scheme_kind": "mark_scheme", "questions": QUESTIONS, "scheme": SCHEME}
    body.update(over)
    return auth.post("/api/assignments", json=body).json()


def _class_with_students(auth, names=("Tan Wei Ling", "Muhammad Danish")):
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": i + 1, "name": n} for i, n in enumerate(names)]})
    c["students"] = auth.get(f"/api/classes/{c['id']}/students").json()
    return c


def test_set_edit_open_and_delete_a_class_assignment(auth):
    t = _template(auth)
    c = _class_with_students(auth)
    r = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "due_at": "2026-09-30T08:00:00Z"})
    assert r.status_code == 201
    ca = r.json()
    assert ca["title"] == "Quadratics — Worksheet 3" and ca["status"] == "draft" and ca["derived_status"] == "draft"
    assert ca["due_at"] == "2026-09-30T08:00:00Z" and ca["allow_student_uploads"] is True and ca["template_deleted"] is False
    assert ca["subject"] == "math" and ca["scheme_kind"] == "mark_scheme" and ca["submission_count"] == 0
    assert auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": 999}).status_code == 404
    got = auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
                   json={"title": "Worksheet 3", "due_at": None, "allow_student_uploads": False, "status": "open"}).json()
    assert (got["title"], got["due_at"], got["allow_student_uploads"], got["status"]) == ("Worksheet 3", None, False, "open")
    assert auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
                    json={"title": "W", "due_at": None, "allow_student_uploads": True, "status": "bogus"}).json()["error"]["code"] == "bad_status"
    assert [a["id"] for a in auth.get(f"/api/classes/{c['id']}/assignments").json()] == [ca["id"]]
    assert auth.get(f"/api/classes/{c['id']}").json()["open_assignments"] == 1
    assert auth.delete(f"/api/classes/{c['id']}/assignments/{ca['id']}").status_code == 204
    assert auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").status_code == 404


def test_teacher_upload_for_a_student_creates_a_linked_submission(auth, app):
    _with_key(auth)
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    tan = c["students"][0]
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/upload",
                  files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 202
    sid = r.json()["id"]
    row = app.state.db.query("SELECT * FROM submissions WHERE id = :s", {"s": sid})[0]
    assert row["class_assignment_id"] == ca["id"] and row["student_id"] == tan["id"] and row["source"] == "teacher"
    assert row["assignment_id"] == t["id"] and row["label"] == "#1 Tan Wei Ling" and row["handed_in_at"] is not None
    assert row["scheme_kind"] == "mark_scheme"
    # once per student
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/upload",
                  files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_handed_in"
    assert auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["submission_count"] == 1
    assert auth.get("/api/submissions").json()[0]["class_label"] == "4E2 · #1"
    # cannot delete the class assignment while it has submissions
    assert auth.delete(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["error"]["code"] == "in_use"
    # remove the hand-in: submission, pages and job are gone; the student can hand in again
    assert auth.delete(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/submission").status_code == 204
    assert app.state.db.query("SELECT 1 FROM submissions WHERE id = :s", {"s": sid}) == []
    assert app.state.db.query("SELECT 1 FROM pages WHERE submission_id = :s", {"s": sid}) == []
    assert app.state.db.query("SELECT 1 FROM jobs WHERE submission_id = :s", {"s": sid}) == []
    assert auth.delete(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/submission").status_code == 404
    assert auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{tan['id']}/upload",
                     files=[("files", ("p1.png", _png(), "image/png"))]).status_code == 202


def test_upload_for_unknown_student_or_deleted_template(auth):
    _with_key(auth)
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    assert auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/999/upload",
                     files=[("files", ("p1.png", _png(), "image/png"))]).status_code == 404
    # deleting the template is refused because it is set in a class; forced, later hand-ins fail clearly
    r = auth.delete(f"/api/assignments/{t['id']}")
    assert r.status_code == 409 and "set in 1 class" in r.json()["error"]["message"]
    assert auth.get(f"/api/assignments/{t['id']}").json()["class_assignment_count"] == 1
    assert auth.delete(f"/api/assignments/{t['id']}?force=true").status_code == 204
    assert auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["template_deleted"] is True
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/students/{c['students'][0]['id']}/upload",
                  files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 409 and r.json()["error"]["code"] == "template_deleted"
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/web/test_class_assignments_api.py -q` → FAIL.

- [ ] **Step 3: Extend `create_submission`** in `src/sms/web/services/submissions.py`:

Signature becomes:
```python
def create_submission(db: Database, storage: PageStorage, jobs: JobStore, *, label: str, subject: str,
                      context: str, rubric_json: str, files: List[Tuple[str, bytes]],
                      assignment_id: Optional[int] = None, class_assignment_id: Optional[int] = None,
                      student_id: Optional[int] = None, source: str = "teacher") -> Dict[str, Any]:
```
Replace the INSERT with:
```python
        sid = tx.insert(
            "INSERT INTO submissions (label, subject, context, rubric_json, status, assignment_id, scheme_kind, "
            "class_assignment_id, student_id, source, handed_in_at) "
            "VALUES (:label, :subject, :context, :rubric, 'uploaded', :aid, :kind, :ca, :st, :src, "
            + ("CURRENT_TIMESTAMP" if class_assignment_id is not None else "NULL") + ") RETURNING id",
            {"label": label, "subject": subject, "context": context.strip(), "rubric": rubric.model_dump_json(),
             "aid": assignment_id, "kind": scheme_kind, "ca": class_assignment_id, "st": student_id, "src": source},
        )
```
Wrap the `with db.transaction() as tx:` block in `try: ... except IntegrityError: raise ApiError(409, "already_handed_in", "This student has already handed in — remove the hand-in first to redo it")` (`from sqlalchemy.exc import IntegrityError`). Files already stored by `process_uploads` for the failed insert are orphaned; that is acceptable (the sweep does not touch them, and a duplicate hand-in is rare) — leave a one-line comment saying so.

Also add `class_label` to `list_submissions` rows: extend the SELECT with
`LEFT JOIN students st ON st.id = s.student_id LEFT JOIN classes cl ON cl.id = st.class_id` selecting `cl.name AS class_name, st.reg_no AS reg_no`, and emit `"class_label": f"{s['class_name']} · #{s['reg_no']}" if s["class_name"] else None`. Also add `"class_assignment_id": s["class_assignment_id"]` to both list rows and `get_submission`'s dict.

- [ ] **Step 4: Write the service**

`src/sms/web/services/class_assignments.py`:
```python
"""A bank template set to a class: due date, status (draft/open/released), and the students' hand-ins."""
import json
from typing import Any, Dict, List, Optional, Tuple

from sms.memory.db import Database
from sms.storage import PageStorage
from sms.timeutil import iso_utc
from sms.web.errors import ApiError
from sms.web.services.assignments import get_template
from sms.web.services.classes import get_class
from sms.web.services.pages_cleanup import unlink_pages
from sms.web.services.submissions import create_submission
from sms.worker.jobs import JobStore

STATUSES = ("draft", "open", "released")

_SELECT = ("SELECT a.*, t.subject AS subject, t.scheme_kind AS scheme_kind, "
           "(SELECT COUNT(*) FROM submissions s WHERE s.class_assignment_id = a.id) AS submission_count, "
           "(SELECT COUNT(*) FROM submissions s WHERE s.class_assignment_id = a.id AND s.status NOT IN ('done', 'needs_you')) AS in_progress "
           "FROM class_assignments a LEFT JOIN assignment_templates t ON t.id = a.template_id")


def _row(r: dict) -> Dict[str, Any]:
    status = r["status"]
    derived = "marking" if status == "open" and int(r["in_progress"] or 0) > 0 else status
    return {
        "id": r["id"], "class_id": r["class_id"], "template_id": r["template_id"], "title": r["title"],
        "due_at": iso_utc(r["due_at"]), "status": status, "derived_status": derived,
        "allow_student_uploads": bool(r["allow_student_uploads"]), "released_at": iso_utc(r["released_at"]),
        "template_deleted": r["subject"] is None, "subject": r["subject"], "scheme_kind": r["scheme_kind"],
        "submission_count": int(r["submission_count"] or 0),
        "created_at": iso_utc(r["created_at"]), "updated_at": iso_utc(r["updated_at"]),
    }


def list_class_assignments(db: Database, class_id: int) -> List[Dict[str, Any]]:
    if get_class(db, class_id) is None:
        raise ApiError(404, "not_found", "No such class")
    return [_row(r) for r in db.query(_SELECT + " WHERE a.class_id = :c ORDER BY a.due_at IS NULL, a.due_at, a.id DESC", {"c": class_id})]


def get_class_assignment(db: Database, class_id: int, caid: int) -> Optional[Dict[str, Any]]:
    rows = db.query(_SELECT + " WHERE a.id = :id AND a.class_id = :c", {"id": caid, "c": class_id})
    return _row(rows[0]) if rows else None


def require_class_assignment(db: Database, class_id: int, caid: int) -> Dict[str, Any]:
    ca = get_class_assignment(db, class_id, caid)
    if ca is None:
        raise ApiError(404, "not_found", "No such assignment in this class")
    return ca


def _parse_due(due_at: Optional[str]) -> Optional[str]:
    """ISO 8601 -> 'YYYY-MM-DD HH:MM:SS' UTC for the DateTime column; None passes through."""
    if not due_at:
        return None
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, "bad_due", "Due date must be an ISO 8601 date-time")
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def set_assignment(db: Database, class_id: int, *, template_id: int, title: Optional[str] = None,
                   due_at: Optional[str] = None, allow_student_uploads: bool = True) -> Dict[str, Any]:
    if get_class(db, class_id) is None:
        raise ApiError(404, "not_found", "No such class")
    t = get_template(db, template_id)
    if t is None:
        raise ApiError(404, "not_found", "No such assignment in the bank")
    title = (title or "").strip() or t["title"]
    caid = db.insert("INSERT INTO class_assignments (class_id, template_id, title, due_at, allow_student_uploads) "
                     "VALUES (:c, :t, :title, :due, :allow) RETURNING id",
                     {"c": class_id, "t": template_id, "title": title[:200], "due": _parse_due(due_at),
                      "allow": bool(allow_student_uploads)})
    return get_class_assignment(db, class_id, caid)  # type: ignore[return-value]


def update_class_assignment(db: Database, class_id: int, caid: int, *, title: str, due_at: Optional[str],
                            allow_student_uploads: bool, status: str) -> Dict[str, Any]:
    ca = require_class_assignment(db, class_id, caid)
    if status not in STATUSES:
        raise ApiError(400, "bad_status", "Status must be draft, open or released")
    if status == "released" and ca["status"] != "released":
        raise ApiError(400, "bad_status", "Use Release feedback to release an assignment")
    title = (title or "").strip()
    if not title:
        raise ApiError(400, "bad_title", "Give the assignment a title")
    db.execute("UPDATE class_assignments SET title = :title, due_at = :due, allow_student_uploads = :allow, status = :st, "
               "updated_at = CURRENT_TIMESTAMP WHERE id = :id",
               {"title": title[:200], "due": _parse_due(due_at), "allow": bool(allow_student_uploads), "st": status, "id": caid})
    return get_class_assignment(db, class_id, caid)  # type: ignore[return-value]


def delete_class_assignment(db: Database, class_id: int, caid: int) -> None:
    ca = require_class_assignment(db, class_id, caid)
    if ca["submission_count"]:
        raise ApiError(409, "in_use", f"{ca['submission_count']} hand-in(s) reference this assignment — remove them first")
    db.execute("DELETE FROM class_assignments WHERE id = :id", {"id": caid})


def get_student(db: Database, class_id: int, student_id: int) -> Optional[Dict[str, Any]]:
    rows = db.query("SELECT id, class_id, reg_no, name FROM students WHERE id = :s AND class_id = :c",
                    {"s": student_id, "c": class_id})
    return dict(rows[0]) if rows else None


def hand_in(db: Database, storage: PageStorage, jobs: JobStore, *, ca: Dict[str, Any], student: Dict[str, Any],
            files: List[Tuple[str, bytes]], source: str) -> Dict[str, Any]:
    """Create the student's submission for a class assignment; marking starts as for any upload."""
    template = get_template(db, ca["template_id"])
    if template is None:
        raise ApiError(409, "template_deleted", "This assignment was deleted from the bank — set it again from a current assignment")
    if db.query("SELECT 1 FROM submissions WHERE class_assignment_id = :a AND student_id = :s", {"a": ca["id"], "s": student["id"]}):
        raise ApiError(409, "already_handed_in", "This student has already handed in — remove the hand-in first to redo it")
    return create_submission(db, storage, jobs, label=f"#{student['reg_no']} {student['name']}", subject=template["subject"],
                             context=template["context"], rubric_json=json.dumps(template["rubric"]), files=files,
                             assignment_id=template["id"], class_assignment_id=ca["id"], student_id=student["id"], source=source)


def remove_hand_in(db: Database, storage: PageStorage, ca_id: int, student_id: int) -> None:
    """Delete the student's submission (pages, jobs, queue items) so they can hand in again."""
    rows = db.query("SELECT id FROM submissions WHERE class_assignment_id = :a AND student_id = :s", {"a": ca_id, "s": student_id})
    if not rows:
        raise ApiError(404, "not_found", "This student has not handed in")
    sid = rows[0]["id"]
    if db.query("SELECT 1 FROM jobs WHERE submission_id = :s AND status = 'running'", {"s": sid}):
        raise ApiError(409, "marking", "This script is being marked right now — try again in a minute")
    with db.transaction() as tx:
        paths = [r["storage_path"] for r in tx.query("SELECT storage_path FROM pages WHERE submission_id = :s AND deleted_at IS NULL", {"s": sid})]
        tx.execute("DELETE FROM teacher_queue WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM jobs WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM pages WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM submissions WHERE id = :s", {"s": sid})
    unlink_pages(storage, paths)
```
`unlink_pages(storage, paths)` exists in `pages_cleanup.py` (see its signature there and match it).

- [ ] **Step 5: Write the router** `src/sms/web/routers/class_assignments.py`:
```python
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from sms.web.deps import get_db, get_jobs, get_settings_store, get_storage, require_teacher
from sms.web.errors import ApiError
from sms.web.services.class_assignments import (delete_class_assignment, get_class_assignment, get_student, hand_in,
                                                list_class_assignments, remove_hand_in, require_class_assignment,
                                                set_assignment, update_class_assignment)
from sms.web.uploads import check_content_length, read_upload_files

router = APIRouter(prefix="/api/classes/{class_id}/assignments", tags=["class-assignments"],
                   dependencies=[Depends(require_teacher)])


class SetBody(BaseModel):
    template_id: int
    title: Optional[str] = None
    due_at: Optional[str] = None
    allow_student_uploads: bool = True


class EditBody(BaseModel):
    title: str
    due_at: Optional[str] = None
    allow_student_uploads: bool = True
    status: str


@router.get("")
def index(class_id: int, db=Depends(get_db)):
    return list_class_assignments(db, class_id)


@router.post("", status_code=201)
def create(class_id: int, body: SetBody, db=Depends(get_db)):
    return set_assignment(db, class_id, template_id=body.template_id, title=body.title, due_at=body.due_at,
                          allow_student_uploads=body.allow_student_uploads)


@router.get("/{caid}")
def show(class_id: int, caid: int, db=Depends(get_db)):
    return require_class_assignment(db, class_id, caid)


@router.put("/{caid}")
def edit(class_id: int, caid: int, body: EditBody, db=Depends(get_db)):
    return update_class_assignment(db, class_id, caid, title=body.title, due_at=body.due_at,
                                   allow_student_uploads=body.allow_student_uploads, status=body.status)


@router.delete("/{caid}", status_code=204)
def delete(class_id: int, caid: int, db=Depends(get_db)):
    delete_class_assignment(db, class_id, caid)
    return Response(status_code=204)


@router.post("/{caid}/students/{student_id}/upload", status_code=202)
async def upload_for_student(class_id: int, caid: int, student_id: int, request: Request,
                             files: List[UploadFile] = File(...), db=Depends(get_db), storage=Depends(get_storage),
                             jobs=Depends(get_jobs), settings=Depends(get_settings_store)):
    check_content_length(request)
    ca = require_class_assignment(db, class_id, caid)
    student = get_student(db, class_id, student_id)
    if student is None:
        raise ApiError(404, "not_found", "No such student in this class")
    if not await run_in_threadpool(lambda: settings.load().has_key):
        raise ApiError(400, "no_key", "Add an API key under Settings before marking")
    payload = await read_upload_files(request, files)
    return await run_in_threadpool(hand_in, db, storage, jobs, ca=ca, student=student, files=payload, source="teacher")


@router.delete("/{caid}/students/{student_id}/submission", status_code=204)
def remove(class_id: int, caid: int, student_id: int, db=Depends(get_db), storage=Depends(get_storage)):
    require_class_assignment(db, class_id, caid)
    remove_hand_in(db, storage, caid, student_id)
    return Response(status_code=204)
```
Register in `app.py`: `app.include_router(class_assignments.router)` after `classes.router`.

- [ ] **Step 6: Delete guard** in `src/sms/web/services/assignments.py`: extend `_COUNTS` with
`"(SELECT COUNT(*) FROM class_assignments c WHERE c.template_id = t.id) AS class_assignment_count"`, add `"class_assignment_count": int(r.get("class_assignment_count") or 0)` to `_row_to_dict`, and in `delete_template` refuse when `t["submission_count"] or t["class_assignment_count"]` (unless `force`), building the message from the parts that apply: `"3 scripts reference this assignment"`, `"set in 1 class"` (join with " and "), then `" — delete anyway to remove it from the bank"`. Add to `tests/web/test_assignments_api.py` an assertion that a template set in a class returns 409 with "set in 1 class" (the class-assignments test already covers it end to end; a one-liner here documents the guard).

- [ ] **Step 7: Run** `uv run pytest -q` → PASS (fix the existing `Assignments.test.tsx` fixtures only if `tsc` complains — new fields are optional).

- [ ] **Step 8: Commit**

```bash
git add src/sms/web/services/class_assignments.py src/sms/web/routers/class_assignments.py src/sms/web/services/submissions.py src/sms/web/services/assignments.py src/sms/web/app.py tests/web/test_class_assignments_api.py tests/web/test_assignments_api.py
git commit -m "feat(classes): set bank assignments to a class; teacher hand-in for a student; remove hand-in; delete guard counts classes"
```

---

### Task 4: Roster, progress counts, release gate, marks CSV

**Files:**
- Modify: `src/sms/web/services/class_assignments.py`, `src/sms/web/routers/class_assignments.py`, `src/sms/web/services/submissions.py` (extract `submission_totals`)
- Test: `tests/web/test_class_assignments_api.py`

**Interfaces:**
- `submissions.submission_totals(db, s: dict) -> Optional[dict]` — the totals block `list_submissions` computes per row, extracted so the roster reuses it (refactor `list_submissions` to call it).
- `class_assignments.roster(db, jobs, ca) -> dict` → `{"rows": [...], "counts": {"not_handed_in", "handed_in", "marking", "needs_you", "ready"}}`; row keys: `student_id, reg_no, name, submission_id, pages, handed_in_at, late, source, status, total, total_upper, total_max, needs_you_parts`. `status ∈ not_handed_in | handed_in | marking | failed | needs_you | ready | released`.
- `release(db, class_id, caid) -> dict`; `marks_csv(db, jobs, ca) -> str`.
- Routes: `GET /{caid}` now includes `"roster": roster(...)`; `POST /{caid}/release`; `GET /{caid}/marks.csv` (`text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="<slug>-marks.csv"`).

- [ ] **Step 1: Write the failing tests** (append to `tests/web/test_class_assignments_api.py`):

```python
from tests.web.seed_v2 import seed_v2


def _link(app, sid, ca_id, student_id, handed_in="2026-09-09 13:02:00"):
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :a, student_id = :s, handed_in_at = :h, source = 'student' WHERE id = :id",
                         {"a": ca_id, "s": student_id, "h": handed_in, "id": sid})


def test_roster_counts_release_gate_and_marks_csv(auth, app):
    t = _template(auth)
    c = _class_with_students(auth, names=("Tan Wei Ling", "Muhammad Danish", "Priya Nair"))
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "due_at": "2026-09-10T00:00:00Z"}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={"title": ca["title"], "due_at": ca["due_at"], "allow_student_uploads": True, "status": "open"})
    tan, danish, priya = c["students"]
    sid_tan, qids = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan")          # needs_you (part 2)
    sid_dan, _ = seed_v2(app, label="#2 Muhammad Danish", assignment_id=t["id"], run_id="r-dan", queue={})  # done
    _link(app, sid_tan, ca["id"], tan["id"])
    _link(app, sid_dan, ca["id"], danish["id"], handed_in="2026-09-11 01:00:00")                         # late
    got = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()
    rows = got["roster"]["rows"]
    assert [r["status"] for r in rows] == ["needs_you", "ready", "not_handed_in"]
    assert rows[0]["needs_you_parts"] == ["2"] and rows[0]["late"] is False and rows[0]["total"] == 3 and rows[0]["total_upper"] == 5
    assert rows[1]["late"] is True and rows[1]["pages"] == 1 and rows[1]["source"] == "student"
    assert rows[2]["submission_id"] is None and rows[2]["total"] is None
    assert got["roster"]["counts"] == {"not_handed_in": 1, "handed_in": 0, "marking": 0, "needs_you": 1, "ready": 1}
    assert got["derived_status"] == "open"
    # release is refused while a part needs the teacher
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release")
    assert r.status_code == 409 and r.json()["error"]["code"] == "needs_you" and "1 part" in r.json()["error"]["message"]
    auth.post(f"/api/queue/{qids['2']}/resolve", json={"allocations": [{"label": "M1", "got": True}, {"label": "A1", "got": False}], "reason": "ok"})
    released = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release").json()
    assert released["status"] == "released" and released["released_at"] is not None
    rows = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["roster"]["rows"]
    assert [r["status"] for r in rows] == ["released", "released", "not_handed_in"]
    # marks csv: one column per part in scheme order, teacher's mark wins, blanks for not handed in
    r = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/marks.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="quadratics-worksheet-3-marks.csv"' in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0] == "reg_no,name,1(a),1(b),2,total,max,status"
    assert lines[1] == "1,Tan Wei Ling,2,0,1,3,6,released"
    assert lines[3] == "3,Priya Nair,,,,,6,not_handed_in"


def test_release_needs_at_least_one_marked_script(auth):
    t = _template(auth)
    c = _class_with_students(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    r = auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release")
    assert r.status_code == 409 and r.json()["error"]["code"] == "nothing_marked"
```
Note: `seed_v2` uses its own QUESTIONS/SCHEME (`1a`, `1b`, `2`) while `_template` has only `1a`; the CSV columns come from the **run's** scheme? No — from the **template's** scheme. To make the test consistent, create the template in this test with `questions=seed_v2.QUESTIONS, scheme=seed_v2.SCHEME` (import them from `tests.web.seed_v2`). Tan's marks: 1a = 2, 1b = 0, 2 = teacher-resolved M1 only = 1 → total 3 of max 6.

- [ ] **Step 2: Run to verify failure** — FAIL (`roster` missing).

- [ ] **Step 3: Extract `submission_totals`** in `submissions.py`: move the body of the per-row totals computation in `list_submissions` (the `scheme_info`/`final_v2`/`compute_totals` branch) into
```python
def submission_totals(db: Database, s: dict) -> Optional[Dict[str, int]]:
    """{total, total_upper, total_max} for a submissions row (needs `run_id` and `rubric_json`), or None when unmarked."""
```
and call it from `list_submissions`.

- [ ] **Step 4: Roster, release, CSV** in `class_assignments.py`:
```python
import csv
import io
import re

from sms.schemas.scheme import q_label
from sms.web.services.submissions import get_submission, row_key, submission_totals


def _student_status(sub: Optional[dict], released: bool) -> str:
    if sub is None:
        return "not_handed_in"
    st = sub["status"]
    if st in ("uploaded", "queued"):
        return "handed_in"
    if st == "marking":
        return "marking"
    if st == "failed":
        return "failed"
    if st == "needs_you":
        return "needs_you"
    return "released" if released else "ready"


def roster(db: Database, ca: Dict[str, Any]) -> Dict[str, Any]:
    students = db.query("SELECT id, reg_no, name FROM students WHERE class_id = :c ORDER BY reg_no", {"c": ca["class_id"]})
    subs = {r["student_id"]: r for r in db.query(
        "SELECT s.*, (SELECT COUNT(*) FROM pages p WHERE p.submission_id = s.id) AS page_count "
        "FROM submissions s WHERE s.class_assignment_id = :a", {"a": ca["id"]})}
    pending: Dict[int, List[str]] = {}
    for q in db.query("SELECT q.submission_id, q.q_id FROM teacher_queue q JOIN submissions s ON s.id = q.submission_id "
                      "WHERE s.class_assignment_id = :a AND q.status = 'pending' ORDER BY q.id", {"a": ca["id"]}):
        pending.setdefault(q["submission_id"], []).append(q_label(q["q_id"]))
    released = ca["status"] == "released"
    due = ca["due_at"]
    rows = []
    counts = {"not_handed_in": 0, "handed_in": 0, "marking": 0, "needs_you": 0, "ready": 0}
    for st in students:
        sub = subs.get(st["id"])
        status = _student_status(sub, released)
        totals = submission_totals(db, sub) if sub else None
        handed = iso_utc(sub["handed_in_at"]) if sub else None
        rows.append({
            "student_id": st["id"], "reg_no": int(st["reg_no"]), "name": st["name"],
            "submission_id": sub["id"] if sub else None, "pages": int(sub["page_count"] or 0) if sub else 0,
            "handed_in_at": handed, "late": bool(due and handed and handed > due), "source": sub["source"] if sub else None,
            "status": status,
            "total": totals["total"] if totals else None, "total_upper": totals["total_upper"] if totals else None,
            "total_max": totals["total_max"] if totals else None,
            "needs_you_parts": pending.get(sub["id"], []) if sub else [],
        })
        bucket = {"failed": "marking", "released": "ready"}.get(status, status)
        counts[bucket] += 1
    return {"rows": rows, "counts": counts}


def release(db: Database, class_id: int, caid: int) -> Dict[str, Any]:
    ca = require_class_assignment(db, class_id, caid)
    n = db.query("SELECT COUNT(*) AS c FROM teacher_queue q JOIN submissions s ON s.id = q.submission_id "
                 "WHERE s.class_assignment_id = :a AND q.status = 'pending'", {"a": caid})[0]["c"]
    if int(n or 0):
        raise ApiError(409, "needs_you", f"{n} part{'s' if int(n) != 1 else ''} still need{'s' if int(n) == 1 else ''} you — clear the review queue first")
    marked = db.query("SELECT COUNT(*) AS c FROM submissions WHERE class_assignment_id = :a AND run_id IS NOT NULL", {"a": caid})[0]["c"]
    if not int(marked or 0):
        raise ApiError(409, "nothing_marked", "Nothing has been marked yet")
    db.execute("UPDATE class_assignments SET status = 'released', released_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
               "WHERE id = :id", {"id": caid})
    return get_class_assignment(db, class_id, caid)  # type: ignore[return-value]


def part_columns(template: Optional[dict]) -> List[Tuple[str, str]]:
    """(key, label) per scheme row in scheme order; criteria templates use their criterion ids."""
    if template is None:
        return []
    kind = template["scheme_kind"]
    if kind in ("mark_scheme", "rubric"):
        keys = [row_key(kind, row) for row in template["scheme"]]
        return [(k, q_label(k) if kind == "mark_scheme" else k) for k in keys]
    return [(c["id"], c["id"]) for c in template["rubric"]["criterion_defs"]]


def final_mark_by_key(detail: dict) -> Dict[str, Any]:
    """key -> int mark or "Review" (pending) from a submission detail; teacher corrections win."""
    out: Dict[str, Any] = {}
    if detail.get("marks_version") == 2:
        for p in detail.get("parts") or []:
            out[p["q_id"]] = "Review" if p["escalated"] else (p["teacher"]["total"] if p.get("teacher") else p["total"])
    else:
        for m in detail.get("marks") or []:
            out[m["q_id"]] = "Review" if m["escalated"] else (sum(m["teacher_scores"]) if m.get("teacher_scores") else m["total"])
    return out


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "assignment"


def marks_csv(db: Database, jobs: JobStore, ca: Dict[str, Any]) -> str:
    template = get_template(db, ca["template_id"])
    cols = part_columns(template)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["reg_no", "name", *[label for _, label in cols], "total", "max", "status"])
    for r in roster(db, ca)["rows"]:
        marks: Dict[str, Any] = {}
        if r["submission_id"] is not None:
            detail = get_submission(db, jobs, r["submission_id"])
            marks = final_mark_by_key(detail) if detail and detail.get("run_id") else {}
        cells = [marks.get(k, "") for k, _ in cols]
        total = "" if r["total"] is None else r["total"]
        maximum = r["total_max"] if r["total_max"] is not None else sum(
            (row_max_for(template, k) for k, _ in cols), 0)
        w.writerow([r["reg_no"], r["name"], *cells, total, maximum, r["status"]])
    return buf.getvalue()
```
`row_max_for(template, key)`: for mark_scheme/rubric use `submissions.row_max(kind, row)` on the matching scheme row (`row_key`), for criteria `c["max_score"]`. Put it beside `part_columns`. In the CSV test, Priya's `max` is 6 = 2 + 1 + 3 from the seed scheme.

`final_mark_by_key` for v1 `marks`: those rows carry `escalated`, `total`, `teacher_scores` (see `get_submission`).

Router additions:
```python
@router.get("/{caid}")
def show(class_id: int, caid: int, db=Depends(get_db)):
    ca = require_class_assignment(db, class_id, caid)
    return {**ca, "roster": roster(db, ca)}


@router.post("/{caid}/release")
def release_feedback(class_id: int, caid: int, db=Depends(get_db)):
    return release(db, class_id, caid)


@router.get("/{caid}/marks.csv")
async def marks(class_id: int, caid: int, db=Depends(get_db), jobs=Depends(get_jobs)):
    ca = require_class_assignment(db, class_id, caid)
    text = await run_in_threadpool(marks_csv, db, jobs, ca)
    return Response(content=text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{slug(ca["title"])}-marks.csv"'})
```
Update the Task 3 test's `submission_count` assertion if the roster key changes nothing else.

- [ ] **Step 5: Run** `uv run pytest -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sms/web/services/class_assignments.py src/sms/web/routers/class_assignments.py src/sms/web/services/submissions.py tests/web/test_class_assignments_api.py
git commit -m "feat(classes): roster with progress counts, release gate, marks CSV"
```

---

### Task 5: Student identity — lookup, session cookie, `require_student`

**Files:**
- Modify: `src/sms/web/deps.py`
- Create: `src/sms/web/services/student.py`, `src/sms/web/routers/student.py`
- Modify: `src/sms/web/app.py`
- Test: `tests/web/test_student_api.py`

**Interfaces:**
- `deps.STUDENT_COOKIE = "sms_student"`; `SessionSigner.issue_student(class_id: int, student_id: int) -> str`; `SessionSigner.verify_student(token) -> Optional[Tuple[int, int]]`; `require_student(request) -> dict` with keys `student_id, class_id, reg_no, name, class_name, code` (401 `student_session`).
- `services/student.py`: `lookup_student(db, code: str, reg_no: int) -> dict` (`{class_id, class_name, code, student_id, student_name, reg_no}`; 404 `no_such_class` / `no_such_student`); `touch_last_seen(db, student_id)`.
- Routes: `POST /api/student/lookup {code, reg_no}`, `POST /api/student/session {code, reg_no}` (204 + cookie), `DELETE /api/student/session` (204), `GET /api/student/me`.

- [ ] **Step 1: Write the failing tests** `tests/web/test_student_api.py`:
```python
def _class(auth, names=("Tan Wei Ling", "Muhammad Danish")):
    c = auth.post("/api/classes", json={"name": "4E2 Mathematics"}).json()
    auth.put(f"/api/classes/{c['id']}/students", json={"rows": [{"reg_no": i + 1, "name": n} for i, n in enumerate(names)]})
    c["students"] = auth.get(f"/api/classes/{c['id']}/students").json()
    return c


def test_lookup_and_session(auth, client):
    c = _class(auth)
    client.cookies.clear()      # no teacher cookie from here on
    r = client.post("/api/student/lookup", json={"code": c["code"].lower(), "reg_no": 1})
    assert r.status_code == 200 and r.json() == {"class_name": "4E2 Mathematics", "code": c["code"], "student_name": "Tan Wei Ling", "reg_no": 1}
    r = client.post("/api/student/lookup", json={"code": c["code"], "reg_no": 37})
    assert r.status_code == 404 and r.json()["error"] == {"code": "no_such_student", "message": "No student #37 in this class — check the number on your class list"}
    r = client.post("/api/student/lookup", json={"code": "ZZZZ", "reg_no": 1})
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_such_class"
    assert client.get("/api/student/me").status_code == 401
    assert client.post("/api/student/session", json={"code": c["code"], "reg_no": 1}).status_code == 204
    assert "sms_student" in client.cookies
    assert client.get("/api/student/me").json() == {"class_name": "4E2 Mathematics", "code": c["code"], "student_name": "Tan Wei Ling", "reg_no": 1}
    # the student cookie opens nothing teacher-only
    assert client.get("/api/classes").status_code == 401
    assert client.delete("/api/student/session").status_code == 204
    assert client.get("/api/student/me").status_code == 401


def test_teacher_cookie_is_not_a_student_session(auth):
    assert auth.get("/api/student/me").status_code == 401


def test_archived_class_is_invisible_and_kills_sessions(auth, client):
    c = _class(auth)
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    auth.post(f"/api/classes/{c['id']}/archive")
    assert client.post("/api/student/lookup", json={"code": c["code"], "reg_no": 1}).json()["error"]["code"] == "no_such_class"
    assert client.get("/api/student/me").status_code == 401


def test_lookup_failures_are_rate_limited(auth, client):
    c = _class(auth)
    client.cookies.clear()
    for _ in range(5):
        client.post("/api/student/lookup", json={"code": c["code"], "reg_no": 99})
    assert client.post("/api/student/lookup", json={"code": c["code"], "reg_no": 1}).status_code == 429


def test_session_updates_last_seen(auth, client):
    c = _class(auth)
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 2})
    client.cookies.clear()
    r = auth.post("/api/auth/login", json={"password": "letmein"})
    assert auth.get(f"/api/classes/{c['id']}/students").json()[1]["last_seen_at"] is not None
```
(The `auth` and `client` fixtures share one `TestClient`, so the cookie jar is shared — the tests clear it where the teacher cookie must not be present, and log the teacher back in when needed.)

- [ ] **Step 2: Run to verify failure** — FAIL.

- [ ] **Step 3: deps.py** additions:
```python
STUDENT_COOKIE = "sms_student"


class SessionSigner:
    def __init__(self, secret: str):
        self._s = URLSafeTimedSerializer(secret, salt="sms-session")
        self._student = URLSafeTimedSerializer(secret, salt="sms-student")

    # ...issue/verify unchanged...

    def issue_student(self, class_id: int, student_id: int) -> str:
        return self._student.dumps({"role": "student", "class_id": class_id, "student_id": student_id})

    def verify_student(self, token: str) -> Optional[Tuple[int, int]]:
        try:
            data = self._student.loads(token, max_age=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return None
        if data.get("role") != "student":
            return None
        return int(data["class_id"]), int(data["student_id"])


def require_student(request: Request) -> dict:
    token = request.cookies.get(STUDENT_COOKIE)
    ids = request.app.state.signer.verify_student(token) if token else None
    if ids is None:
        raise ApiError(401, "student_session", "Enter your class code and number to continue")
    rows = request.app.state.db.query(
        "SELECT s.id AS student_id, s.class_id, s.reg_no, s.name, c.name AS class_name, c.code "
        "FROM students s JOIN classes c ON c.id = s.class_id WHERE s.id = :s AND s.class_id = :c AND c.archived_at IS NULL",
        {"s": ids[1], "c": ids[0]})
    if not rows:
        raise ApiError(401, "student_session", "Enter your class code and number to continue")
    r = rows[0]
    return {"student_id": r["student_id"], "class_id": r["class_id"], "reg_no": int(r["reg_no"]), "name": r["name"],
            "class_name": r["class_name"], "code": r["code"]}
```

- [ ] **Step 4: service and router**

`src/sms/web/services/student.py`:
```python
"""What a student can see: their class, their assignments, their own hand-in and released feedback."""
from typing import Any, Dict

from sms.memory.db import Database
from sms.web.errors import ApiError
from sms.web.services.classes import normalise_code

NO_CLASS = "That class code is not right — check the link your teacher shared"


def lookup_student(db: Database, code: str, reg_no: int) -> Dict[str, Any]:
    code = normalise_code(code)
    rows = db.query("SELECT id, name, code FROM classes WHERE code = :c AND archived_at IS NULL", {"c": code})
    if not rows:
        raise ApiError(404, "no_such_class", NO_CLASS)
    cls = rows[0]
    st = db.query("SELECT id, name, reg_no FROM students WHERE class_id = :c AND reg_no = :r", {"c": cls["id"], "r": reg_no})
    if not st:
        raise ApiError(404, "no_such_student", f"No student #{reg_no} in this class — check the number on your class list")
    return {"class_id": cls["id"], "class_name": cls["name"], "code": cls["code"],
            "student_id": st[0]["id"], "student_name": st[0]["name"], "reg_no": int(st[0]["reg_no"])}


def touch_last_seen(db: Database, student_id: int) -> None:
    db.execute("UPDATE students SET last_seen_at = CURRENT_TIMESTAMP WHERE id = :s", {"s": student_id})


def public(found: Dict[str, Any]) -> Dict[str, Any]:
    return {"class_name": found["class_name"], "code": found["code"], "student_name": found["student_name"], "reg_no": found["reg_no"]}
```

`src/sms/web/routers/student.py`:
```python
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from sms.web.deps import SESSION_MAX_AGE, STUDENT_COOKIE, client_ip, get_db, require_student
from sms.web.errors import ApiError
from sms.web.services.student import lookup_student, public, touch_last_seen

router = APIRouter(prefix="/api/student", tags=["student"])


class IdBody(BaseModel):
    code: str
    reg_no: int


def _lookup(request: Request, body: IdBody, db):
    ip = client_ip(request)
    limiter = request.app.state.login_limiter
    if limiter.blocked(ip):
        raise ApiError(429, "too_many_attempts", "Too many attempts — wait a minute and try again")
    try:
        return lookup_student(db, body.code, body.reg_no)
    except ApiError:
        limiter.record_failure(ip)
        raise


@router.post("/lookup")
def lookup(body: IdBody, request: Request, db=Depends(get_db)):
    return public(_lookup(request, body, db))


@router.post("/session", status_code=204)
def start_session(body: IdBody, request: Request, response: Response, db=Depends(get_db)):
    found = _lookup(request, body, db)
    touch_last_seen(db, found["student_id"])
    secure = request.url.hostname not in ("localhost", "127.0.0.1", "testserver")
    response.set_cookie(STUDENT_COOKIE, request.app.state.signer.issue_student(found["class_id"], found["student_id"]),
                        max_age=SESSION_MAX_AGE, httponly=True, samesite="lax", secure=secure, path="/")
    return None   # keep the injected response (and its cookie); a new Response would drop it


@router.delete("/session", status_code=204)
def end_session(response: Response):
    response.delete_cookie(STUDENT_COOKIE, path="/")
    return None


@router.get("/me")
def me(student: dict = Depends(require_student)):
    return {"class_name": student["class_name"], "code": student["code"], "student_name": student["name"], "reg_no": student["reg_no"]}
```
Register `student.router` in `app.py`.

- [ ] **Step 5: Run** `uv run pytest -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sms/web/deps.py src/sms/web/services/student.py src/sms/web/routers/student.py src/sms/web/app.py tests/web/test_student_api.py
git commit -m "feat(student): class code + register number lookup and a scoped student session cookie"
```

---

### Task 6: Student API — assignments, hand-in, feedback view, pages

**Files:**
- Modify: `src/sms/web/services/student.py`, `src/sms/web/routers/student.py`
- Test: `tests/web/test_student_api.py`

**Interfaces:**
- `student_assignments(db, student) -> List[dict]`: `id, title, due_at, status (to_hand_in|handed_in|checking|feedback_ready), handed_in_at, allow_student_uploads`.
- `student_assignment(db, jobs, student, caid) -> dict`: the list row plus `feedback` block when `feedback_ready` (`{summary, strengths, improvement_plan, next_steps, total, max, questions: [{label, mark, max, comment, try_next, transcription}], pages: [page ids]}`) else `feedback: null`.
- `student_hand_in(db, storage, jobs, student, caid, files) -> dict`.
- `student_page_path(db, storage, student, page_id) -> Path` (404/410).
- Routes: `GET /api/student/assignments`, `GET /api/student/assignments/{caid}`, `POST /api/student/assignments/{caid}/hand-in` (202), `GET /api/student/pages/{page_id}`.

- [ ] **Step 1: Write the failing tests** (append to `tests/web/test_student_api.py`):
```python
import io
from PIL import Image
from tests.web.seed_v2 import QUESTIONS, SCHEME, seed_v2

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]}


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def _setup(auth):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x", "rpm_limit": 60, "confidence_threshold": 0})
    t = auth.post("/api/assignments", json={"title": "Worksheet 3", "subject": "math", "context": "", "rubric": RUBRIC,
                                            "scheme_kind": "mark_scheme", "questions": QUESTIONS, "scheme": SCHEME}).json()
    c = _class(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "due_at": "2026-09-30T08:00:00Z"}).json()
    draft = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "title": "Hidden draft"}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={"title": ca["title"], "due_at": ca["due_at"], "allow_student_uploads": True, "status": "open"})
    return t, c, ca, draft


def test_student_sees_open_assignments_and_hands_in_once(auth, client, app):
    t, c, ca, draft = _setup(auth)
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    lst = client.get("/api/student/assignments").json()
    assert [(a["id"], a["title"], a["status"]) for a in lst] == [(ca["id"], "Worksheet 3", "to_hand_in")]
    assert client.get(f"/api/student/assignments/{draft['id']}").status_code == 404
    r = client.post(f"/api/student/assignments/{ca['id']}/hand-in", files=[("files", ("p1.png", _png(), "image/png")), ("files", ("p2.png", _png(), "image/png"))])
    assert r.status_code == 202
    sid = r.json()["id"]
    row = app.state.db.query("SELECT * FROM submissions WHERE id = :s", {"s": sid})[0]
    assert row["source"] == "student" and row["student_id"] == c["students"][0]["id"] and row["label"] == "#1 Tan Wei Ling"
    assert client.post(f"/api/student/assignments/{ca['id']}/hand-in", files=[("files", ("p1.png", _png(), "image/png"))]).json()["error"]["code"] == "already_handed_in"
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["status"] == "handed_in" and got["handed_in_at"] is not None and got["pages"] == 2 and got["feedback"] is None
    # the teacher's roster shows the same
    auth.post("/api/auth/login", json={"password": "letmein"})
    roster = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}").json()["roster"]
    assert roster["rows"][0]["status"] == "handed_in" and roster["rows"][0]["source"] == "student"


def test_hand_in_refused_when_closed_or_not_open(auth, client):
    t, c, ca, draft = _setup(auth)
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={"title": "W", "due_at": None, "allow_student_uploads": False, "status": "open"})
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    r = client.post(f"/api/student/assignments/{ca['id']}/hand-in", files=[("files", ("p1.png", _png(), "image/png"))])
    assert r.status_code == 403 and r.json()["error"]["code"] == "uploads_closed"
    assert client.get("/api/student/assignments").json()[0]["allow_student_uploads"] is False


def test_feedback_hidden_until_release_then_complete_and_scoped(auth, client, app):
    t, c, ca, draft = _setup(auth)
    tan, danish = c["students"]
    sid, qids = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan", queue={})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :a, student_id = :s, handed_in_at = CURRENT_TIMESTAMP, source = 'student' WHERE id = :id",
                         {"a": ca["id"], "s": tan["id"], "id": sid})
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["status"] == "checking" and got["feedback"] is None
    auth.post("/api/auth/login", json={"password": "letmein"})
    assert auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release").status_code == 200
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["status"] == "feedback_ready"
    fb = got["feedback"]
    assert fb["total"] == 3 and fb["max"] == 6 and fb["summary"] == "Good effort." and fb["strengths"] == ["method"]
    assert [(q["label"], q["mark"], q["max"]) for q in fb["questions"]] == [("1(a)", 2, 2), ("1(b)", 0, 1), ("2", 1, 3)]
    assert fb["questions"][0]["transcription"] == "x = 3" and fb["questions"][0]["comment"] == ""
    page_id = app.state.db.query("SELECT id FROM pages WHERE submission_id = :s", {"s": sid})[0]["id"]
    assert fb["pages"] == [page_id]
    text = str(got)
    for word in ("escalat", "confidence", "reviewer"):
        assert word not in text.lower()
    # another student cannot see Tan's page
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 2})
    assert client.get(f"/api/student/pages/{page_id}").status_code == 404
    assert client.get("/api/student/assignments").json()[0]["status"] == "to_hand_in"
```
(`seed_v2` writes `pages.storage_path = "pages/h<sid>.jpg"` without a file; a 404 "missing from storage" for Tan's own page is fine — the test only checks the other student gets 404. If you want the positive case, write `app.state.storage.abs(...)` bytes first.)

- [ ] **Step 2: Run to verify failure** — FAIL.

- [ ] **Step 3: Service** (append to `services/student.py`):
```python
import json
from pathlib import Path
from typing import List, Optional, Tuple

from sms.schemas.scheme import norm_qid
from sms.storage import PageStorage
from sms.web.services.class_assignments import get_class_assignment, get_student, hand_in
from sms.web.services.submissions import get_submission
from sms.timeutil import iso_utc
from sms.worker.jobs import JobStore


def _status(sub: Optional[dict], released: bool) -> str:
    if sub is None:
        return "to_hand_in"
    if sub["status"] not in ("done", "needs_you"):
        return "handed_in"
    if sub["status"] == "needs_you" or not released:
        return "checking"
    return "feedback_ready"


def _visible(db: Database, student: dict, caid: Optional[int] = None) -> List[dict]:
    sql = ("SELECT a.*, s.id AS submission_id, s.status AS sub_status, s.handed_in_at, s.run_id, "
           "(SELECT COUNT(*) FROM pages p WHERE p.submission_id = s.id) AS page_count "
           "FROM class_assignments a LEFT JOIN submissions s ON s.class_assignment_id = a.id AND s.student_id = :st "
           "WHERE a.class_id = :c AND a.status != 'draft'")
    params = {"st": student["student_id"], "c": student["class_id"]}
    if caid is not None:
        sql += " AND a.id = :a"
        params["a"] = caid
    return db.query(sql + " ORDER BY a.due_at IS NULL, a.due_at, a.id DESC", params)


def _row(r: dict) -> Dict[str, Any]:
    sub = {"status": r["sub_status"]} if r["submission_id"] is not None else None
    return {"id": r["id"], "title": r["title"], "due_at": iso_utc(r["due_at"]),
            "status": _status(sub, r["status"] == "released"), "handed_in_at": iso_utc(r["handed_in_at"]),
            "pages": int(r["page_count"] or 0), "allow_student_uploads": bool(r["allow_student_uploads"])}


def student_assignments(db: Database, student: dict) -> List[Dict[str, Any]]:
    return [_row(r) for r in _visible(db, student)]


def feedback_view(detail: dict) -> Dict[str, Any]:
    """The student-safe projection of a marked submission: final marks per question, comments, transcription."""
    fb = detail.get("feedback") or {}
    comments = {norm_qid(c.get("q_id")): c for c in fb.get("per_question_comments") or []}
    questions = []
    if detail.get("marks_version") == 2:
        for p in detail.get("parts") or []:
            c = comments.get(norm_qid(p["q_id"]), {})
            questions.append({"label": p["label"], "mark": p["teacher"]["total"] if p.get("teacher") else p["total"], "max": p["max"],
                              "comment": c.get("comment", ""), "try_next": c.get("suggested_action", ""),
                              "transcription": p.get("extracted") or ""})
    else:
        for m in detail.get("marks") or []:
            c = comments.get(norm_qid(m["q_id"]), {})
            questions.append({"label": m["q_id"], "mark": sum(m["teacher_scores"]) if m.get("teacher_scores") else m["total"], "max": m["max"],
                              "comment": c.get("comment", ""), "try_next": c.get("suggested_action", ""),
                              "transcription": m.get("evidence") or ""})
    totals = detail.get("totals") or {}
    return {"summary": fb.get("summary", ""), "strengths": fb.get("strengths") or [],
            "improvement_plan": fb.get("improvement_plan") or [], "next_steps": fb.get("next_steps") or [],
            "total": totals.get("total"), "max": totals.get("total_max"), "questions": questions,
            "pages": [p["id"] for p in detail.get("pages") or [] if not p["deleted"]]}


def student_assignment(db: Database, jobs: JobStore, student: dict, caid: int) -> Dict[str, Any]:
    rows = _visible(db, student, caid)
    if not rows:
        raise ApiError(404, "not_found", "No such assignment")
    r = rows[0]
    out = _row(r)
    out["feedback"] = None
    if out["status"] == "feedback_ready":
        detail = get_submission(db, jobs, r["submission_id"])
        out["feedback"] = feedback_view(detail) if detail else None
    return out


def student_hand_in(db: Database, storage: PageStorage, jobs: JobStore, student: dict, caid: int,
                    files: List[Tuple[str, bytes]]) -> Dict[str, Any]:
    ca = get_class_assignment(db, student["class_id"], caid)
    if ca is None or ca["status"] == "draft":
        raise ApiError(404, "not_found", "No such assignment")
    if ca["status"] != "open" or not ca["allow_student_uploads"]:
        raise ApiError(403, "uploads_closed", "Hand-ins are closed for this assignment — ask your teacher")
    st = get_student(db, student["class_id"], student["student_id"])
    return hand_in(db, storage, jobs, ca=ca, student=st, files=files, source="student")


def student_page_path(db: Database, storage: PageStorage, student: dict, page_id: int) -> Path:
    rows = db.query("SELECT p.storage_path, p.deleted_at FROM pages p JOIN submissions s ON s.id = p.submission_id "
                    "WHERE p.id = :p AND s.student_id = :st AND p.kind = 'student'", {"p": page_id, "st": student["student_id"]})
    if not rows:
        raise ApiError(404, "not_found", "No such page")
    if rows[0]["deleted_at"] is not None:
        raise ApiError(410, "gone", "This page was deleted after marking")
    path = storage.abs(rows[0]["storage_path"])
    if not path.is_file():
        raise ApiError(404, "not_found", "Page image is missing from storage")
    return path
```
`v1` mark rows in `get_submission` have `max` (`per_q_max`) and `evidence`. Note `hand_in` needs `no_key` handling: check `settings.load().has_key` in the router like the teacher upload does (400 `no_key` → for students say "Your teacher has not finished setting up marking yet").

- [ ] **Step 4: Router** additions:
```python
from typing import List
from fastapi import File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sms.web.deps import get_jobs, get_settings_store, get_storage
from sms.web.services.student import student_assignment, student_assignments, student_hand_in, student_page_path
from sms.web.uploads import check_content_length, read_upload_files

MAX_HAND_IN_PAGES = 20


@router.get("/assignments")
def assignments(student: dict = Depends(require_student), db=Depends(get_db)):
    return student_assignments(db, student)


@router.get("/assignments/{caid}")
def assignment(caid: int, student: dict = Depends(require_student), db=Depends(get_db), jobs=Depends(get_jobs)):
    return student_assignment(db, jobs, student, caid)


@router.post("/assignments/{caid}/hand-in", status_code=202)
async def hand_in_pages(caid: int, request: Request, files: List[UploadFile] = File(...),
                        student: dict = Depends(require_student), db=Depends(get_db), storage=Depends(get_storage),
                        jobs=Depends(get_jobs), settings=Depends(get_settings_store)):
    check_content_length(request)
    if len(files) > MAX_HAND_IN_PAGES:
        raise ApiError(400, "too_many_pages", f"Hand in at most {MAX_HAND_IN_PAGES} pages")
    if not await run_in_threadpool(lambda: settings.load().has_key):
        raise ApiError(400, "no_key", "Your teacher has not finished setting up marking yet — try again later")
    payload = await read_upload_files(request, files)
    return await run_in_threadpool(student_hand_in, db, storage, jobs, student, caid, payload)


@router.get("/pages/{page_id}")
def page(page_id: int, student: dict = Depends(require_student), db=Depends(get_db), storage=Depends(get_storage)):
    return FileResponse(student_page_path(db, storage, student, page_id), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})
```

- [ ] **Step 5: Run** `uv run pytest -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sms/web/services/student.py src/sms/web/routers/student.py tests/web/test_student_api.py
git commit -m "feat(student): assignments list, hand-in, released feedback view, own pages"
```

---

### Task 7: Frontend — types, Classes list, Nav, routes, Submissions class column, delete dialog copy

**Files:**
- Modify: `web/src/api/types.ts`, `web/src/components/Nav.tsx`, `web/src/App.tsx`, `web/src/pages/Submissions.tsx`, `web/src/pages/Assignments.tsx`, `web/src/styles/app.css`
- Create: `web/src/pages/Classes.tsx`
- Test: `web/src/pages/__tests__/Classes.test.tsx`, update `Assignments.test.tsx`, `Submissions.test.tsx`

**Interfaces (types added to `types.ts`):**
```ts
export interface ClassRow { id: number; name: string; code: string; student_count: number; open_assignments: number; archived_at: string | null; created_at: string; updated_at: string }
export interface Student { id: number; reg_no: number; name: string; submissions: number; last_seen_at: string | null }
export interface ClasslistPreviewRow { reg_no: number | null; raw_reg_no: string; name: string; issues: ("missing_name" | "bad_reg_no" | "duplicate_reg_no")[] }
export type ClassAssignmentStatus = "draft" | "open" | "released";
export interface ClassAssignment {
  id: number; class_id: number; template_id: number; title: string; due_at: string | null; status: ClassAssignmentStatus;
  derived_status: ClassAssignmentStatus | "marking"; allow_student_uploads: boolean; released_at: string | null;
  template_deleted: boolean; subject: Subject | null; scheme_kind: SchemeKind | null; submission_count: number; created_at: string; updated_at: string;
}
export type RosterStatus = "not_handed_in" | "handed_in" | "marking" | "failed" | "needs_you" | "ready" | "released";
export interface RosterRow { student_id: number; reg_no: number; name: string; submission_id: number | null; pages: number; handed_in_at: string | null; late: boolean; source: "teacher" | "student" | null; status: RosterStatus; total: number | null; total_upper: number | null; total_max: number | null; needs_you_parts: string[] }
export interface Roster { rows: RosterRow[]; counts: Record<"not_handed_in" | "handed_in" | "marking" | "needs_you" | "ready", number> }
export interface ClassAssignmentDetail extends ClassAssignment { roster: Roster }
export type StudentAssignmentStatus = "to_hand_in" | "handed_in" | "checking" | "feedback_ready";
export interface StudentMe { class_name: string; code: string; student_name: string; reg_no: number }
export interface StudentAssignment { id: number; title: string; due_at: string | null; status: StudentAssignmentStatus; handed_in_at: string | null; pages: number; allow_student_uploads: boolean }
export interface StudentFeedback { summary: string; strengths: string[]; improvement_plan: string[]; next_steps: string[]; total: number | null; max: number | null; questions: { label: string; mark: number; max: number; comment: string; try_next: string; transcription: string }[]; pages: number[] }
export interface StudentAssignmentDetail extends StudentAssignment { feedback: StudentFeedback | null }
```
Also add `class_label?: string | null; class_assignment_id?: number | null` to `SubmissionRow`/`SubmissionDetail`, and `class_assignment_count?: number` to `AssignmentTemplate`.

- [ ] **Step 1: Write the failing tests** `web/src/pages/__tests__/Classes.test.tsx` (copy the `mockFetch` helper pattern from `Assignments.test.tsx`):
```tsx
describe("Classes", () => {
  it("lists classes as cards and creates a new one", async () => {
    let list: ClassRow[] = [{ id: 1, name: "4E2 Mathematics", code: "CE4R", student_count: 40, open_assignments: 2, archived_at: null, created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z" },
      { id: 2, name: "Old 3N1", code: "QWER", student_count: 0, open_assignments: 0, archived_at: "2026-09-01T00:00:00Z", created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z" }];
    const calls = mockFetch({
      "GET /api/classes": () => new Response(JSON.stringify(list), { status: 200 }),
      "POST /api/classes": () => { list = [...list, { ...list[0], id: 3, name: "4E1 Science", code: "TZ7K", student_count: 0, open_assignments: 0 }]; return new Response(JSON.stringify(list[2]), { status: 201 }); },
    });
    render(<MemoryRouter><Classes /></MemoryRouter>);
    const card = (await screen.findByText("4E2 Mathematics")).closest("a")!;
    expect(card).toHaveAttribute("href", "/classes/1");
    expect(card).toHaveTextContent("CE4R");
    expect(card).toHaveTextContent("40 students");
    expect(card).toHaveTextContent("2 open");
    expect(screen.getByText("Archived (1)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New class" }));
    await userEvent.type(screen.getByLabelText("Class name"), "4E1 Science");
    await userEvent.click(screen.getByRole("button", { name: "Create class" }));
    expect(await screen.findByText("4E1 Science")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/classes")).toBe(true);
  });

  it("shows the empty state", async () => {
    mockFetch({ "GET /api/classes": () => new Response("[]", { status: 200 }) });
    render(<MemoryRouter><Classes /></MemoryRouter>);
    expect(await screen.findByText(/No classes yet/)).toBeInTheDocument();
  });
});
```
Update `Submissions.test.tsx`: add a row with `class_label: "4E2 · #12"` and assert the table has a `Class` header and the cell text. Update `Assignments.test.tsx` delete guard: a template with `class_assignment_count: 2` shows "set in 2 classes" in the dialog.

- [ ] **Step 2: Run** `cd web && npx vitest run` → FAIL.

- [ ] **Step 3: Implement**

`web/src/pages/Classes.tsx`:
```tsx
import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { ClassRow } from "../api/types";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";

export function Classes() {
  const [rows, setRows] = useState<ClassRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setRows(await api.get<ClassRow[]>("/api/classes")); setError(null); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Couldn't load classes."); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const create = async () => {
    setBusy(true);
    try { await api.post("/api/classes", { name: name.trim() }); setCreating(false); setName(""); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Something went wrong — try again."); }
    finally { setBusy(false); }
  };
  const live = (rows ?? []).filter((c) => !c.archived_at);
  const archived = (rows ?? []).filter((c) => c.archived_at);
  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Classes</h1><p className="meta">Each class has a code students type to hand in.</p></div>
        <Button variant="primary" onClick={() => setCreating(true)}><Plus size={16} aria-hidden /> New class</Button>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {rows && rows.length === 0 && <EmptyState title="No classes yet" hint="Create a class, upload its classlist, then set an assignment from the bank." />}
      <div className="cards">
        {live.map((c) => <ClassCard key={c.id} c={c} />)}
      </div>
      {archived.length > 0 && (
        <details className="section"><summary>Archived ({archived.length})</summary>
          <div className="cards">{archived.map((c) => <ClassCard key={c.id} c={c} />)}</div>
        </details>
      )}
      {creating && (
        <Dialog title="New class" onClose={() => setCreating(false)}
          footer={<><Button variant="secondary" onClick={() => setCreating(false)}>Cancel</Button><Button variant="primary" onClick={create} disabled={busy || !name.trim()}>Create class</Button></>}>
          <div className="field"><label htmlFor="class-name">Class name</label>
            <input id="class-name" className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="4E2 Mathematics"
              onKeyDown={(e) => { if (e.key === "Enter" && name.trim()) create(); }} /></div>
        </Dialog>
      )}
    </div>
  );
}

function ClassCard({ c }: { c: ClassRow }) {
  return (
    <Link to={`/classes/${c.id}`} className="card-link">
      <div className="card-title">{c.name}</div>
      <div className="meta"><span className="mono">{c.code}</span> · {c.student_count} student{c.student_count === 1 ? "" : "s"} · {c.open_assignments} open</div>
    </Link>
  );
}
```
Check `EmptyState`'s props in `web/src/components/EmptyState.tsx` and match them. Add to `app.css`:
```css
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-top: 16px; }
.card-link { display: block; border: 2px solid var(--color-divider); padding: 20px; text-decoration: none; color: inherit; min-height: 44px; }
.card-link:hover { border-color: var(--ink); }
.card-title { font-size: 20px; font-weight: 700; margin-bottom: 6px; }
```
Nav: add `<NavLink to="/classes">Classes</NavLink>` first; make `index` redirect to `/classes` and the `*` route too. Routes: `/classes` → `Classes`, `/classes/:id` → `ClassPage` (Task 8), `/classes/:id/assignments/:caid` → `ClassAssignmentPage` (Task 9). Until Tasks 8/9 exist, register only `/classes`.

Submissions: add `<th>Class</th>` after Script and `<td>{r.class_label ?? "—"}</td>`. Assignments delete dialog `DeleteWarning`: when `class_assignment_count > 0` add a sentence "It is set in N class(es); those class assignments will need to be set again." and treat it as in-use (force + "Delete anyway").

- [ ] **Step 4: Run** `npx vitest run && npx tsc --noEmit && npm run build` → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): Classes list, nav entry, class column on submissions, delete dialog counts classes"
```

---

### Task 8: Frontend — Class page (Students / Assignments / Settings tabs)

**Files:**
- Create: `web/src/pages/ClassPage.tsx`, `web/src/components/ClasslistImport.tsx`
- Modify: `web/src/App.tsx`, `web/src/styles/app.css`
- Test: `web/src/pages/__tests__/ClassPage.test.tsx`

**Interfaces:** `ClasslistImport({ classId, onSaved })` — drop zone → `POST /api/classes/{id}/students/preview` → preview table → **Confirm classlist** (`PUT`). `ClassPage` reads `useParams().id`, tabs via `?tab=students|assignments|settings` (default `students`).

- [ ] **Step 1: Write the failing tests** `ClassPage.test.tsx`:
```tsx
const cls: ClassRow = { id: 1, name: "4E2 Mathematics", code: "CE4R", student_count: 0, open_assignments: 0, archived_at: null, created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z" };
const app = (tab = "") => (
  <MemoryRouter initialEntries={[`/classes/1${tab}`]}><Routes><Route path="/classes/:id" element={<ClassPage />} /></Routes></MemoryRouter>
);

it("copies the class link and explains the CSV in the empty state", async () => {
  mockFetch({ "GET /api/classes/1": () => new Response(JSON.stringify(cls), { status: 200 }), "GET /api/classes/1/students": () => new Response("[]", { status: 200 }) });
  const writeText = vi.fn(() => Promise.resolve());
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  render(app());
  expect(await screen.findByText("4E2 Mathematics")).toBeInTheDocument();
  expect(screen.getByText(/two columns: name, reg_no/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Copy link" }));
  expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/\/c\/CE4R$/));
  expect(await screen.findByText(/Paste this into Google Classroom/)).toBeInTheDocument();
});

it("previews a CSV with issues, then confirms a clean one", async () => {
  const preview = { rows: [{ reg_no: 1, raw_reg_no: "1", name: "Tan", issues: [] }, { reg_no: 1, raw_reg_no: "1", name: "Lim", issues: ["duplicate_reg_no"] }], errors: [] };
  let students: Student[] = [];
  const calls = mockFetch({
    "GET /api/classes/1": () => new Response(JSON.stringify(cls), { status: 200 }),
    "GET /api/classes/1/students": () => new Response(JSON.stringify(students), { status: 200 }),
    "POST /api/classes/1/students/preview": () => new Response(JSON.stringify(preview), { status: 200 }),
    "PUT /api/classes/1/students": () => { students = [{ id: 1, reg_no: 1, name: "Tan", submissions: 0, last_seen_at: null }]; return new Response(JSON.stringify({ students, kept: [] }), { status: 200 }); },
  });
  render(app());
  await screen.findByText("4E2 Mathematics");
  const input = screen.getByLabelText("Choose classlist file") as HTMLInputElement;
  await userEvent.upload(input, new File(["name,reg_no\nTan,1\nLim,1\n"], "list.csv", { type: "text/csv" }));
  expect(await screen.findByText("Duplicate register number")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Confirm classlist" })).toBeDisabled();
  preview.rows[1] = { reg_no: 2, raw_reg_no: "2", name: "Lim", issues: [] };
  await userEvent.upload(input, new File(["name,reg_no\nTan,1\nLim,2\n"], "list.csv", { type: "text/csv" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Confirm classlist" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Confirm classlist" }));
  expect(await screen.findByRole("cell", { name: "Tan" })).toBeInTheDocument();
  expect(calls.some((c) => c.method === "PUT" && c.path === "/api/classes/1/students")).toBe(true);
});

it("sets an assignment from the bank and opens it", async () => {
  const templates = [{ id: 7, title: "Worksheet 3", subject: "math", context: "", rubric: { criterion_defs: [] }, criteria_count: 0, total_marks: 6, times_used: 0, created_at: "", updated_at: "", scheme_kind: "mark_scheme", questions: [], scheme: [], paper_page_ids: [], scheme_page_ids: [], delete_pages_after_marking: null, effective_delete_pages: true }];
  let cas: ClassAssignment[] = [];
  const calls = mockFetch({
    "GET /api/classes/1": () => new Response(JSON.stringify(cls), { status: 200 }),
    "GET /api/classes/1/assignments": () => new Response(JSON.stringify(cas), { status: 200 }),
    "GET /api/assignments": () => new Response(JSON.stringify(templates), { status: 200 }),
    "POST /api/classes/1/assignments": () => { cas = [{ id: 3, class_id: 1, template_id: 7, title: "Worksheet 3", due_at: null, status: "draft", derived_status: "draft", allow_student_uploads: true, released_at: null, template_deleted: false, subject: "math", scheme_kind: "mark_scheme", submission_count: 0, created_at: "", updated_at: "" }]; return new Response(JSON.stringify(cas[0]), { status: 201 }); },
    "PUT /api/classes/1/assignments/3": () => { cas[0] = { ...cas[0], status: "open", derived_status: "open" }; return new Response(JSON.stringify(cas[0]), { status: 200 }); },
  });
  render(app("?tab=assignments"));
  await userEvent.click(await screen.findByRole("button", { name: "Set assignment" }));
  await userEvent.selectOptions(await screen.findByLabelText("Assignment from the bank"), "7");
  await userEvent.click(screen.getByRole("button", { name: "Set for this class" }));
  const row = (await screen.findByText("Worksheet 3")).closest("tr")!;
  expect(row).toHaveTextContent("Draft");
  await userEvent.click(within(row).getByRole("button", { name: "Open" }));
  await waitFor(() => expect(row).toHaveTextContent("Open"));
  expect(calls.some((c) => c.method === "PUT" && c.path === "/api/classes/1/assignments/3")).toBe(true);
  expect(within(row).getByRole("link", { name: "Worksheet 3" })).toHaveAttribute("href", "/classes/1/assignments/3");
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

`ClasslistImport.tsx`:
```tsx
import { useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ClasslistPreviewRow, Student } from "../api/types";
import { Button } from "./Button";
import { Notice } from "./Notice";

const ISSUE: Record<string, string> = { missing_name: "Missing name", bad_reg_no: "Not a register number", duplicate_reg_no: "Duplicate register number" };

export function ClasslistImport({ classId, hasStudents, onSaved }: { classId: number; hasStudents: boolean; onSaved: (students: Student[], kept: number[]) => void }) {
  const [rows, setRows] = useState<ClasslistPreviewRow[] | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const pick = async (file: File) => {
    const form = new FormData(); form.append("file", file);
    setBusy(true);
    try { const p = await api.postForm<{ rows: ClasslistPreviewRow[]; errors: string[] }>(`/api/classes/${classId}/students/preview`, form); setRows(p.rows); setErrors(p.errors); }
    catch (e) { setErrors([e instanceof ApiError ? e.message : "Couldn't read that file."]); setRows(null); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    if (!rows) return;
    setBusy(true);
    try { const r = await api.put<{ students: Student[]; kept: number[] }>(`/api/classes/${classId}/students`, { rows: rows.map((x) => ({ reg_no: x.reg_no, name: x.name })) }); setRows(null); onSaved(r.students, r.kept); }
    catch (e) { setErrors([e instanceof ApiError ? e.message : "Couldn't save the classlist."]); }
    finally { setBusy(false); }
  };
  const clean = !!rows && rows.length > 0 && rows.every((r) => r.issues.length === 0);
  return (
    <div className="section">
      {!hasStudents && !rows && (
        <div className="empty">
          <h3>Upload the classlist</h3>
          <p className="help">A CSV with two columns: <code>name, reg_no</code> — one row per student. The header row can be in any case.</p>
        </div>
      )}
      <div className="actions">
        <Button variant={hasStudents ? "secondary" : "primary"} onClick={() => input.current?.click()} disabled={busy}>{hasStudents ? "Replace classlist" : "Choose CSV"}</Button>
        <input ref={input} type="file" accept=".csv,text/csv" hidden aria-label="Choose classlist file" onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f); e.target.value = ""; }} />
      </div>
      {errors.map((e) => <Notice key={e} kind="error">{e}</Notice>)}
      {rows && (
        <>
          <table className="table"><thead><tr><th className="num">#</th><th>Name</th><th>Issue</th></tr></thead>
            <tbody>{rows.map((r, i) => <tr key={i} className={r.issues.length ? "warn-note" : ""}><td className="num">{r.reg_no ?? r.raw_reg_no}</td><td>{r.name || "—"}</td><td>{r.issues.map((x) => ISSUE[x]).join(", ")}</td></tr>)}</tbody></table>
          <p className="help">{rows.length} student{rows.length === 1 ? "" : "s"}. {clean ? "Looks good." : "Fix the rows with issues in the file and upload it again."}</p>
          <div className="actions"><Button variant="primary" onClick={confirm} disabled={!clean || busy}>Confirm classlist</Button><Button variant="secondary" onClick={() => setRows(null)}>Cancel</Button></div>
        </>
      )}
    </div>
  );
}
```
`ClassPage.tsx`: loads `GET /api/classes/:id`; header with name, `code` in `.mono`, **Copy link** (`navigator.clipboard.writeText(`${window.location.origin}/c/${code}`)`, then show "Copied — Paste this into Google Classroom" for 3 s); tab bar (`.seg` buttons updating `?tab=`). **Students** tab: `ClasslistImport` + table `#, Name, Submissions, Last seen` (`fmtDate`), and a `Notice` when `kept.length` ("N students not in the file were kept because they have hand-ins"). **Assignments** tab: table `Title (link to /classes/:id/assignments/:caid), Status pill (Draft/Open/Marking/Released via derived_status; use StatusPill-like `.pill` classes: draft→pill-neutral, open→pill-open, marking→pill-ink, released→pill-outline), Due (fmtDate), Hand-ins (submission_count), actions: **Open** (draft → PUT status open), **Back to draft** (open with 0 hand-ins), **Delete** (0 hand-ins, confirm)`; **Set assignment** button → Dialog with `<select aria-label="Assignment from the bank">` listing `GET /api/assignments` (title · scheme label · marks), title input (defaults to the template title), `due_at` `<input type="datetime-local">` (convert to ISO with `new Date(v).toISOString()`), checkbox "Students can submit their own pages", **Set for this class** (POST). **Settings** tab: rename form, **Regenerate code** (Dialog "The old link stops working. Students who already entered their number stay signed in."), **Archive class** / **Unarchive**. Template-deleted rows show "Assignment deleted from the bank — set it again" in place of the link.

Reuse `.seg`/`.seg-opt` for tabs; add `.tabs { margin: 16px 0 24px; }` if needed.

- [ ] **Step 4: Run** `npx vitest run && npx tsc --noEmit && npm run build` → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): class page — classlist import with preview, assignments from the bank, settings"
```

---

### Task 9: Frontend — Class assignment page (progress strip, roster, upload, release, CSV)

**Files:**
- Create: `web/src/pages/ClassAssignmentPage.tsx`, `web/src/components/ProgressStrip.tsx`
- Modify: `web/src/App.tsx`, `web/src/styles/app.css`
- Test: `web/src/pages/__tests__/ClassAssignmentPage.test.tsx`

**Interfaces:** `ProgressStrip({ counts, filter, onFilter })` — five cells; `needs_you` cell amber when > 0. Roster status labels: `not_handed_in → "Not handed in"`, `handed_in → "Handed in"`, `marking → "Marking"`, `failed → "Marking failed"`, `needs_you → "Needs you · 1(a), 2"` (amber pill, link `/review?item=` is not available per part here — link the row to `/submissions/:id`), `ready → "Ready"`, `released → "Released"`.

- [ ] **Step 1: Write the failing tests**:
```tsx
const detail: ClassAssignmentDetail = { id: 3, class_id: 1, template_id: 7, title: "Quadratic equations — Worksheet 3", due_at: "2026-09-10T00:00:00Z", status: "open", derived_status: "marking", allow_student_uploads: true, released_at: null, template_deleted: false, subject: "math", scheme_kind: "mark_scheme", submission_count: 3, created_at: "", updated_at: "",
  roster: { counts: { not_handed_in: 1, handed_in: 0, marking: 1, needs_you: 1, ready: 1 }, rows: [
    { student_id: 1, reg_no: 1, name: "Tan Wei Ling", submission_id: 11, pages: 4, handed_in_at: "2026-09-09T13:02:00Z", late: false, source: "student", status: "needs_you", total: 15, total_upper: 17, total_max: 25, needs_you_parts: ["3"] },
    { student_id: 2, reg_no: 2, name: "Muhammad Danish", submission_id: 12, pages: 3, handed_in_at: "2026-09-11T01:00:00Z", late: true, source: "teacher", status: "ready", total: 21, total_upper: 21, total_max: 25, needs_you_parts: [] },
    { student_id: 3, reg_no: 3, name: "Priya Nair", submission_id: null, pages: 0, handed_in_at: null, late: false, source: null, status: "not_handed_in", total: null, total_upper: null, total_max: null, needs_you_parts: [] },
    { student_id: 4, reg_no: 4, name: "Lim Jun Hao", submission_id: 14, pages: 2, handed_in_at: "2026-09-09T13:02:00Z", late: false, source: "student", status: "marking", total: null, total_upper: null, total_max: null, needs_you_parts: [] },
  ] } };

it("renders the strip, filters the roster, and disables release while parts need you", async () => {
  mockFetch({ "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(detail), { status: 200 }) });
  render(app());
  expect(await screen.findByRole("heading", { name: "Quadratic equations — Worksheet 3" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Needs you/ })).toHaveTextContent("1");
  expect(screen.getByRole("button", { name: "Release feedback" })).toBeDisabled();
  expect(screen.getByText("Needs you · 3")).toBeInTheDocument();
  expect(screen.getByText("15–17 / 25")).toBeInTheDocument();
  expect(screen.getByText(/late/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Not handed in/ }));
  expect(screen.getAllByRole("row")).toHaveLength(2);
  expect(screen.getByRole("button", { name: "Upload pages" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Show all 4" }));
  expect(screen.getAllByRole("row")).toHaveLength(5);
});

it("releases feedback after confirming and downloads the CSV", async () => {
  const ready = { ...detail, derived_status: "open" as const, roster: { ...detail.roster, counts: { ...detail.roster.counts, needs_you: 0 }, rows: detail.roster.rows.map((r) => r.status === "needs_you" ? { ...r, status: "ready" as const, needs_you_parts: [] } : r) } };
  const calls = mockFetch({
    "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(ready), { status: 200 }),
    "POST /api/classes/1/assignments/3/release": () => new Response(JSON.stringify({ ...ready, status: "released", released_at: "2026-09-12T00:00:00Z" }), { status: 200 }),
  });
  render(app());
  await userEvent.click(await screen.findByRole("button", { name: "Release feedback" }));
  await userEvent.click(screen.getByRole("button", { name: "Release to students" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/release"))).toBe(true));
  expect(await screen.findByText(/Released/)).toBeInTheDocument();
});

it("uploads pages for a student who has not handed in", async () => {
  const calls = mockFetch({
    "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(detail), { status: 200 }),
    "POST /api/classes/1/assignments/3/students/3/upload": () => new Response(JSON.stringify({ id: 99, status: "queued", pages: [] }), { status: 202 }),
  });
  render(app());
  await userEvent.click(await screen.findByRole("button", { name: "Upload pages" }));
  const input = screen.getByLabelText("Choose pages for Priya Nair") as HTMLInputElement;
  await userEvent.upload(input, [new File(["x"], "p1.png", { type: "image/png" })]);
  await userEvent.click(screen.getByRole("button", { name: "Start marking" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/students/3/upload"))).toBe(true));
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** `ProgressStrip.tsx` (five `<button className="strip-cell">` with `<strong>{n}</strong><span>{label}</span>`, `aria-pressed` for the active filter, `.strip-cell.amber` for needs_you > 0) and `ClassAssignmentPage.tsx`:
- Loads `GET /api/classes/:id/assignments/:caid`; polls every 10 s while any row is `handed_in`/`marking`.
- Header: breadcrumb `← {class name}` (`GET /api/classes/:id`), title, meta "Due {fmtDate} · {counts total} students", status pill from `derived_status`.
- Actions: **Download marks CSV** (`downloadFile(`/api/classes/${id}/assignments/${caid}/marks.csv`, "marks.csv")`), **Download marking records** (`POST /api/submissions/records.zip {ids}` for rows with a `run`-able status `needs_you|ready|released`, via `downloadFile(..., "marking-records.zip", { ids })`), **Release feedback** (disabled when `counts.needs_you > 0` or `status === "released"` or no marked rows; title attribute explains), Dialog "Release feedback to students?" with body "Students will see their marks and feedback. Anyone who hands in later is marked and shown feedback automatically." and **Release to students**.
- Strip filter state; "Showing N students with …" + **Show all N** button when filtered.
- Roster table `#, Name, Pages, Handed in (fmtDate + " · late" muted span, or "Uploaded by you" when source teacher), Status, Total (totalLabel from lib/marks; "—" when null), →`. Row click → `/submissions/:submission_id` when present. `not_handed_in` rows show **Upload pages** → Dialog with `DropZone`-like file input labelled `Choose pages for {name}` + **Start marking** (postForm `files`). Rows with a hand-in have a tertiary **Remove hand-in** (Dialog confirm) → `DELETE .../students/{sid}/submission` then reload.
- After release the status pill says **Released** and the release button is hidden.

CSS: `.strip { display: grid; grid-template-columns: repeat(5, 1fr); border: 2px solid var(--color-divider); margin: 24px 0; } .strip-cell { all: unset; cursor: pointer; padding: 20px 16px; border-right: 2px solid var(--color-divider); min-height: 44px; } .strip-cell:last-child { border-right: 0 } .strip-cell strong { display: block; font-size: 32px; } .strip-cell[aria-pressed="true"] { box-shadow: inset 0 -3px 0 var(--ink); } .strip-cell.amber { background: var(--color-amber-100, #fff4d6); } @media (max-width: 700px) { .strip { grid-template-columns: repeat(2, 1fr); } }`. Check `tokens.css` for the amber token name and use it.

- [ ] **Step 4: Run** frontend checks → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): class assignment page — progress strip, roster, per-student upload, release, marks CSV"
```

---

### Task 10: Student frontend — layout, enter number, confirm, home

**Files:**
- Create: `web/src/student/StudentLayout.tsx`, `web/src/student/Enter.tsx`, `web/src/student/Confirm.tsx`, `web/src/student/Home.tsx`, `web/src/student/api.ts`
- Modify: `web/src/App.tsx`, `web/src/styles/app.css`
- Test: `web/src/student/__tests__/Enter.test.tsx`, `Home.test.tsx`

**Interfaces:**
- `student/api.ts`: `parseStudentId(text: string): { code: string; reg_no: number } | null` (accepts `CE4R-12`, `ce4r 12`, `CE4R–12`; code = 4 chars of the alphabet upper-cased, reg_no positive int), `CODE_ALPHABET` regex `/^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/`, and `studentApi` = the same `api` client (cookies are same-origin).
- Routes (outside the teacher `Shell`): `/c/:code` → `Enter` (code pre-filled, number input only), `/join` → `Enter` (single input for the whole ID), `/s/confirm` → `Confirm` (state passed via `location.state` `{code, reg_no, student_name, class_name}`; redirect to `/join` if missing), `/s` → `Home`, `/s/a/:caid/hand-in` and `/s/a/:caid` (Tasks 11–12). `/s/*` routes are wrapped in `StudentLayout`, which calls `GET /api/student/me`; 401 → `<Navigate to="/join" />`.
- `StudentLayout`: header row — brand "Smart Marking" small, right side `{student_name} · #{reg_no}` and a **Not me?** button (`DELETE /api/student/session` → `/join`); `<Outlet context={{ me }} />`; wrapper `.student` sets `max-width: 480px; margin: 0 auto; padding: 16px; font-size: 17px;` and buttons `min-height: 48px; width: 100%`.

- [ ] **Step 1: Write the failing tests**

`Enter.test.tsx`:
```tsx
it("pre-fills the code from the link and looks the number up", async () => {
  const calls = mockFetch({ "POST /api/student/lookup": () => new Response(JSON.stringify({ class_name: "4E2", code: "CE4R", student_name: "Tan Wei Ling", reg_no: 1 }), { status: 200 }) });
  render(<MemoryRouter initialEntries={["/c/ce4r"]}><Routes><Route path="/c/:code" element={<Enter />} /><Route path="/s/confirm" element={<p>confirm page</p>} /></Routes></MemoryRouter>);
  expect(screen.getByText("CE4R-")).toBeInTheDocument();
  const input = screen.getByLabelText("Your register number");
  expect(input).toHaveAttribute("inputmode", "numeric");
  await userEvent.type(input, "1");
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByText("confirm page")).toBeInTheDocument();
  expect(calls[0]).toEqual({ path: "/api/student/lookup", method: "POST" });
});

it("shows the server's plain-words error", async () => {
  mockFetch({ "POST /api/student/lookup": () => new Response(JSON.stringify({ error: { code: "no_such_student", message: "No student #37 in this class — check the number on your class list" } }), { status: 404 }) });
  render(<MemoryRouter initialEntries={["/c/CE4R"]}><Routes><Route path="/c/:code" element={<Enter />} /></Routes></MemoryRouter>);
  await userEvent.type(screen.getByLabelText("Your register number"), "37");
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("No student #37 in this class");
});

it("/join takes the whole ID", async () => {
  mockFetch({ "POST /api/student/lookup": (init) => { expect(JSON.parse(String(init?.body))).toEqual({ code: "CE4R", reg_no: 12 }); return new Response(JSON.stringify({ class_name: "4E2", code: "CE4R", student_name: "Lim", reg_no: 12 }), { status: 200 }); } });
  render(<MemoryRouter initialEntries={["/join"]}><Routes><Route path="/join" element={<Enter />} /><Route path="/s/confirm" element={<p>confirm page</p>} /></Routes></MemoryRouter>);
  await userEvent.type(screen.getByLabelText("Your student ID"), "ce4r-12");
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByText("confirm page")).toBeInTheDocument();
});
```
`Home.test.tsx`: mock `GET /api/student/me` and `GET /api/student/assignments` with four statuses; assert each renders its label — "To hand in" (a link to `/s/a/1/hand-in`), "Handed in · marking", "Marked — your teacher is checking", "Feedback ready" (link to `/s/a/4`) — and that the header shows "Tan Wei Ling · #1". Confirm test: renders "Are you Tan Wei Ling, #1 of 4E2?"; **Yes, that's me** posts `/api/student/session` then navigates to `/s`; **Not me** goes back to `/c/CE4R`.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** the four files. `Enter`:
```tsx
export function Enter() {
  const { code: codeParam } = useParams();
  const nav = useNavigate();
  const fixed = codeParam ? codeParam.toUpperCase() : null;
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const id = fixed ? parseStudentId(`${fixed}-${value}`) : parseStudentId(value);
    if (!id) { setError(fixed ? "Type your register number — just the number." : "Type your ID like CE4R-12."); return; }
    setBusy(true); setError(null);
    try {
      const me = await api.post<StudentMe>("/api/student/lookup", id);
      nav("/s/confirm", { state: { ...id, ...me } });
    } catch (err) { setError(err instanceof ApiError ? err.message : "Can't reach Smart Marking — check your signal and try again."); }
    finally { setBusy(false); }
  };
  return (
    <div className="student">
      <h1>Enter your number</h1>
      <form onSubmit={submit}>
        {fixed ? (
          <div className="student-id"><span className="student-id-prefix">{fixed}-</span>
            <input aria-label="Your register number" className="input" inputMode="numeric" pattern="[0-9]*" autoFocus value={value} onChange={(e) => setValue(e.target.value.replace(/\D/g, ""))} /></div>
        ) : (
          <div className="field"><label htmlFor="sid">Your student ID</label><input id="sid" className="input" autoFocus placeholder="CE4R-12" value={value} onChange={(e) => setValue(e.target.value)} /></div>
        )}
        {error && <p role="alert" className="notice notice-error">{error}</p>}
        <button className="btn btn-primary btn-lg" disabled={busy || !value.trim()}>Continue</button>
      </form>
      <p className="help">Your teacher shared a link and your register number is on the class list.</p>
    </div>
  );
}
```
`Confirm`: reads `location.state`; posts `/api/student/session {code, reg_no}` on **Yes, that's me** → `nav("/s")`; **Not me** → `nav(`/c/${code}`)`. `Home`: `useOutletContext<{ me: StudentMe }>()`; lists assignments; each item is a `.student-card` with title, "Due {fmtDate}" and the status control: `to_hand_in` → `<Link className="btn btn-primary" to=/s/a/:id/hand-in>To hand in</Link>` (or muted "Hand-ins closed" when `!allow_student_uploads`), `handed_in` → `<Link to=/s/a/:id>Handed in · marking</Link>`, `checking` → "Marked — your teacher is checking", `feedback_ready` → `<Link className="btn btn-primary">Feedback ready</Link>`. Empty state: "No assignments yet — check back when your teacher sets one."

App.tsx: add `<Route path="/c/:code" element={<Enter />} /><Route path="/join" element={<Enter />} /><Route path="/s/confirm" element={<Confirm />} /><Route path="/s" element={<StudentLayout />}><Route index element={<Home />} />…</Route>` **before** the teacher `Shell` route; the `*` fallback stays on the teacher side.

CSS (`app.css`, appended):
```css
.student { max-width: 480px; margin: 0 auto; padding: 16px 16px 48px; font-size: 17px; }
.student h1 { font-size: 28px; margin: 8px 0 16px; }
.student .btn { min-height: 48px; width: 100%; justify-content: center; font-size: 17px; }
.student-header { display: flex; justify-content: space-between; align-items: center; min-height: 48px; font-size: 15px; }
.student-id { display: flex; align-items: center; gap: 8px; }
.student-id-prefix { font-family: var(--font-mono, monospace); font-size: 24px; font-weight: 700; }
.student-id .input { font-size: 24px; min-height: 56px; flex: 1; }
.student-card { border: 2px solid var(--color-divider); padding: 16px; margin: 12px 0; }
.student-card h2 { font-size: 18px; margin: 0 0 4px; }
```

- [ ] **Step 4: Run** frontend checks → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(student): enter number, confirm, home on the phone"
```

---

### Task 11: Student frontend — hand in (camera/gallery, reorder, downscale, retry)

**Files:**
- Create: `web/src/lib/image.ts`, `web/src/student/HandIn.tsx`
- Modify: `web/src/App.tsx`
- Test: `web/src/lib/__tests__/image.test.ts`, `web/src/student/__tests__/HandIn.test.tsx`

**Interfaces:**
- `lib/image.ts`: `export async function downscale(file: File, maxEdge = 2000, quality = 0.85): Promise<File>` — for `image/jpeg|png|webp` files draw onto a canvas no larger than `maxEdge` on the long edge and return a JPEG `File` named `<basename>.jpg`; other types (PDF, HEIC, unknown) are returned unchanged. Uses `createImageBitmap` when available, else an `<img>` + object URL. Any failure returns the original file.
- `HandIn` route `/s/a/:caid/hand-in`: state `{ pages: { id: string; file: File; url: string }[] }`; controls: **Take photo** (`<input type=file accept="image/*" capture="environment">`), **Choose from gallery** (`accept="image/*,.pdf,.heic,.heif" multiple`); thumbnail list with **Move up / Move down / Delete** buttons (≥ 44 px) and the page number; **Hand in N pages** → `downscale` each → `FormData` `files` → `POST /api/student/assignments/{caid}/hand-in`; on success show the done state "Handed in {fmtDate(now)}" with a link **Back to assignments**; on failure keep the pages and show "Couldn't hand in — check your signal and try again." + **Try again**. If the page loads for an assignment whose status is not `to_hand_in`, redirect to `/s/a/:caid`.

- [ ] **Step 1: Write the failing tests**

`image.test.ts`: `downscale(new File(["%PDF"], "a.pdf", { type: "application/pdf" }))` resolves to the same file; a `image/png` file in jsdom (no canvas) resolves to the original file (the fallback path) — assert it does not throw and returns a `File`.

`HandIn.test.tsx`:
```tsx
it("orders pages, hands them in, and keeps them when the upload fails", async () => {
  let fail = true;
  const calls = mockFetch({
    "GET /api/student/me": () => new Response(JSON.stringify(me), { status: 200 }),
    "GET /api/student/assignments/1": () => new Response(JSON.stringify({ id: 1, title: "Worksheet 3", due_at: null, status: "to_hand_in", handed_in_at: null, pages: 0, allow_student_uploads: true, feedback: null }), { status: 200 }),
    "POST /api/student/assignments/1/hand-in": () => fail ? new Response("", { status: 0 }) : new Response(JSON.stringify({ id: 5, status: "queued", pages: [] }), { status: 202 }),
  });
  vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:x", revokeObjectURL: () => {} });
  render(app("/s/a/1/hand-in"));
  const gallery = await screen.findByLabelText("Choose from gallery");
  await userEvent.upload(gallery, [new File(["a"], "a.jpg", { type: "image/jpeg" }), new File(["b"], "b.jpg", { type: "image/jpeg" })]);
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  await userEvent.click(screen.getAllByRole("button", { name: "Move up" })[1]);
  expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("b.jpg");
  await userEvent.click(screen.getByRole("button", { name: "Hand in 2 pages" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't hand in");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  fail = false;
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText(/Handed in/)).toBeInTheDocument();
  expect(calls.filter((c) => c.method === "POST").length).toBe(2);
});
```
(`new Response("", { status: 0 })` may throw in jsdom; if so, make the handler `throw new TypeError("Failed to fetch")` instead — the page must treat a thrown fetch as the offline case.)

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** `lib/image.ts`:
```ts
const RESIZABLE = new Set(["image/jpeg", "image/png", "image/webp"]);

export async function downscale(file: File, maxEdge = 2000, quality = 0.85): Promise<File> {
  if (!RESIZABLE.has(file.type)) return file;
  try {
    const bitmap = await loadBitmap(file);
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
    const w = Math.round(bitmap.width * scale), h = Math.round(bitmap.height * scale);
    const canvas = document.createElement("canvas"); canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext("2d"); if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, w, h);
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/jpeg", quality));
    if (!blob) return file;
    return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch { return file; }
}

async function loadBitmap(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if (typeof createImageBitmap === "function") return createImageBitmap(file);
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file); const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("decode failed")); };
    img.src = url;
  });
}
```
`HandIn.tsx` as specified above; the list is `<ol>` of `<li>` with `<img src={url} alt="">` (or the filename for PDFs/HEIC via `canThumbnail` from `lib/files.ts`), filename in a `.help` span, and the three buttons. Hand-in error handling: `catch (e) { setError(e instanceof ApiError ? e.message : "Couldn't hand in — check your signal and try again."); }` and a **Try again** button that re-runs the same submit. Register the route inside the `/s` layout.

- [ ] **Step 4: Run** frontend checks → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(student): hand in pages from camera or gallery with reorder, downscale and retry"
```

---

### Task 12: Student frontend — waiting and feedback screens

**Files:**
- Create: `web/src/student/AssignmentView.tsx`
- Modify: `web/src/App.tsx`, `web/src/styles/app.css`
- Test: `web/src/student/__tests__/AssignmentView.test.tsx`

**Interfaces:** route `/s/a/:caid` → `AssignmentView`: `GET /api/student/assignments/:caid`; `to_hand_in` → redirect to hand-in; `handed_in` → "Handed in {fmtDate}. Marking usually takes a day. We'll show your feedback here." (no spinner); `checking` → "Marked — your teacher is checking. Come back when your teacher releases the feedback."; `feedback_ready` → feedback layout (S6–S9).

- [ ] **Step 1: Write the failing tests**:
```tsx
it("shows the calm waiting state", async () => {
  mockFetch({ "GET /api/student/me": () => ok(me), "GET /api/student/assignments/1": () => ok({ id: 1, title: "Worksheet 3", due_at: null, status: "handed_in", handed_in_at: "2026-09-09T07:12:00Z", pages: 4, allow_student_uploads: true, feedback: null }) });
  render(app("/s/a/1"));
  expect(await screen.findByText(/Marking usually takes a day/)).toBeInTheDocument();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});

it("renders released feedback in order and expands a question", async () => {
  const fb = { summary: "You factorise confidently.", strengths: ["Q1 both factors correct"], improvement_plan: ["Check signs"], next_steps: ["Redo Q3"], total: 18, max: 25,
    questions: [{ label: "1(a)", mark: 4, max: 4, comment: "Clear.", try_next: "Keep going.", transcription: "x = 3" }, { label: "3", mark: 3, max: 5, comment: "Sign slip.", try_next: "Try the formula again.", transcription: "x = -2" }], pages: [7] };
  mockFetch({ "GET /api/student/me": () => ok(me), "GET /api/student/assignments/1": () => ok({ id: 1, title: "Worksheet 3", due_at: null, status: "feedback_ready", handed_in_at: "2026-09-09T07:12:00Z", pages: 1, allow_student_uploads: true, feedback: fb }) });
  render(app("/s/a/1"));
  expect(await screen.findByText("18")).toBeInTheDocument();
  expect(screen.getByText("/ 25")).toBeInTheDocument();
  const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
  expect(headings).toEqual(["What you did well", "Question by question", "Work on next", "Next steps"]);
  await userEvent.click(screen.getByRole("button", { name: /3 · 3 \/ 5/ }));
  expect(screen.getByText("Sign slip.")).toBeInTheDocument();
  expect(screen.getByText(/Try next: Try the formula again/)).toBeInTheDocument();
  expect(screen.getByText("x = -2")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Your page 1" })).toHaveAttribute("src", "/api/student/pages/7");
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** `AssignmentView.tsx`: total block (`<div className="student-total"><span className="big">18</span><span className="muted">/ 25</span></div>` + a `.blocks` bar of `max` squares with `total` filled, `aria-hidden`), summary paragraph, then four sections with `<h2>`; each question is a `.qrow` `<button aria-expanded>` with `{label} · {mark} / {max}` and the expanded `.qrow-body` shows comment, "Try next: …", the transcription in a `.callout` (label "What we read from your page"), and, if `pages.length`, the page images `<img alt="Your page N" src="/api/student/pages/{id}">` under the question list (once, not per question). Questions with no comment show "No comment for this question." Waiting/checking states as above with **Back to assignments** link.

CSS: `.student-total { display: flex; align-items: baseline; gap: 8px; margin: 8px 0; } .student-total .big { font-size: 56px; font-weight: 800; } .blocks { display: flex; flex-wrap: wrap; gap: 3px; margin: 8px 0 16px; } .blocks i { width: 12px; height: 12px; background: var(--color-neutral-300); } .blocks i.on { background: var(--ink); } .student section { margin-top: 24px; } .student h2 { font-size: 20px; }`.

- [ ] **Step 4: Run** frontend checks → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(student): waiting state and released feedback screen"
```

---

### Task 13: README, Postgres smoke, final checks

**Files:**
- Modify: `README.md`, `tests/postgres/test_postgres_smoke.py`

- [ ] **Step 1: Postgres smoke** — add a test that inserts a class + student, two submissions for the same `(class_assignment_id, student_id)` and asserts the second raises `IntegrityError`; clean up rows in a `finally`. Skips without `SMS_TEST_DATABASE_URL` like the others.

- [ ] **Step 2: README** — under **Web app** add a **Classes and student hand-in** paragraph: create a class → upload the classlist CSV (`name, reg_no`) → **Copy link** (`/c/CODE`) into Google Classroom → set an assignment from the bank with a due date → students open the link, type their number, photograph pages and hand in → marking runs as usual → clear **Review** → **Release feedback** → students see marks and feedback; **Download marks CSV**. Note there is no student password (class code + register number is the accepted trade-off) and that a teacher can **Remove hand-in** so a student can redo it. Update the roadmap: move "Classes and students" and "Student phone flow" to done; keep the page sorter.

- [ ] **Step 3: Full verification** — `uv run pytest -q`; `cd web && npx vitest run && npx tsc --noEmit && npm run build`; then run the app locally (`SECRET_KEY=dev TEACHER_PASSWORD=dev uv run sms serve`) and click through: create class → CSV → set assignment → open → `/c/CODE` on a 375 px viewport → hand in a PNG → roster shows Handed in.

- [ ] **Step 4: Commit**

```bash
git add README.md tests/postgres/test_postgres_smoke.py
git commit -m "docs: classes and student hand-in; postgres smoke for the hand-in unique index"
```

---

## Self-review

- **Spec coverage**: §1 → T1/T3; §2 → T5; §3 (all routes) → T1–T4; §4 → T6; §5 rules → T3 (once, remove), T4 (release gate, late), T6 (draft invisible, closed uploads, checking vs ready); §6 → T7–T9; §7 → T3; §8 → T10–T12; §9 → tests in every task + T13 Postgres; README → T13. Not covered on purpose: student "blur hint" (out of scope in §10).
- **Type consistency**: `roster()` is `roster(db, ca)` everywhere (no `jobs`); `marks_csv(db, jobs, ca)`; `hand_in(db, storage, jobs, *, ca, student, files, source)`; student status strings match between `services/student.py` and `types.ts`; roster status strings match `RosterStatus`.
- **Placeholders**: none — every step has its code or exact behaviour.

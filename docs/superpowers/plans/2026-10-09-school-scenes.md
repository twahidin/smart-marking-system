# School Scenes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a painted, interactive scene at the top of Classes (the school, built from classroom tiles), Assignments (the teacher's desk), Review (the marking desk) and Learning (the library), each a real control surface over the page's existing list, with hover/tap labels, a Show labels switch, a 3 s Tour, CSS ambient effects, one-shot cues and optional film loops.

**Architecture:** One shared `Scene` component in `web/src/scene/` owns labels, tour, film and cues over a still painting; each page passes it hotspots and effects derived from data it already loads plus three small new routes (class subject and counts, a review summary, a due list). Classes renders a `ClassTile` per live class instead of a card. Art and film loops are already committed under `web/public/art/`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core, Alembic, pytest; React 18, TypeScript, react-router 6, vitest + testing-library; CSS keyframes only (no new libraries).

**Spec:** `docs/superpowers/specs/2026-10-09-school-scenes-design.md`

## Global Constraints

- No new npm or Python dependencies. Motion is CSS keyframes and `<video>` only; no three.js, no Lottie.
- Every effect element is `aria-hidden="true"` and is not rendered on the `static` tier (`useDeviceTier()` returns `"static"` under `prefers-reduced-motion`). The film `<video>` is never rendered on the `static` tier.
- Every hotspot is a real `<button type="button">` or a `<Link>` with an accessible name; a label that is hidden is still in the DOM (opacity 0), so screen readers read the hotspot's `aria-label`, never the label text twice (labels are `aria-hidden`).
- Show labels is stored in `localStorage` under `sms.scene.labels` as `"on"` or `"off"`; Film is stored in `sessionStorage` under `sms.scene.film` as `"off"` when switched off. Every storage read and write is wrapped in try/catch.
- Tour: 3000 ms per hotspot, once round, then off; its interval is cleared on stop and on unmount.
- Subject colours (add to `web/src/lib/format.ts`): `math` `var(--crew-marker)`, `language` `var(--mint)`, `science` `var(--gold)`, `mt` `var(--lilac)`, `computing` `var(--sky)`; tokens `--lilac: #C9A7E8` and `--sky: #8FB8E8` are added to `tokens.css`.
- Every new SQL runs on SQLite and Postgres: no `boolean = 1`, no string comparison against DateTime columns (filter dates in Python); extend `tests/unit/test_migrations_postgres.py` and run it against a local Postgres before the final review (`SMS_TEST_PG_URL=postgresql+psycopg://sms@127.0.0.1:54329/smstest`; recipe in `tests/unit/test_migrations_postgres.py`'s docstring).
- Existing behaviour stays: every column, action, dialog and keyboard shortcut on the four pages keeps working; the tests that exist for them must keep passing untouched except where this plan says to extend them.
- Copy: "Build a classroom" is New class; "Your school", "Your desk", "The marking desk", "The library" are the page titles; crew names stay Reader / Marker / Checker.
- Commits end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Backend tests: `uv run python -m pytest -q`; web: `cd web && npx vitest run && npx tsc --noEmit`.

---

## File structure

**Backend (new)**
- `src/sms/migrations/versions/0015_class_subject.py` — `classes.subject TEXT NULL`.
- `src/sms/web/services/scenes.py` — `review_summary(db)` and `due_class_assignments(db, days)`.
- `src/sms/web/routers/scenes.py` — `GET /api/review/summary`, `GET /api/class-assignments/due`.

**Backend (modified)**
- `src/sms/web/services/classes.py` — `_SELECT` gains derived `subject`, `marking`, `needs_you`; `create_class(db, name, subject=None)`; `update_class(db, class_id, *, name, subject)`; `clean_subject()`.
- `src/sms/web/routers/classes.py` — `ClassBody.subject`, PUT calls `update_class`.
- `src/sms/web/app.py` — include `scenes.router`.

**Web (new)**
- `web/src/scene/art.ts` — `ART`, `FILM`, `SUBJECT_TILE` paths.
- `web/src/scene/useSceneLabels.ts`, `web/src/scene/useTour.ts`, `web/src/scene/useFilm.ts`.
- `web/src/scene/Scene.tsx` — the shared scene card.
- `web/src/scene/effects.tsx` — `Glow`, `Flag`, `Dots`, `Paper`, `Stamp`, `Tick`, `Book`, `Star`.
- `web/src/scene/ClassTile.tsx` — one classroom tile.
- Tests under `web/src/scene/__tests__/` and the four page tests.

**Web (modified)**
- `web/src/api/types.ts` — `ClassRow.subject/marking/needs_you`, `ReviewSummary`, `DueClassAssignment`.
- `web/src/lib/format.ts` — `subjectColor`.
- `web/src/styles/tokens.css`, `web/src/styles/app.css` — tokens, `.scene*`, `.tile*`, `.fx*`, keyframes.
- `web/src/pages/Classes.tsx`, `ClassPage.tsx`, `Assignments.tsx`, `Review.tsx`, `Learning.tsx`.
- `web/src/components/CorrectionsTab.tsx` — optional `onReleased` prop.

**Art (already committed before Task 1)**
- `web/public/art/tile-{math,language,science,mt,computing,general}.jpg` (1024², cream background `#FFF7E6`), `desk.jpg`, `review.jpg`, `library.jpg`, `school.jpg` (1400 px wide, 4:3).
- `web/public/art/film/{desk,review,library,tile-math,tile-language,tile-science,tile-mt,tile-computing,tile-general}.mp4` (5 s, 1040 px wide, H.264, no audio, each under 300 KB).

---

### Task 1: Migration 0015 and class subject, marking and needs-you counts

**Files:**
- Create: `src/sms/migrations/versions/0015_class_subject.py`
- Modify: `src/sms/web/services/classes.py:30-78`
- Modify: `src/sms/web/routers/classes.py:16-46`
- Test: `tests/unit/test_migration_0015.py`, `tests/web/test_classes_api.py`, `tests/unit/test_migrations_postgres.py`

**Interfaces:**
- Consumes: `classes`, `class_assignments`, `assignment_templates`, `submissions` tables; `SubjectRouter.KNOWN_SUBJECTS` from `sms.pipeline.router`.
- Produces: class rows with `subject: str | None`, `marking: int`, `needs_you: int`; `create_class(db, name, subject=None)`; `update_class(db, class_id, *, name, subject)`; `clean_subject(value) -> str | None` raising `ApiError(400, "bad_subject", ...)`.

- [ ] **Step 1: Write the failing migration test**

```python
# tests/unit/test_migration_0015.py
from sqlalchemy import inspect

from sms.memory.db import Database


def test_0015_adds_a_nullable_subject_to_classes(tmp_path):
    db = Database(path=str(tmp_path / "m.db"))
    cols = {c["name"]: c for c in inspect(db.engine).get_columns("classes")}
    assert "subject" in cols and cols["subject"]["nullable"] is True
    cid = db.insert("INSERT INTO classes (name, code) VALUES ('4E2', 'ABCD') RETURNING id")
    assert db.query("SELECT subject FROM classes WHERE id = :i", {"i": cid})[0]["subject"] is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run python -m pytest tests/unit/test_migration_0015.py -q`
Expected: FAIL with `assert 'subject' in cols`.

- [ ] **Step 3: Write the migration**

```python
# src/sms/migrations/versions/0015_class_subject.py
"""A class can carry a subject so the school draws the right classroom tile.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("classes") as b:
        b.add_column(sa.Column("subject", sa.Text))   # NULL = derive from the latest class assignment


def downgrade() -> None:
    with op.batch_alter_table("classes") as b:
        b.drop_column("subject")
```

- [ ] **Step 4: Run the migration test and the Postgres chain test**

Run: `uv run python -m pytest tests/unit/test_migration_0015.py -q`
Expected: PASS.

Edit `tests/unit/test_migrations_postgres.py`: change the two `== "0014"` assertions to `== "0015"` and add:

```python
def test_0015_subject_is_nullable_on_postgres(pg_engine):
    upgrade(pg_engine, "head")
    with pg_engine.begin() as conn:
        conn.execute(text("INSERT INTO classes (id, name, code) VALUES (1, '4E2', 'ABCD')"))
        assert conn.execute(text("SELECT subject FROM classes WHERE id = 1")).scalar() is None
        conn.execute(text("UPDATE classes SET subject = 'math' WHERE id = 1"))
```

Run (with a scratch Postgres up): `SMS_TEST_PG_URL=postgresql+psycopg://sms@127.0.0.1:54329/smstest uv run python -m pytest tests/unit/test_migrations_postgres.py -q`
Expected: PASS (or SKIPPED when the URL is not set; the final review runs it for real).

- [ ] **Step 5: Write the failing API tests**

Append to `tests/web/test_classes_api.py`:

```python
def _template(auth, subject="math"):
    return auth.post("/api/assignments", json={"title": f"{subject} paper", "subject": subject, "context": "", "rubric": {"criterion_defs": []},
                                               "scheme_kind": "criteria", "questions": [], "scheme": []}).json()


def test_subject_is_saved_validated_or_derived_from_the_latest_class_assignment(auth):
    c = auth.post("/api/classes", json={"name": "4E2 Mathematics", "subject": "math"}).json()
    assert c["subject"] == "math" and c["marking"] == 0 and c["needs_you"] == 0
    assert auth.post("/api/classes", json={"name": "X", "subject": "art"}).json()["error"]["code"] == "bad_subject"
    d = auth.post("/api/classes", json={"name": "2E3"}).json()
    assert d["subject"] is None
    t_sci = _template(auth, "science"); t_eng = _template(auth, "language")
    auth.post(f"/api/classes/{d['id']}/assignments", json={"template_id": t_sci["id"]})
    auth.post(f"/api/classes/{d['id']}/assignments", json={"template_id": t_eng["id"]})
    assert auth.get(f"/api/classes/{d['id']}").json()["subject"] == "language"   # the latest set wins
    assert auth.put(f"/api/classes/{d['id']}", json={"name": "2E3", "subject": "science"}).json()["subject"] == "science"
    assert auth.put(f"/api/classes/{d['id']}", json={"name": "2E3 Sci"}).json()["subject"] == "science"   # name-only keeps it
    assert auth.put(f"/api/classes/{d['id']}", json={"name": "2E3 Sci", "subject": None}).json()["subject"] == "language"  # back to derived


def test_marking_and_needs_you_count_this_class_only(auth, app):
    from tests.web.seed_v2 import seed_v2
    t = _template(auth)
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    other = auth.post("/api/classes", json={"name": "3N1"}).json()
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    ca2 = auth.post(f"/api/classes/{other['id']}/assignments", json={"template_id": t["id"]}).json()
    a, _ = seed_v2(app, run_id="r-1", queue={}); b, _ = seed_v2(app, run_id="r-2", queue={}); x, _ = seed_v2(app, run_id="r-3", queue={})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :ca, status = 'marking' WHERE id = :i", {"ca": ca["id"], "i": a})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :ca, status = 'needs_you' WHERE id = :i", {"ca": ca["id"], "i": b})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :ca, status = 'queued' WHERE id = :i", {"ca": ca2["id"], "i": x})
    rows = {r["name"]: r for r in auth.get("/api/classes").json()}
    assert (rows["4E2"]["marking"], rows["4E2"]["needs_you"]) == (1, 1)
    assert (rows["3N1"]["marking"], rows["3N1"]["needs_you"]) == (1, 0)
```

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run python -m pytest tests/web/test_classes_api.py -q -k "subject or marking"`
Expected: FAIL (`subject` missing from the row, 422 on the unknown field is not raised because pydantic ignores extras, so the first assertion fails on `KeyError: 'subject'`).

- [ ] **Step 7: Extend the service**

In `src/sms/web/services/classes.py` replace `_SELECT`, `_row`, `create_class` and `rename_class` with:

```python
from sms.pipeline.router import SubjectRouter

_SELECT = (
    "SELECT c.*, "
    "(SELECT COUNT(*) FROM students s WHERE s.class_id = c.id) AS student_count, "
    "(SELECT COUNT(*) FROM class_assignments a WHERE a.class_id = c.id AND a.status = 'open') AS open_assignments, "
    "COALESCE(c.subject, (SELECT t.subject FROM class_assignments a JOIN assignment_templates t ON t.id = a.template_id "
    "                     WHERE a.class_id = c.id ORDER BY a.id DESC LIMIT 1)) AS shown_subject, "
    "(SELECT COUNT(*) FROM submissions s JOIN class_assignments a ON a.id = s.class_assignment_id "
    " WHERE a.class_id = c.id AND s.status IN ('uploaded', 'queued', 'marking')) AS marking, "
    "(SELECT COUNT(*) FROM submissions s JOIN class_assignments a ON a.id = s.class_assignment_id "
    " WHERE a.class_id = c.id AND s.status = 'needs_you') AS needs_you "
    "FROM classes c")


def _row(r: dict) -> Dict[str, Any]:
    return {
        "id": r["id"], "name": r["name"], "code": r["code"],
        "student_count": int(r["student_count"] or 0), "open_assignments": int(r["open_assignments"] or 0),
        "subject": r["shown_subject"], "marking": int(r["marking"] or 0), "needs_you": int(r["needs_you"] or 0),
        "archived_at": iso_utc(r["archived_at"]),
        "created_at": iso_utc(r["created_at"]), "updated_at": iso_utc(r["updated_at"]),
    }


def clean_subject(value: Optional[str]) -> Optional[str]:
    """None or '' clears the saved subject (the tile then follows the latest class assignment)."""
    if value is None or value == "":
        return None
    if value not in SubjectRouter.KNOWN_SUBJECTS:
        raise ApiError(400, "bad_subject", f"Unknown subject: {value}")
    return value


def create_class(db: Database, name: str, subject: Optional[str] = None) -> Dict[str, Any]:
    cid = db.insert("INSERT INTO classes (name, code, subject) VALUES (:n, :c, :s) RETURNING id",
                    {"n": _clean_name(name), "c": unique_code(db), "s": clean_subject(subject)})
    return get_class(db, cid)  # type: ignore[return-value]


_KEEP: Any = object()


def update_class(db: Database, class_id: int, *, name: str, subject: Any = _KEEP) -> Dict[str, Any]:
    """Rename, and set or clear the subject when the caller sent one (absent = keep)."""
    _require(db, class_id)
    if subject is _KEEP:
        db.execute("UPDATE classes SET name = :n, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                   {"n": _clean_name(name), "id": class_id})
    else:
        db.execute("UPDATE classes SET name = :n, subject = :s, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                   {"n": _clean_name(name), "s": clean_subject(subject), "id": class_id})
    return get_class(db, class_id)  # type: ignore[return-value]


rename_class = update_class   # older callers and tests
```

In `src/sms/web/routers/classes.py`:

```python
class ClassBody(BaseModel):
    name: str
    subject: Optional[str] = None


class ClassEditBody(BaseModel):
    name: str
    # pydantic keeps "sent as null" apart from "absent" through model_fields_set
    subject: Optional[str] = None


@router.post("", status_code=201)
def create(body: ClassBody, db=Depends(get_db)):
    return create_class(db, body.name, body.subject)


@router.put("/{class_id}")
def rename(class_id: int, body: ClassEditBody, db=Depends(get_db)):
    if "subject" in body.model_fields_set:
        return update_class(db, class_id, name=body.name, subject=body.subject)
    return update_class(db, class_id, name=body.name)
```

Update the import line to `from sms.web.services.classes import (create_class, get_class, list_classes, regenerate_code, set_archived, update_class)` and add `from typing import Optional`.

- [ ] **Step 8: Run the class tests**

Run: `uv run python -m pytest tests/web/test_classes_api.py tests/web/test_class_assignments_api.py -q`
Expected: PASS, including the pre-existing tests.

- [ ] **Step 9: Commit**

```bash
git add src/sms/migrations/versions/0015_class_subject.py src/sms/web/services/classes.py src/sms/web/routers/classes.py tests/unit/test_migration_0015.py tests/unit/test_migrations_postgres.py tests/web/test_classes_api.py
git commit -m "feat(classes): subject per class, marking and needs-you counts for the school tiles"
```

---

### Task 2: Review summary and due-soon routes

**Files:**
- Create: `src/sms/web/services/scenes.py`, `src/sms/web/routers/scenes.py`
- Modify: `src/sms/web/app.py:78-86`
- Test: `tests/web/test_scenes_api.py`

**Interfaces:**
- Consumes: `teacher_queue.status = 'pending'`, `student_corrections.status`, `class_assignments`, `submissions`, `classes`.
- Produces: `GET /api/review/summary` → `{"needs_you": int, "remarked": int, "ready_to_release": int, "ready_sets": [{"id", "class_id", "class_name", "title"}]}` (`ready_sets` at most 5, soonest created first); `GET /api/class-assignments/due?days=7` → `[{"id", "class_id", "class_name", "title", "due_at", "status"}]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/web/test_scenes_api.py
from datetime import datetime, timedelta, timezone

from tests.web.seed_v2 import seed_v2


def _template(auth):
    return auth.post("/api/assignments", json={"title": "Paper", "subject": "math", "context": "", "rubric": {"criterion_defs": []},
                                               "scheme_kind": "criteria", "questions": [], "scheme": []}).json()


def _open_set(auth, cid, tid, due=None):
    ca = auth.post(f"/api/classes/{cid}/assignments", json={"template_id": tid, "due_at": due}).json()
    auth.put(f"/api/classes/{cid}/assignments/{ca['id']}", json={"title": ca["title"], "due_at": due, "allow_student_uploads": True, "status": "open"})
    return ca


def test_requires_auth(client):
    assert client.get("/api/review/summary").status_code == 401
    assert client.get("/api/class-assignments/due").status_code == 401


def test_review_summary_counts_queue_remarked_and_ready_sets(auth, app):
    t = _template(auth)
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    ready = _open_set(auth, c["id"], t["id"]); busy = _open_set(auth, c["id"], t["id"]); empty = _open_set(auth, c["id"], t["id"])
    done, _ = seed_v2(app, run_id="r-d", queue={})
    flagged, _ = seed_v2(app, run_id="r-f", queue={"1a": "low_confidence"})
    db = app.state.db
    db.execute("UPDATE submissions SET class_assignment_id = :ca WHERE id = :i", {"ca": ready["id"], "i": done})
    db.execute("UPDATE submissions SET class_assignment_id = :ca, status = 'needs_you' WHERE id = :i", {"ca": busy["id"], "i": flagged})
    db.execute("INSERT INTO student_corrections (submission_id, q_id, reason, text, status) VALUES (:s, '1b', 'sign', 'x', 'remarked')", {"s": done})
    db.execute("INSERT INTO student_corrections (submission_id, q_id, reason, text, status) VALUES (:s, '2', 'sign', 'y', 'released')", {"s": done})
    s = auth.get("/api/review/summary").json()
    assert s["needs_you"] == 1 and s["remarked"] == 1 and s["ready_to_release"] == 1
    assert [x["id"] for x in s["ready_sets"]] == [ready["id"]] and s["ready_sets"][0]["class_name"] == "4E2"
    assert empty["id"] not in [x["id"] for x in s["ready_sets"]]   # nothing handed in yet


def test_due_list_is_open_sets_inside_the_window_soonest_first(auth):
    t = _template(auth)
    c = auth.post("/api/classes", json={"name": "4E2"}).json()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    soon = _open_set(auth, c["id"], t["id"], iso(now + timedelta(days=2)))
    later = _open_set(auth, c["id"], t["id"], iso(now + timedelta(days=1)))
    far = _open_set(auth, c["id"], t["id"], iso(now + timedelta(days=20)))
    past = _open_set(auth, c["id"], t["id"], iso(now - timedelta(days=1)))
    nodue = _open_set(auth, c["id"], t["id"])
    draft = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "due_at": iso(now + timedelta(days=1))}).json()
    rows = auth.get("/api/class-assignments/due?days=7").json()
    assert [r["id"] for r in rows] == [later["id"], soon["id"]]
    assert rows[0]["class_name"] == "4E2" and rows[0]["status"] == "open" and rows[0]["due_at"].endswith("Z")
    assert auth.get("/api/class-assignments/due?days=30").json()[-1]["id"] == far["id"]
    assert {past["id"], nodue["id"], draft["id"]}.isdisjoint({r["id"] for r in rows})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run python -m pytest tests/web/test_scenes_api.py -q`
Expected: FAIL with 404s (routes missing).

- [ ] **Step 3: Write the service and router**

```python
# src/sms/web/services/scenes.py
"""Numbers the painted scenes need that no existing route carries: the Review desk's trays and the desk pinboard."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sms.memory.db import Database
from sms.timeutil import iso_utc

_UNSETTLED = "('uploaded', 'queued', 'marking', 'needs_you')"


def review_summary(db: Database) -> Dict[str, Any]:
    needs_you = db.query("SELECT COUNT(*) AS n FROM teacher_queue WHERE status = 'pending'")[0]["n"]
    remarked = db.query("SELECT COUNT(*) AS n FROM student_corrections WHERE status = 'remarked'")[0]["n"]
    ready = db.query(
        "SELECT a.id, a.class_id, a.title, c.name AS class_name FROM class_assignments a JOIN classes c ON c.id = a.class_id "
        "WHERE a.status = 'open' "
        "AND EXISTS (SELECT 1 FROM submissions s WHERE s.class_assignment_id = a.id) "
        f"AND NOT EXISTS (SELECT 1 FROM submissions s WHERE s.class_assignment_id = a.id AND s.status IN {_UNSETTLED}) "
        "ORDER BY a.created_at, a.id")
    return {"needs_you": int(needs_you or 0), "remarked": int(remarked or 0), "ready_to_release": len(ready),
            "ready_sets": [{"id": r["id"], "class_id": r["class_id"], "class_name": r["class_name"], "title": r["title"]} for r in ready[:5]]}


def _as_utc(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace(" ", "T").replace("Z", "+00:00")).astimezone(timezone.utc)


def due_class_assignments(db: Database, days: int) -> List[Dict[str, Any]]:
    """Open class sets due between now and `days` from now, soonest first. Dates are compared in Python so the
    same code runs on SQLite (text) and Postgres (timestamp)."""
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=max(0, days))
    rows = db.query("SELECT a.id, a.class_id, a.title, a.due_at, a.status, c.name AS class_name FROM class_assignments a "
                    "JOIN classes c ON c.id = a.class_id WHERE a.status = 'open' AND a.due_at IS NOT NULL")
    due = [r for r in rows if now <= _as_utc(r["due_at"]) <= until]
    due.sort(key=lambda r: (_as_utc(r["due_at"]), r["id"]))
    return [{"id": r["id"], "class_id": r["class_id"], "class_name": r["class_name"], "title": r["title"],
             "due_at": iso_utc(r["due_at"]), "status": r["status"]} for r in due]
```

```python
# src/sms/web/routers/scenes.py
from fastapi import APIRouter, Depends, Query

from sms.web.deps import get_db, require_teacher
from sms.web.services.scenes import due_class_assignments, review_summary

router = APIRouter(tags=["scenes"], dependencies=[Depends(require_teacher)])


@router.get("/api/review/summary")
def summary(db=Depends(get_db)):
    return review_summary(db)


@router.get("/api/class-assignments/due")
def due(days: int = Query(7, ge=0, le=365), db=Depends(get_db)):
    return due_class_assignments(db, days)
```

In `src/sms/web/app.py` add `scenes` to the routers import and `app.include_router(scenes.router)` after `corrections.router` (the `/api/class-assignments/{caid}/release-corrections` route is a POST, so `/api/class-assignments/due` does not collide; keep it after anyway).

- [ ] **Step 4: Run the tests**

Run: `uv run python -m pytest tests/web/test_scenes_api.py tests/web/test_corrections_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sms/web/services/scenes.py src/sms/web/routers/scenes.py src/sms/web/app.py tests/web/test_scenes_api.py
git commit -m "feat(api): review summary and due-soon routes for the marking desk and the pinboard"
```

---

### Task 3: Scene framework — types, art manifest, hooks, effects, CSS

**Files:**
- Create: `web/src/scene/art.ts`, `web/src/scene/useSceneLabels.ts`, `web/src/scene/useTour.ts`, `web/src/scene/useFilm.ts`, `web/src/scene/effects.tsx`, `web/src/scene/Scene.tsx`
- Modify: `web/src/api/types.ts:151`, `web/src/lib/format.ts:17-21`, `web/src/styles/tokens.css:13-16`, `web/src/styles/app.css` (append)
- Test: `web/src/scene/__tests__/Scene.test.tsx`, `web/src/scene/__tests__/useTour.test.tsx`

**Interfaces:**
- Produces:
  - `ClassRow` gains `subject: Subject | null; marking: number; needs_you: number`.
  - `export interface ReviewSummary { needs_you: number; remarked: number; ready_to_release: number; ready_sets: { id: number; class_id: number; class_name: string; title: string }[] }`
  - `export interface DueClassAssignment { id: number; class_id: number; class_name: string; title: string; due_at: string; status: string }`
  - `export const subjectColor: Record<Subject, string>`; `export type TileKey = Subject | "general"`.
  - `ART: Record<"desk" | "review" | "library" | "school", string>`, `FILM: Partial<Record<"desk" | "review" | "library" | TileKey, string>>`, `SUBJECT_TILE: Record<TileKey, string>`.
  - `export interface Hotspot { id: string; left: string; top: string; label: string; sub?: string; color?: string; href?: string; onPick?: () => void }`
  - `export function Scene(props: { art: string; film?: string; alt: string; hotspots: Hotspot[]; effects?: ReactNode; cue?: { name: string; key: number } | null; tier: DeviceTier; name: string; tourable?: boolean; children?: ReactNode })` — `name` is the `aria-label` of the scene region and the key under which pins are kept; `children` render in the card under the painting.
  - `useSceneLabels(): [on: boolean, set: (v: boolean) => void]`; `useTour(count: number): { index: number; running: boolean; toggle: () => void }`; `useFilm(tier: DeviceTier): [on: boolean, set: (v: boolean) => void]` (false whenever `tier === "static"` or `saveData`).
  - Effects: `Glow({ left, top, size?, delay? })`, `Flag({ left, top })`, `Dots({ left, top, delay? })`, `Paper({ left, top, delay? })`, `Stamp({ left, top, text })`, `Tick({ left, top })`, `Book({ left, top, color?, delay? })`, `Star({ left, top, delay? })` — each renders one `aria-hidden` element positioned by percentage strings.

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/scene/__tests__/useTour.test.tsx
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTour } from "../useTour";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useTour", () => {
  it("walks every hotspot once at 3 s each, then stops", () => {
    const { result } = renderHook(() => useTour(3));
    expect(result.current.running).toBe(false);
    act(() => result.current.toggle());
    expect(result.current).toMatchObject({ running: true, index: 0 });
    act(() => { vi.advanceTimersByTime(3000); });
    expect(result.current.index).toBe(1);
    act(() => { vi.advanceTimersByTime(3000); });
    expect(result.current.index).toBe(2);
    act(() => { vi.advanceTimersByTime(3000); });
    expect(result.current).toMatchObject({ running: false, index: -1 });
  });

  it("stops early on a second toggle and clears its timer on unmount", () => {
    const { result, unmount } = renderHook(() => useTour(4));
    act(() => result.current.toggle());
    act(() => result.current.toggle());
    expect(result.current.running).toBe(false);
    act(() => result.current.toggle());
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
```

```tsx
// web/src/scene/__tests__/Scene.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Glow } from "../effects";
import { Scene, type Hotspot } from "../Scene";

const spots: Hotspot[] = [
  { id: "a", left: "20%", top: "30%", label: "4E2 Mathematics", sub: "4KEF · 4 students", onPick: () => {} },
  { id: "b", left: "60%", top: "30%", label: "3N1 English", href: "/classes/2" },
];
const tag = (name: string) => screen.getByTestId(`tag-${name}`);
function mount(extra: Partial<React.ComponentProps<typeof Scene>> = {}) {
  return render(<MemoryRouter><Scene name="The school" art="/art/school.jpg" alt="school" hotspots={spots} tier="2d" effects={<Glow left="10%" top="10%" />} {...extra} /></MemoryRouter>);
}
function pointer(coarse: boolean) {
  vi.stubGlobal("matchMedia", vi.fn((q: string) => ({ matches: q.includes("coarse") && coarse, addEventListener() {}, removeEventListener() {} })));
}

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); pointer(false); });
afterEach(() => vi.unstubAllGlobals());

describe("Scene", () => {
  it("hides labels until a hotspot is hovered or focused, and pins on tap", async () => {
    mount();
    expect(tag("a")).toHaveClass("off");
    await userEvent.hover(screen.getByRole("button", { name: "4E2 Mathematics" }));
    expect(tag("a")).toHaveClass("on");
    await userEvent.unhover(screen.getByRole("button", { name: "4E2 Mathematics" }));
    expect(tag("a")).toHaveClass("off");
    await userEvent.click(screen.getByRole("button", { name: "4E2 Mathematics" }));
    await userEvent.unhover(screen.getByRole("button", { name: "4E2 Mathematics" }));
    expect(tag("a")).toHaveClass("on");
    expect(screen.getByRole("link", { name: "3N1 English" })).toHaveAttribute("href", "/classes/2");
    screen.getByRole("link", { name: "3N1 English" }).focus();
    expect(tag("b")).toHaveClass("on");
  });

  it("Show labels opens every tag, is remembered, and defaults on for a coarse pointer", async () => {
    mount();
    await userEvent.click(screen.getByRole("button", { name: "Show labels" }));
    expect(tag("a")).toHaveClass("on"); expect(tag("b")).toHaveClass("on");
    expect(localStorage.getItem("sms.scene.labels")).toBe("on");
    localStorage.clear(); pointer(true);
    mount();
    expect(screen.getAllByTestId(/^tag-/).every((el) => el.classList.contains("on"))).toBe(true);
  });

  it("renders no effects and no film on the static tier, and the film gate obeys the switch", () => {
    const { unmount } = mount({ tier: "static", film: "/art/film/school.mp4" });
    expect(screen.queryByTestId("fx")).toBeNull();
    expect(document.querySelector("video")).toBeNull();
    unmount();
    mount({ film: "/art/film/school.mp4" });
    expect(screen.getByTestId("fx")).toBeInTheDocument();
    expect(document.querySelector("video")).toHaveAttribute("src", "/art/film/school.mp4");
  });

  it("plays a cue as a class for a moment", () => {
    vi.useFakeTimers();
    const { container } = mount({ cue: { name: "settle", key: 1 } });
    expect(container.querySelector(".scene-box")).toHaveClass("cue-settle");
    vi.advanceTimersByTime(1500);
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd web && npx vitest run src/scene`
Expected: FAIL (modules not found).

- [ ] **Step 3: Types, tokens and the art manifest**

In `web/src/api/types.ts` replace the `ClassRow` line with:

```ts
export interface ClassRow { id: number; name: string; code: string; student_count: number; open_assignments: number; subject: Subject | null; marking: number; needs_you: number; archived_at: string | null; created_at: string; updated_at: string }
export interface ReviewSummary { needs_you: number; remarked: number; ready_to_release: number; ready_sets: { id: number; class_id: number; class_name: string; title: string }[] }
export interface DueClassAssignment { id: number; class_id: number; class_name: string; title: string; due_at: string; status: string }
```

In `web/src/lib/format.ts` after `SUBJECTS`:

```ts
export type TileKey = Subject | "general";
/** The colour each subject wears on folder tabs, shelf dots and classroom tags. */
export const subjectColor: Record<Subject, string> = { math: "var(--crew-marker)", language: "var(--mint)", science: "var(--gold)", mt: "var(--lilac)", computing: "var(--sky)" };
```

In `web/src/styles/tokens.css` after `--oak`: `--lilac: #C9A7E8;` and `--sky: #8FB8E8;`.

```ts
// web/src/scene/art.ts
import type { TileKey } from "../lib/format";

export const ART = { desk: "/art/desk.jpg", review: "/art/review.jpg", library: "/art/library.jpg", school: "/art/school.jpg" } as const;
export const SUBJECT_TILE: Record<TileKey, string> = {
  math: "/art/tile-math.jpg", language: "/art/tile-language.jpg", science: "/art/tile-science.jpg",
  mt: "/art/tile-mt.jpg", computing: "/art/tile-computing.jpg", general: "/art/tile-general.jpg",
};
/** 5 s muted loops made from the stills; a scene without an entry shows its still. */
export const FILM: Partial<Record<keyof typeof ART | TileKey, string>> = {
  desk: "/art/film/desk.mp4", review: "/art/film/review.mp4", library: "/art/film/library.mp4",
  math: "/art/film/tile-math.mp4", language: "/art/film/tile-language.mp4", science: "/art/film/tile-science.mp4",
  mt: "/art/film/tile-mt.mp4", computing: "/art/film/tile-computing.mp4", general: "/art/film/tile-general.mp4",
};
```

- [ ] **Step 4: The hooks**

```ts
// web/src/scene/useSceneLabels.ts
import { useCallback, useState } from "react";

const KEY = "sms.scene.labels";
const read = (): boolean | null => { try { const v = localStorage.getItem(KEY); return v === "on" ? true : v === "off" ? false : null; } catch { return null; } };
const coarse = () => typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;

/** Show labels: remembered across visits; on by default where there is no hover (phones). */
export function useSceneLabels(): [boolean, (v: boolean) => void] {
  const [on, setOn] = useState<boolean>(() => read() ?? coarse());
  const set = useCallback((v: boolean) => { setOn(v); try { localStorage.setItem(KEY, v ? "on" : "off"); } catch { /* private mode */ } }, []);
  return [on, set];
}
```

```ts
// web/src/scene/useTour.ts
import { useCallback, useEffect, useRef, useState } from "react";

export const TOUR_STEP_MS = 3000;

/** Walks hotspots 0..count-1, one every 3 s, once round; index is -1 when not running. */
export function useTour(count: number): { index: number; running: boolean; toggle: () => void } {
  const [index, setIndex] = useState(-1);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const stop = useCallback(() => { if (timer.current) clearInterval(timer.current); timer.current = null; setIndex(-1); }, []);
  const toggle = useCallback(() => {
    if (timer.current) { stop(); return; }
    if (count === 0) return;
    setIndex(0);
    timer.current = setInterval(() => setIndex((i) => {
      if (i + 1 >= count) { if (timer.current) clearInterval(timer.current); timer.current = null; return -1; }
      return i + 1;
    }), TOUR_STEP_MS);
  }, [count, stop]);
  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);
  return { index, running: timer.current !== null && index >= 0, toggle };
}
```

```ts
// web/src/scene/useFilm.ts
import { useCallback, useState } from "react";
import type { DeviceTier } from "./useDeviceTier";

const KEY = "sms.scene.film";
const saveData = () => Boolean((navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData);
const readOff = () => { try { return sessionStorage.getItem(KEY) === "off"; } catch { return false; } };

/** Whether a scene may play its film loop: never on the static tier or under Save-Data, and not after the teacher switched it off this session. */
export function useFilm(tier: DeviceTier): [boolean, (v: boolean) => void] {
  const [wanted, setWanted] = useState(() => !readOff());
  const set = useCallback((v: boolean) => { setWanted(v); try { if (v) sessionStorage.removeItem(KEY); else sessionStorage.setItem(KEY, "off"); } catch { /* ignore */ } }, []);
  return [wanted && tier === "2d" && !saveData(), set];
}
```

- [ ] **Step 5: The effects**

```tsx
// web/src/scene/effects.tsx
import type { CSSProperties } from "react";

type At = { left: string; top: string; delay?: number };
const at = ({ left, top, delay }: At, extra: CSSProperties = {}): CSSProperties => ({ left, top, animationDelay: delay ? `${delay}s` : undefined, ...extra });
const fx = (cls: string, style: CSSProperties, children?: React.ReactNode) => <div className={`fx ${cls}`} style={style} aria-hidden="true" data-testid="fx">{children}</div>;

/** A warm pulsing light: a lit doorway, a lamp, a screen. `size` is a percentage of the painting's width. */
export const Glow = (p: At & { size?: string }) => fx("fx-glow", at(p, { width: p.size ?? "12%" }));
export const Flag = (p: At) => fx("fx-flag", at(p));
/** Three bobbing dots: someone is thinking or writing. */
export const Dots = (p: At) => fx("fx-dots", at(p), <><i /><i /><i /></>);
export const Paper = (p: At) => fx("fx-paper", at(p));
export const Stamp = (p: At & { text: string }) => fx("fx-stamp", at(p), p.text);
export const Tick = (p: At) => <svg className="fx fx-tick" style={at(p)} viewBox="0 0 24 24" aria-hidden="true" data-testid="fx"><path d="M4 13l5 5L20 7" /></svg>;
export const Book = (p: At & { color?: string }) => fx("fx-book", at(p, { background: p.color }));
export const Star = (p: At) => fx("fx-star", at(p));
```

- [ ] **Step 6: The Scene component**

```tsx
// web/src/scene/Scene.tsx
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { DeviceTier } from "./useDeviceTier";
import { useFilm } from "./useFilm";
import { useSceneLabels } from "./useSceneLabels";
import { useTour } from "./useTour";

export interface Hotspot { id: string; left: string; top: string; label: string; sub?: string; color?: string; href?: string; onPick?: () => void }
export interface Cue { name: string; key: number }

interface Props { name: string; art: string; film?: string; alt: string; hotspots: Hotspot[]; effects?: ReactNode; cue?: Cue | null; tier: DeviceTier; tourable?: boolean; children?: ReactNode }

/** A painted scene with hover/tap labels, a Show labels switch, a 3 s Tour, optional film loop, ambient effects and one-shot cues. */
export function Scene({ name, art, film, alt, hotspots, effects, cue, tier, tourable = true, children }: Props) {
  const [labels, setLabels] = useSceneLabels();
  const [filmOn, setFilmOn] = useFilm(tier);
  const tour = useTour(hotspots.length);
  const [hover, setHover] = useState<string | null>(null);
  const [pinned, setPinned] = useState<Record<string, boolean>>({});
  const [filmBroken, setFilmBroken] = useState(false);
  const [cueClass, setCueClass] = useState("");

  useEffect(() => {
    if (!cue || tier === "static") return;
    setCueClass(`cue-${cue.name}`);
    const t = setTimeout(() => setCueClass(""), 1500);
    return () => clearTimeout(t);
  }, [cue?.key, cue?.name, tier]);

  const live = tier !== "static";
  const showFilm = live && filmOn && !!film && !filmBroken;
  const isOn = (h: Hotspot, i: number) => labels || hover === h.id || !!pinned[h.id] || tour.index === i;
  const hint = tour.running ? "Touring, one spot every 3 seconds." : labels ? "Every label is open." : "Hover a spot to see its label; tap to keep it open.";

  return (
    <section className="scene card" aria-label={name}>
      <div className="scene-controls">
        <span className="muted scene-hint">{hint}</span>
        <button type="button" className={`btn btn-sm ${labels ? "btn-primary" : "btn-secondary"}`} aria-pressed={labels} onClick={() => setLabels(!labels)}>Show labels</button>
        {tourable && hotspots.length > 0 && <button type="button" className={`btn btn-sm ${tour.running ? "btn-primary" : "btn-secondary"}`} aria-pressed={tour.running} onClick={tour.toggle}>Tour · 3 s</button>}
        {live && film && <button type="button" className={`btn btn-sm ${filmOn ? "btn-primary" : "btn-secondary"}`} aria-pressed={filmOn} onClick={() => setFilmOn(!filmOn)}>Film</button>}
      </div>
      <div className={`scene-box ${cueClass}`}>
        <img src={art} alt={alt} />
        {showFilm && <video className="scene-film" src={film} poster={art} autoPlay muted loop playsInline aria-hidden="true" onError={() => setFilmBroken(true)} />}
        {live && effects}
        {hotspots.map((h, i) => {
          const handlers = { onMouseEnter: () => setHover(h.id), onMouseLeave: () => setHover((v) => (v === h.id ? null : v)), onFocus: () => setHover(h.id), onBlur: () => setHover((v) => (v === h.id ? null : v)) };
          const style = { left: h.left, top: h.top };
          return (
            <span key={h.id}>
              {h.href
                ? <Link to={h.href} className="scene-spot" style={style} aria-label={h.label} {...handlers} />
                : <button type="button" className={`scene-spot ${pinned[h.id] ? "pinned" : ""}`} style={style} aria-label={h.label} aria-pressed={!!pinned[h.id]} {...handlers}
                    onClick={() => { setPinned((p) => ({ ...p, [h.id]: !p[h.id] })); h.onPick?.(); }} />}
              <div className={`scene-tag ${isOn(h, i) ? "on" : "off"}`} style={style} aria-hidden="true" data-testid={`tag-${h.id}`}>
                <b>{h.color && <i className="dot" style={{ background: h.color }} />}{h.label}</b>
                {h.sub && <span>{h.sub}</span>}
              </div>
            </span>
          );
        })}
      </div>
      {children}
    </section>
  );
}
```

- [ ] **Step 7: The CSS**

Append to `web/src/styles/app.css`:

```css
/* Painted scenes (Classes, Assignments, Review, Learning) */
.scene { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.scene-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.scene-hint { margin-right: auto; font-size: 13px; }
.scene-box { position: relative; border-radius: var(--radius-lg); overflow: hidden; background: var(--color-bg); }
.scene-box img, .scene-film { display: block; width: 100%; height: auto; }
.scene-film { position: absolute; inset: 0; height: 100%; object-fit: cover; }
.scene-spot { position: absolute; transform: translate(-50%, -50%); width: 110px; height: 86px; border-radius: 50%; border: 0; background: transparent; cursor: pointer; padding: 0; display: block; }
.scene-spot:hover, .scene-spot:focus-visible { background: rgba(255, 232, 163, 0.35); outline: 3px solid var(--color-text); outline-offset: -3px; }
.scene-spot.pinned { background: rgba(242, 131, 107, 0.25); }
.scene-tag { position: absolute; transform: translate(-50%, -100%); display: flex; flex-direction: column; gap: 2px; padding: 8px 12px; border-radius: 14px; background: var(--color-text); color: #fff; box-shadow: 0 4px 0 #15141A; white-space: nowrap; pointer-events: none; transition: opacity .35s ease, transform .35s ease; max-width: min(320px, 90%); }
.scene-tag.off { opacity: 0; transform: translate(-50%, -80%); }
.scene-tag b { font: 600 15px var(--font-heading); display: flex; align-items: center; gap: 8px; overflow: hidden; text-overflow: ellipsis; }
.scene-tag span { font-size: 12px; opacity: .85; overflow: hidden; text-overflow: ellipsis; }
.scene-tag::after { content: ""; position: absolute; left: 50%; bottom: -10px; margin-left: -6px; border: 6px solid transparent; border-top-color: var(--color-text); }
.fx { position: absolute; pointer-events: none; }
.fx-glow { aspect-ratio: 1; border-radius: 50%; transform: translate(-50%, -50%); background: radial-gradient(circle, rgba(255, 214, 102, .8) 0%, rgba(255, 214, 102, 0) 70%); animation: fx-glow 2.6s ease-in-out infinite; }
.fx-flag { width: 3%; aspect-ratio: 1.3; background: var(--crew-marker); clip-path: polygon(0 0, 100% 25%, 0 55%); transform-origin: 0 50%; animation: fx-wave 1.3s ease-in-out infinite; }
.fx-dots { display: flex; gap: 3px; padding: 4px 6px; border-radius: 999px; background: #fff; border: 1.5px solid var(--color-text); transform: translate(-50%, -50%); animation: fx-bob 1.8s ease-in-out infinite; }
.fx-dots i { width: 4px; height: 4px; border-radius: 50%; background: var(--color-text); animation: fx-blink 1.2s ease-in-out infinite; }
.fx-dots i:nth-child(2) { animation-delay: .2s; } .fx-dots i:nth-child(3) { animation-delay: .4s; }
.fx-paper { width: 4.5%; aspect-ratio: 1.4; background: #fff; border: 1.5px solid var(--color-text); border-radius: 2px; box-shadow: 1px 1px 0 var(--color-text); opacity: 0; animation: fx-land 3.6s ease-in-out infinite; }
.fx-stamp { padding: 3px 7px; border: 2px solid var(--crew-reader-ink); border-radius: 6px; color: var(--crew-reader-ink); font: 700 11px var(--font-heading); letter-spacing: .06em; background: rgba(255, 255, 255, .7); transform: translate(-50%, -50%) rotate(-12deg) scale(0); opacity: 0; }
.fx-tick { width: 3.4%; transform: translate(-50%, -50%); } .fx-tick path { fill: none; stroke: var(--crew-marker-ink); stroke-width: 4; stroke-linecap: round; stroke-dasharray: 40; stroke-dashoffset: 40; }
.fx-book { width: 1.6%; aspect-ratio: .5; background: var(--crew-marker); border: 1.5px solid var(--color-text); border-radius: 1px; opacity: 0; }
.fx-star { width: 10px; height: 10px; background: var(--gold); clip-path: polygon(50% 0, 61% 38%, 100% 50%, 61% 62%, 50% 100%, 39% 62%, 0 50%, 39% 38%); transform: translate(-50%, -50%) scale(0); animation: fx-twinkle 2.4s ease-in-out infinite; }
/* one-shot cues: the page sets cue-<name> on .scene-box for 1.5 s */
.cue-settle .fx-paper { animation: fx-settle 1.4s ease-in-out 1; opacity: 1; }
.cue-stamp .fx-stamp { animation: fx-thump 1.4s ease-out 1; }
.cue-tick .fx-tick path { animation: fx-draw 1.2s ease-in-out 1; }
.cue-shelve .fx-book { animation: fx-shelve 1.4s ease-in-out 1; }
@keyframes fx-glow { 0%, 100% { opacity: .35; } 50% { opacity: .9; } }
@keyframes fx-wave { 0%, 100% { transform: skewY(0); } 50% { transform: skewY(-10deg) scaleX(.9); } }
@keyframes fx-bob { 0%, 100% { transform: translate(-50%, -50%); } 50% { transform: translate(-50%, -70%); } }
@keyframes fx-blink { 0%, 100% { opacity: .25; } 50% { opacity: 1; } }
@keyframes fx-land { 0% { opacity: 0; transform: translate(60px, -90px) rotate(12deg); } 35% { opacity: 1; } 60% { opacity: 1; transform: translate(0, 0) rotate(0); } 100% { opacity: 0; transform: translate(0, 0); } }
@keyframes fx-settle { 0% { transform: translate(0, 0); } 70% { transform: translate(150px, -40px); } 100% { transform: translate(150px, -40px); opacity: 0; } }
@keyframes fx-thump { 0% { transform: translate(-50%, -50%) rotate(-12deg) scale(0); opacity: 0; } 30% { transform: translate(-50%, -50%) rotate(-12deg) scale(1.25); opacity: 1; } 45% { transform: translate(-50%, -50%) rotate(-12deg) scale(1); } 100% { transform: translate(-50%, -50%) rotate(-12deg) scale(1); opacity: 0; } }
@keyframes fx-draw { 0% { stroke-dashoffset: 40; opacity: 1; } 60% { stroke-dashoffset: 0; opacity: 1; } 100% { stroke-dashoffset: 0; opacity: 0; } }
@keyframes fx-shelve { 0% { opacity: 0; transform: translate(0, 80px); } 30% { opacity: 1; } 70% { opacity: 1; transform: translate(0, 0); } 100% { opacity: 0; } }
@keyframes fx-twinkle { 0%, 100% { transform: translate(-50%, -50%) scale(0) rotate(0); } 50% { transform: translate(-50%, -50%) scale(1) rotate(20deg); } }
@media (prefers-reduced-motion: reduce) { .scene-tag { transition: none; } .fx { display: none; } }
@media (max-width: 560px) { .scene-spot { width: 72px; height: 64px; } .scene-tag { white-space: normal; } }
```

- [ ] **Step 8: Run the scene tests and the type check**

Run: `cd web && npx vitest run src/scene && npx tsc --noEmit`
Expected: PASS. If the pointer-default test fails because `useState`'s initialiser ran before `matchMedia` was stubbed, the stub in `beforeEach` runs first; check the test calls `pointer(true)` before `mount()`.

- [ ] **Step 9: Commit**

```bash
git add web/src/scene web/src/api/types.ts web/src/lib/format.ts web/src/styles/tokens.css web/src/styles/app.css
git commit -m "feat(web): shared Scene with labels, tour, film gate, effects and cues"
```

---

### Task 4: The school — ClassTile, Classes page, subject on New class and the class page

**Files:**
- Create: `web/src/scene/ClassTile.tsx`, `web/src/scene/__tests__/ClassTile.test.tsx`
- Modify: `web/src/pages/Classes.tsx`, `web/src/pages/ClassPage.tsx:245-262`, `web/src/styles/app.css` (append), `web/src/pages/__tests__/Classes.test.tsx`, `web/src/pages/__tests__/ClassPage.test.tsx`

**Interfaces:**
- Consumes: `ClassRow.subject/marking/needs_you`, `SUBJECT_TILE`, `FILM`, `subjectColor`, effects, `useDeviceTier`, `useSceneLabels`, `useFilm`.
- Produces: `ClassTile({ c: ClassRow; tier: DeviceTier; labels: boolean; film: boolean })` — a `<Link>` to `/classes/:id` whose accessible name is the class name.

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/scene/__tests__/ClassTile.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { ClassRow } from "../../api/types";
import { ClassTile } from "../ClassTile";

const base: ClassRow = { id: 1, name: "4E2 Mathematics", code: "4KEF", student_count: 4, open_assignments: 0, subject: "math", marking: 0, needs_you: 0, archived_at: null, created_at: "", updated_at: "" };
const mount = (c: Partial<ClassRow>, tier: "2d" | "static" = "2d", labels = false) =>
  render(<MemoryRouter><ClassTile c={{ ...base, ...c }} tier={tier} labels={labels} film={false} /></MemoryRouter>);

describe("ClassTile", () => {
  it("paints the subject's classroom, falls back to the plain one, and links to the class", () => {
    mount({});
    expect(screen.getByRole("img")).toHaveAttribute("src", "/art/tile-math.jpg");
    expect(screen.getByRole("link", { name: /4E2 Mathematics/ })).toHaveAttribute("href", "/classes/1");
    mount({ subject: null, name: "Form 1" });
    expect(screen.getAllByRole("img")[1]).toHaveAttribute("src", "/art/tile-general.jpg");
  });

  it("shows state as effects on the 2d tier only, and the detail line when labels are on", () => {
    const { container } = mount({ open_assignments: 2, marking: 1, needs_you: 3 });
    expect(container.querySelector(".fx-glow")).not.toBeNull();
    expect(container.querySelector(".fx-dots")).not.toBeNull();
    expect(container.querySelector(".fx-flag")).not.toBeNull();
    expect(screen.getByRole("link", { name: /3 need you/ })).toBeInTheDocument();
    expect(screen.getByTestId("tile-sub")).toHaveClass("off");
    const quiet = mount({}, "static", true);
    expect(quiet.container.querySelector(".fx")).toBeNull();
    expect(quiet.getByTestId("tile-sub")).toHaveClass("on");
  });
});
```

In `web/src/pages/__tests__/Classes.test.tsx` extend the first test's `ClassRow` literals with `subject: "math", marking: 0, needs_you: 0` (and `subject: null` for the archived one) so they type-check, and add:

```tsx
  it("draws a tile per live class, a plot for a new class, and sends the subject", async () => {
    const list: ClassRow[] = [{ id: 1, name: "4E2 Mathematics", code: "CE4R", student_count: 40, open_assignments: 2, subject: "math", marking: 0, needs_you: 0, archived_at: null, created_at: "", updated_at: "" }];
    const calls = mockFetch({
      "GET /api/classes": () => new Response(JSON.stringify(list), { status: 200 }),
      "POST /api/classes": (init) => { const body = JSON.parse(String(init?.body)); list.push({ ...list[0], id: 2, name: body.name, subject: body.subject }); return new Response(JSON.stringify(list[1]), { status: 201 }); },
    });
    render(<MemoryRouter><Classes /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: /4E2 Mathematics/ })).toHaveAttribute("href", "/classes/1");
    expect(screen.getByText("Your school")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Build a classroom" }));
    await userEvent.type(screen.getByLabelText("Class name"), "2E3 Science");
    await userEvent.selectOptions(screen.getByLabelText("Subject"), "science");
    await userEvent.click(screen.getByRole("button", { name: "Create class" }));
    expect(calls.find((c) => c.method === "POST")?.path).toBe("/api/classes");
    expect(await screen.findByRole("link", { name: /2E3 Science/ })).toBeInTheDocument();
  });
```

In `web/src/pages/__tests__/ClassPage.test.tsx` add a test (follow the file's existing mocking helper for `/api/classes/1`):

```tsx
  it("lets the teacher set the class subject under Settings", async () => {
    // reuse the file's mock setup with cls.subject = null; then
    await userEvent.click(screen.getByRole("tab", { name: "Settings" }));   // or the link/button the file uses to switch tabs
    await userEvent.selectOptions(screen.getByLabelText("Subject"), "science");
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ name: "4E2 Mathematics", subject: "science" }));
  });
```

(Read the file first: match its mock helper's name and how it switches tabs; the assertion on the PUT body is the contract.)

- [ ] **Step 2: Run them to verify they fail**

Run: `cd web && npx vitest run src/scene/__tests__/ClassTile.test.tsx src/pages/__tests__/Classes.test.tsx src/pages/__tests__/ClassPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write ClassTile**

```tsx
// web/src/scene/ClassTile.tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import type { ClassRow } from "../api/types";
import { subjectColor } from "../lib/format";
import { FILM, SUBJECT_TILE } from "./art";
import { Dots, Flag, Glow } from "./effects";
import type { DeviceTier } from "./useDeviceTier";

/** Where the doorway, the teacher and the flag sit on every classroom tile (percentages of the tile). */
const DOOR = { left: "26%", top: "66%" }; const TEACHER = { left: "28%", top: "40%" }; const FLAG = { left: "70%", top: "26%" };

export function ClassTile({ c, tier, labels, film }: { c: ClassRow; tier: DeviceTier; labels: boolean; film: boolean }) {
  const key = c.subject ?? "general";
  const [broken, setBroken] = useState(false);
  const [hover, setHover] = useState(false);
  const live = tier !== "static";
  const sub = `${c.code} · ${c.student_count} student${c.student_count === 1 ? "" : "s"} · ${c.open_assignments} open${c.needs_you > 0 ? ` · ${c.needs_you} need you` : ""}`;
  return (
    <Link to={`/classes/${c.id}`} className="tile" aria-label={`${c.name} · ${sub}`}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onFocus={() => setHover(true)} onBlur={() => setHover(false)}>
      <div className="tile-box">
        <img src={SUBJECT_TILE[key]} alt="" />
        {live && film && FILM[key] && !broken && <video className="scene-film" src={FILM[key]} poster={SUBJECT_TILE[key]} autoPlay muted loop playsInline aria-hidden="true" onError={() => setBroken(true)} />}
        {live && c.open_assignments > 0 && <Glow {...DOOR} size="22%" />}
        {live && c.marking > 0 && <Dots {...TEACHER} />}
        {live && c.needs_you > 0 && <Flag {...FLAG} />}
      </div>
      <div className="tile-tag">
        <b><i className="dot" style={{ background: c.subject ? subjectColor[c.subject] : "var(--oak)" }} aria-hidden />{c.name}</b>
        <span className={labels || hover ? "on" : "off"} data-testid="tile-sub">{sub}</span>
      </div>
    </Link>
  );
}
```

Append to `web/src/styles/app.css`:

```css
/* the school: one classroom tile per class */
.campus { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 20px; margin-top: 16px; }
.tile { display: flex; flex-direction: column; gap: 8px; text-decoration: none; color: inherit; border-radius: var(--radius-lg); transition: transform .25s ease; }
.tile:hover, .tile:focus-visible { transform: translateY(-6px); outline: none; }
.tile:focus-visible .tile-box { outline: 3px solid var(--color-text); outline-offset: 2px; }
.tile-box { position: relative; border-radius: var(--radius-lg); overflow: hidden; background: var(--color-bg); aspect-ratio: 1; }
.tile-box img { display: block; width: 100%; height: 100%; object-fit: cover; }
.tile-tag { display: flex; flex-direction: column; gap: 2px; padding: 8px 12px; border-radius: 14px; background: var(--color-text); color: #fff; align-self: flex-start; max-width: 100%; }
.tile-tag b { font: 600 15px var(--font-heading); display: flex; align-items: center; gap: 8px; }
.tile-tag span { font-size: 12px; opacity: .85; transition: opacity .25s ease, max-height .25s ease; overflow: hidden; }
.tile-tag span.off { opacity: 0; max-height: 0; } .tile-tag span.on { opacity: .85; max-height: 40px; }
.tile-plot { display: flex; align-items: center; justify-content: center; text-align: center; aspect-ratio: 1; border-radius: var(--radius-lg); border: 3px dashed var(--crew-reader-ink); background: rgba(255, 255, 255, .6); color: var(--crew-reader-ink); font: 600 18px var(--font-heading); cursor: pointer; padding: 16px; animation: fx-pulse 2s ease-in-out infinite; }
.tile-plot:hover, .tile-plot:focus-visible { background: #fff; }
.campus-empty { max-width: 720px; margin: 16px auto 0; }
.campus-empty img { width: 100%; height: auto; border-radius: var(--radius-lg); display: block; }
@keyframes fx-pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(90, 165, 115, 0); } 50% { box-shadow: 0 0 0 8px rgba(90, 165, 115, .18); } }
@media (prefers-reduced-motion: reduce) { .tile, .tile-plot { transition: none; animation: none; } .tile-tag span { transition: none; } }
@media (max-width: 480px) { .campus { grid-template-columns: 1fr; } }
```

- [ ] **Step 4: Rewrite the Classes page**

Replace `web/src/pages/Classes.tsx` with:

```tsx
import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { ClassRow, Subject } from "../api/types";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { Notice } from "../components/Notice";
import { SUBJECTS, subjectLabel } from "../lib/format";
import { ART } from "../scene/art";
import { ClassTile } from "../scene/ClassTile";
import { useDeviceTier } from "../scene/useDeviceTier";
import { useFilm } from "../scene/useFilm";
import { useSceneLabels } from "../scene/useSceneLabels";

export function Classes() {
  const [rows, setRows] = useState<ClassRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState<Subject | "">("");
  const [busy, setBusy] = useState(false);
  const tier = useDeviceTier();
  const [labels, setLabels] = useSceneLabels();
  const [film, setFilm] = useFilm(tier);
  const load = useCallback(async () => {
    try { setRows(await api.get<ClassRow[]>("/api/classes")); setError(null); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Couldn't load classes."); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const create = async () => {
    setBusy(true);
    try { await api.post("/api/classes", { name: name.trim(), subject: subject || null }); setCreating(false); setName(""); setSubject(""); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Something went wrong — try again."); }
    finally { setBusy(false); }
  };
  const live = (rows ?? []).filter((c) => !c.archived_at);
  const archived = (rows ?? []).filter((c) => c.archived_at);
  const students = live.reduce((n, c) => n + c.student_count, 0);
  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Your school</h1><p className="meta">Every classroom is a class with its own hand-in code. Tap a classroom to open it; build a new one to add a class.</p></div>
        <div className="actions">
          {rows && <span className="pill pill-outline tabular">{live.length} classroom{live.length === 1 ? "" : "s"} · {students} student{students === 1 ? "" : "s"}</span>}
          <button type="button" className={`btn btn-sm ${labels ? "btn-primary" : "btn-secondary"}`} aria-pressed={labels} onClick={() => setLabels(!labels)}>Show labels</button>
          {tier === "2d" && <button type="button" className={`btn btn-sm ${film ? "btn-primary" : "btn-secondary"}`} aria-pressed={film} onClick={() => setFilm(!film)}>Film</button>}
          <Button variant="primary" onClick={() => setCreating(true)}><Plus size={16} aria-hidden /> Build a classroom</Button>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {rows && live.length === 0 && (
        <div className="campus-empty">
          <img src={ART.school} alt="An empty school with four classrooms around a courtyard and a plot marked out for a new one" />
          <p className="help" style={{ textAlign: "center", marginTop: 12 }}>Your school is empty. Build your first classroom, upload its classlist, then set an assignment from the bank.</p>
          <div className="actions" style={{ justifyContent: "center" }}><Button variant="primary" onClick={() => setCreating(true)}>Build your first classroom</Button></div>
        </div>
      )}
      {live.length > 0 && (
        <div className="campus">
          {live.map((c) => <ClassTile key={c.id} c={c} tier={tier} labels={labels} film={film} />)}
          <button type="button" className="tile-plot" onClick={() => setCreating(true)}>+ Build a classroom</button>
        </div>
      )}
      {archived.length > 0 && (
        <details className="section"><summary>Archived ({archived.length})</summary>
          <div className="cards">{archived.map((c) => <ClassCard key={c.id} c={c} />)}</div>
        </details>
      )}
      {creating && (
        <Dialog title="Build a classroom" onClose={() => setCreating(false)}
          footer={<><Button variant="secondary" onClick={() => setCreating(false)}>Cancel</Button><Button variant="primary" onClick={create} disabled={busy || !name.trim()}>Create class</Button></>}>
          <div className="field"><label htmlFor="class-name">Class name</label>
            <input id="class-name" className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="4E2 Mathematics"
              onKeyDown={(e) => { if (e.key === "Enter" && name.trim() && !busy) create(); }} /></div>
          <div className="field"><label htmlFor="class-subject">Subject</label>
            <select id="class-subject" className="input" value={subject} onChange={(e) => setSubject(e.target.value as Subject | "")}>
              <option value="">Follow the latest assignment</option>
              {SUBJECTS.map((s) => <option key={s} value={s}>{subjectLabel[s]}</option>)}
            </select>
            <p className="help">Chooses the classroom's painting. Leave it to follow whatever you set for the class.</p></div>
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

- [ ] **Step 5: The class page's Subject select**

In `web/src/pages/ClassPage.tsx`, in the settings section after the rename form, add (inside the same component that owns `cls`, `run`, `busy`):

```tsx
      <div className="section">
        <h2 style={{ fontSize: 20 }}>Subject</h2>
        <p className="help">Picks the classroom's painting in your school. "Follow the latest assignment" uses the subject of the last assignment you set.</p>
        <div className="field" style={{ maxWidth: 480 }}><label htmlFor="class-subject">Subject</label>
          <select id="class-subject" className="input" value={cls.subject ?? ""} disabled={busy}
            onChange={(e) => run("Subject saved.", () => api.put<ClassRow>(`/api/classes/${cls.id}`, { name: cls.name, subject: e.target.value || null }))}>
            <option value="">Follow the latest assignment</option>
            {SUBJECTS.map((s) => <option key={s} value={s}>{subjectLabel[s]}</option>)}
          </select></div>
      </div>
```

Import `SUBJECTS, subjectLabel` from `../lib/format` (the file already imports `fmtDate, schemeLabel` from there). Note the saved value and the shown value differ: `cls.subject` is the shown (possibly derived) one, so after choosing "Follow the latest assignment" the select shows the derived subject; that is the intended reading.

- [ ] **Step 6: Run the tests and type check**

Run: `cd web && npx vitest run src/scene src/pages/__tests__/Classes.test.tsx src/pages/__tests__/ClassPage.test.tsx && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/scene/ClassTile.tsx web/src/scene/__tests__/ClassTile.test.tsx web/src/pages/Classes.tsx web/src/pages/ClassPage.tsx web/src/styles/app.css web/src/pages/__tests__/Classes.test.tsx web/src/pages/__tests__/ClassPage.test.tsx
git commit -m "feat(web): the school — classroom tiles per class, build-a-classroom plot, class subject"
```

---

### Task 5: The teacher's desk on Assignments

**Files:**
- Modify: `web/src/pages/Assignments.tsx`, `web/src/pages/__tests__/Assignments.test.tsx`, `web/src/styles/app.css` (append)

**Interfaces:**
- Consumes: `Scene`, `Hotspot`, `ART.desk`, `FILM.desk`, effects, `subjectColor`, `GET /api/class-assignments/due?days=7` → `DueClassAssignment[]`, `GET /api/room` → `RoomSnapshot`.
- Produces: the page with a subject filter (`filter: Subject | null`) and a subject tab on each row.

- [ ] **Step 1: Write the failing test**

Read `web/src/pages/__tests__/Assignments.test.tsx` first; add to its existing mocks `"GET /api/class-assignments/due?days=7"` returning `[{ id: 9, class_id: 1, class_name: "3N1", title: "Comprehension — Unit 4", due_at: "2026-10-12T08:00:00Z", status: "open" }]` and `"GET /api/room"` returning `{ counts: { queued: 0, read: 1, mark: 0, check: 0, feedback: 0, done: 2, needs_you: 0, failed: 0 }, started_at: null, desks: [], last_event_id: 1 }`, with two rows (one `math`, one `language`). Then add:

```tsx
  it("shows the desk, filters the table from the folder rack, and lists what is due on the pinboard", async () => {
    // mount as the file does
    expect(await screen.findByText("Your desk")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "The teacher's desk" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Pinboard · due this week/ })).toHaveAttribute("href", "/classes/1/assignments/9");
    expect(screen.getByRole("link", { name: /Marking now · 1 script/ })).toHaveAttribute("href", "/room");
    await userEvent.click(screen.getByRole("button", { name: /^Maths · 1 folder/ }));
    expect(screen.getByRole("button", { name: "Showing Maths · Show all" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(2);   // header + the maths row
    await userEvent.click(screen.getByRole("button", { name: "Showing Maths · Show all" }));
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd web && npx vitest run src/pages/__tests__/Assignments.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Add the scene and the filter**

In `web/src/pages/Assignments.tsx` add imports:

```tsx
import type { AssignmentTemplate, DueClassAssignment, RoomSnapshot, Subject } from "../api/types";
import { fmtDate, providerLabel, schemeLabel, SUBJECTS, subjectColor, subjectLabel } from "../lib/format";
import { ART, FILM } from "../scene/art";
import { Glow, Paper } from "../scene/effects";
import { Scene, type Hotspot } from "../scene/Scene";
import { useDeviceTier } from "../scene/useDeviceTier";
```

Inside `Assignments()` add state and loads after `fileRef`:

```tsx
  const [filter, setFilter] = useState<Subject | null>(null);
  const [due, setDue] = useState<DueClassAssignment[]>([]);
  const [marking, setMarking] = useState(0);
  const tier = useDeviceTier();
  useEffect(() => {
    // Both are decoration for the scene: a failure leaves the desk quiet and the page says nothing.
    api.get<DueClassAssignment[]>("/api/class-assignments/due?days=7").then(setDue).catch(() => {});
    api.get<RoomSnapshot>("/api/room").then((s) => setMarking(s.counts.read + s.counts.mark + s.counts.check + s.counts.queued)).catch(() => {});
  }, []);
```

Before the `return`, build the hotspots:

```tsx
  /** Rack slots, left to right along the folder rack in the painting. */
  const RACK = [{ left: "57%", top: "36%" }, { left: "61%", top: "39%" }, { left: "65%", top: "42%" }, { left: "69%", top: "45%" }, { left: "73%", top: "48%" }];
  const bySubject = SUBJECTS.filter((s) => (rows ?? []).some((t) => t.subject === s));
  const hotspots: Hotspot[] = [
    ...bySubject.map((s, i) => {
      const titles = (rows ?? []).filter((t) => t.subject === s);
      return { id: `rack-${s}`, ...RACK[i], color: subjectColor[s], label: `${subjectLabel[s]} · ${titles.length} folder${titles.length === 1 ? "" : "s"}`,
        sub: titles.slice(0, 2).map((t) => t.title).join(" · "), onPick: () => setFilter((f) => (f === s ? null : s)) };
    }),
    { id: "pad", left: "46%", top: "46%", label: "Blank pad", sub: "Start a new assignment", href: "/assignments/new" },
    ...(due.length > 0
      ? [{ id: "pinboard", left: "37%", top: "22%", label: "Pinboard · due this week", sub: due.slice(0, 3).map((d) => `${d.class_name} · ${d.title} · ${fmtDate(d.due_at)}`).join(" · "), href: `/classes/${due[0].class_id}/assignments/${due[0].id}` }]
      : [{ id: "pinboard", left: "37%", top: "22%", label: "Pinboard", sub: "Nothing due this week", onPick: () => {} }]),
    { id: "lamp", left: "36%", top: "44%", label: marking > 0 ? `Marking now · ${marking} script${marking === 1 ? "" : "s"}` : "Lamp", sub: marking > 0 ? "On the desks in the Marking Room" : "Lights up while scripts are being marked", href: "/room" },
  ];
  const effects = <>
    {marking > 0 && <Glow left="37%" top="46%" size="16%" />}
    {due.length > 0 && <Paper left="36%" top="24%" />}
  </>;
  const shown = (rows ?? []).filter((t) => !filter || t.subject === filter);
```

Change the header `<h1>Assignments</h1>` to `<h1>Your desk</h1>` and its meta to "Papers, mark schemes and rubrics you have saved, filed by subject. Pull a folder to edit it or set it for a class; the blank pad starts a new one." Add the count pill to the `actions`: `{rows && <span className="pill pill-outline tabular">{rows.length} folder{rows.length === 1 ? "" : "s"} · {rows.reduce((n, t) => n + (t.class_assignment_count ?? 0), 0)} class sets</span>}`.

After the notices and before the empty state insert:

```tsx
      <Scene name="The teacher's desk" art={ART.desk} film={FILM.desk} alt="A wooden teacher's desk with a lamp, a stack of worksheets, a rack of coloured folders and a pinboard" hotspots={hotspots} effects={effects} tier={tier} />
      {filter && <div className="actions" style={{ marginTop: 12 }}><button type="button" className="btn btn-sm btn-secondary" onClick={() => setFilter(null)}>{`Showing ${subjectLabel[filter]} · Show all`}</button></div>}
```

In the table, map over `shown` instead of `rows`, and give each `<td>` of the title column a leading tab: change the first cell to `<td style={{ borderLeft: \`6px solid ${subjectColor[t.subject]}\` }}>`.

Append to `app.css`: `.table.tall td:first-child { padding-left: 14px; }`.

- [ ] **Step 4: Run the test and the type check**

Run: `cd web && npx vitest run src/pages/__tests__/Assignments.test.tsx && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/Assignments.tsx web/src/pages/__tests__/Assignments.test.tsx web/src/styles/app.css
git commit -m "feat(web): the teacher's desk on Assignments — folder rack filter, pinboard, lamp"
```

---

### Task 6: The marking desk on Review

**Files:**
- Modify: `web/src/pages/Review.tsx:236-251` (the `Review` wrapper) and `ReviewParts` (one callback), `web/src/components/CorrectionsTab.tsx` (optional `onReleased`), `web/src/pages/__tests__/Review.test.tsx`

**Interfaces:**
- Consumes: `GET /api/review/summary` → `ReviewSummary`, `Scene`, effects `Flag`, `Paper`, `Stamp`, `Tick`.
- Produces: `ReviewParts({ onSettled }: { onSettled: () => void })`; `CorrectionsTab` gains `onReleased?: () => void` called after a successful release; `CorrectionsPane({ onReleased })`.

- [ ] **Step 1: Write the failing test**

Read `web/src/pages/__tests__/Review.test.tsx` first; add `"GET /api/review/summary"` to its mocks returning `{ needs_you: 2, remarked: 1, ready_to_release: 1, ready_sets: [{ id: 3, class_id: 1, class_name: "2E3", title: "Acids and bases" }] }` wherever it mocks fetch, then add:

```tsx
  it("shows the marking desk with the trays and drawers wired to the tabs", async () => {
    // mount as the file does, on /review
    expect(await screen.findByText("The marking desk")).toBeInTheDocument();
    expect(screen.getByText("2 need you")).toBeInTheDocument();
    expect(screen.getByText("1 ready to release")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ready to release · 1 class set/ })).toHaveAttribute("href", "/classes/1/assignments/3");
    await userEvent.click(screen.getByRole("button", { name: /Corrections drawer · 1 re-marked/ }));
    expect(screen.getByRole("button", { name: "Corrections" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: /Needs you · 2 parts/ }));
    expect(screen.getByRole("button", { name: "Parts" })).toHaveAttribute("aria-pressed", "true");
  });
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd web && npx vitest run src/pages/__tests__/Review.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Wire the scene**

In `web/src/components/CorrectionsTab.tsx` add `onReleased?: () => void` to the props and call `onReleased?.()` right after the release request succeeds (next to where the "Released N correction" notice is set).

In `web/src/pages/Review.tsx`:

- `ReviewParts` takes `{ onSettled }: { onSettled: () => void }` and calls `onSettled()` right after `refreshQueue()` in `save`.
- `CorrectionsPane` takes `{ onReleased }: { onReleased: () => void }` and passes `onReleased={onReleased}` to `<CorrectionsTab>`.
- Replace the `Review` wrapper with:

```tsx
export function Review() {
  const [params, setParams] = useSearchParams();
  const { needsYou } = useOutletContext<{ refreshQueue: () => void; needsYou?: number }>();
  const tab = params.get("tab") === "corrections" || params.has("ca") ? "corrections" : "parts";
  const choose = (t: "parts" | "corrections") => setParams((p) => { const n = new URLSearchParams(p); if (t === "parts") { n.delete("tab"); n.delete("ca"); } else n.set("tab", "corrections"); return n; }, { replace: true });
  const tier = useDeviceTier();
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [cue, setCue] = useState<Cue | null>(null);
  const play = (name: string) => setCue((c) => ({ name, key: (c?.key ?? 0) + 1 }));
  const loadSummary = useCallback(() => { api.get<ReviewSummary>("/api/review/summary").then(setSummary).catch(() => {}); }, []);
  useEffect(() => { loadSummary(); }, [loadSummary]);
  const n = summary?.needs_you ?? needsYou ?? 0;
  const ready = summary?.ready_sets ?? [];
  const hotspots: Hotspot[] = [
    { id: "flagged", left: "30%", top: "38%", color: "var(--crew-marker)", label: `Needs you · ${n} part${n === 1 ? "" : "s"}`, sub: "Marker and Checker disagree", onPick: () => choose("parts") },
    ready.length > 0
      ? { id: "ticked", left: "66%", top: "30%", color: "var(--mint)", label: `Ready to release · ${summary!.ready_to_release} class set${summary!.ready_to_release === 1 ? "" : "s"}`, sub: ready.map((s) => `${s.class_name} · ${s.title}`).join(" · "), href: `/classes/${ready[0].class_id}/assignments/${ready[0].id}` }
      : { id: "ticked", left: "66%", top: "30%", color: "var(--mint)", label: "Ready to release · none yet", sub: "Finished class sets wait here", onPick: () => {} },
    { id: "parts-drawer", left: "31%", top: "56%", label: "Parts drawer", sub: "Every part that needs a decision", onPick: () => choose("parts") },
    { id: "corrections-drawer", left: "36%", top: "62%", label: `Corrections drawer${summary && summary.remarked > 0 ? ` · ${summary.remarked} re-marked` : ""}`, sub: "Student corrections, re-marked by the Marker", onPick: () => choose("corrections") },
    { id: "checker", left: "50%", top: "14%", color: "var(--crew-checker)", label: "Checker", sub: "Flags the parts she and the Marker read differently", href: "/room" },
  ];
  const effects = <>
    {n > 0 && <Flag left="27.5%" top="38%" />}
    <Paper left="30%" top="43%" />
    <Tick left="48%" top="47%" />
    <Stamp left="65%" top="33%" text="RELEASED" />
  </>;
  return (
    <div className="page">
      <div className="page-header">
        <div><h1>The marking desk</h1><p className="meta">The Checker keeps two trays: the flagged tray holds the parts where she and the Marker disagree, the ticked tray holds what is ready to release. The drawers are Parts and Corrections.</p></div>
        <div className="actions">
          <span className="pill pill-crew-marker tabular">{n} need{n === 1 ? "s" : ""} you</span>
          {summary && <span className="pill tabular" style={{ background: "var(--mint)" }}>{summary.ready_to_release} ready to release</span>}
        </div>
      </div>
      <Scene name="The marking desk" art={ART.review} film={FILM.review} alt="The Checker at a wooden desk with a red pen, a magnifier, a stamp, a flagged tray and a ticked tray" hotspots={hotspots} effects={effects} cue={cue} tier={tier} />
      <div className="actions" role="group" aria-label="Review" style={{ margin: "16px 0 12px" }}>
        <button type="button" className={`btn ${tab === "parts" ? "btn-primary" : "btn-secondary"}`} aria-pressed={tab === "parts"} onClick={() => choose("parts")}>Parts</button>
        <button type="button" className={`btn ${tab === "corrections" ? "btn-primary" : "btn-secondary"}`} aria-pressed={tab === "corrections"} onClick={() => choose("corrections")}>Corrections</button>
      </div>
      {tab === "parts" ? <ReviewParts onSettled={() => { play("settle"); loadSummary(); }} /> : <CorrectionsPane onReleased={() => { play("stamp"); loadSummary(); }} />}
    </div>
  );
}
```

Add the imports: `ReviewSummary` to the types import; `ART, FILM` from `../scene/art`; `Flag, Paper, Stamp, Tick` from `../scene/effects`; `Scene, type Cue, type Hotspot` from `../scene/Scene`; `useDeviceTier` from `../scene/useDeviceTier`. Keep `ReviewParts`'s own `<div className="page">` wrappers as they are (the outer page padding is fine on top of them; if the double padding looks wrong, change the inner ones to plain `<div>`).

- [ ] **Step 4: Run the Review and CorrectionsTab tests and the type check**

Run: `cd web && npx vitest run src/pages/__tests__/Review.test.tsx src/components/__tests__/CorrectionsTab.test.tsx && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/Review.tsx web/src/components/CorrectionsTab.tsx web/src/pages/__tests__/Review.test.tsx
git commit -m "feat(web): the marking desk on Review — trays, drawers, settle and stamp cues"
```

---

### Task 7: The library on Learning

**Files:**
- Modify: `web/src/pages/Learning.tsx`, `web/src/pages/__tests__/Learning.test.tsx`

**Interfaces:**
- Consumes: `notes`, `ex`, `stats` already loaded; `Scene`, effects `Glow`, `Star`, `Book`.
- Produces: a `filterOn` state; the shelves set `subject` and `filterOn`.

- [ ] **Step 1: Write the failing test**

Read `web/src/pages/__tests__/Learning.test.tsx`; its mocks return notes and exemplars. Add:

```tsx
  it("shows the library, filters both tables from a shelf, and clears the filter", async () => {
    // mount with two notes: { subject: "math", status: "active" } and { subject: "language", status: "draft" }, and one math exemplar
    expect(await screen.findByText("The library")).toBeInTheDocument();
    expect(screen.getByText("1 active ruling · 1 example")).toBeInTheDocument();
    expect(screen.getByText("1 draft to approve")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^Maths shelf · 1 ruling/ }));
    expect(screen.getByLabelText("Subject")).toHaveValue("math");
    expect(screen.queryByText(/language/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Showing Maths · Show all" }));
    expect(screen.getByText("language")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd web && npx vitest run src/pages/__tests__/Learning.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Add the scene and the filter**

In `web/src/pages/Learning.tsx` add imports (`subjectColor` from format; `ART, FILM` from `../scene/art`; `Book, Glow, Star` from `../scene/effects`; `Scene, type Cue, type Hotspot` from `../scene/Scene`; `useDeviceTier` from `../scene/useDeviceTier`) and state after `error`:

```tsx
  const [filterOn, setFilterOn] = useState(false);
  const [cue, setCue] = useState<Cue | null>(null);
  const tier = useDeviceTier();
  const play = (name: string) => setCue((c) => ({ name, key: (c?.key ?? 0) + 1 }));
```

Make `approveNote` and `approveEx` call `play("shelve")` after their `await load()`.

Before the `return`:

```tsx
  /** Shelf positions per subject, in SUBJECTS order, on the library painting. */
  const SHELF = [{ left: "34%", top: "40%" }, { left: "43%", top: "30%" }, { left: "57%", top: "30%" }, { left: "38%", top: "34%" }, { left: "52%", top: "24%" }];
  const active = notes.filter((n) => n.status === "active");
  const drafts = notes.filter((n) => n.status !== "active").length + ex.filter((e) => e.status !== "active").length;
  const marked = stats?.marker?.count ?? 0;
  const hotspots: Hotspot[] = [
    ...SUBJECTS.map((s, i) => {
      const r = active.filter((n) => n.subject === s).length; const x = ex.filter((e) => e.subject === s).length;
      return { id: `shelf-${s}`, ...SHELF[i], color: subjectColor[s], label: `${subjectLabel[s]} shelf · ${r} ruling${r === 1 ? "" : "s"}`, sub: `${x} example${x === 1 ? "" : "s"}`, onPick: () => { setSubject(s); setFilterOn(true); } };
    }),
    { id: "table", left: "47%", top: "57%", color: "var(--gold)", label: `Reading table · ${drafts} draft${drafts === 1 ? "" : "s"}`, sub: "Approve to use them on the next run", onPick: () => document.getElementById("rubric-notes")?.scrollIntoView({ behavior: "smooth" }) },
    { id: "board", left: "73%", top: "31%", color: "var(--mint)", label: `Notice board · ${ex.length} example${ex.length === 1 ? "" : "s"}`, sub: "Answers you marked by hand, with why they matter", onPick: () => document.getElementById("exemplars")?.scrollIntoView({ behavior: "smooth" }) },
    { id: "trophy", left: "50%", top: "12%", label: "Trophy", sub: `${marked} script${marked === 1 ? "" : "s"} marked so far`, onPick: () => {} },
  ];
  const effects = <>
    {drafts > 0 && <Glow left="50.5%" top="54%" size="14%" />}
    <Star left="48%" top="17%" /><Star left="52.5%" top="21%" delay={0.8} />
    <Book left="43.5%" top="38%" color={subjectColor[subject]} />
  </>;
  const shownNotes = filterOn ? notes.filter((n) => n.subject === subject) : notes;
  const shownEx = filterOn ? ex.filter((e) => e.subject === subject) : ex;
```

Change the header: `<h1>The library</h1>` with meta "What the Marker has learned from your corrections, shelved by subject. Drafts wait on the reading table until you approve them; the notice board keeps the worked examples." Add to the header's `actions`, before the select: `<span className="pill pill-outline tabular">{active.length} active ruling{active.length === 1 ? "" : "s"} · {ex.length} example{ex.length === 1 ? "" : "s"}</span>` and `<span className="pill tabular" style={{ background: "var(--butter)" }}>{drafts} draft{drafts === 1 ? "" : "s"} to approve</span>`.

Insert after the notices, before the stats strip:

```tsx
      <Scene name="The library" art={ART.library} film={FILM.library} alt="A library nook with bookshelves, a reading table with an open book, a notice board, a beanbag and a trophy" hotspots={hotspots} effects={effects} cue={cue} tier={tier} />
      {filterOn && <div className="actions" style={{ margin: "12px 0" }}><button type="button" className="btn btn-sm btn-secondary" onClick={() => setFilterOn(false)}>{`Showing ${subjectLabel[subject]} · Show all`}</button></div>}
```

Give the two headings ids: `<h4 id="rubric-notes">Rubric notes</h4>` and `<h4 id="exemplars" ...>Exemplar cases</h4>`; map the tables over `shownNotes` and `shownEx`; add a subject dot to each row's subject cell: `<td><i className="dot" style={{ background: subjectColor[n.subject as Subject] ?? "var(--oak)", marginRight: 6 }} aria-hidden />{n.subject}</td>` (import `Subject` is already there).

- [ ] **Step 4: Run the test and the type check**

Run: `cd web && npx vitest run src/pages/__tests__/Learning.test.tsx && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/Learning.tsx web/src/pages/__tests__/Learning.test.tsx
git commit -m "feat(web): the library on Learning — shelves filter, reading table, notice board, trophy"
```

---

### Task 8: Documentation and whole-branch verification

**Files:**
- Modify: `README.md` (the feature list that mentions the Marking Room), `docs/setup-guide/README.md` (steps 7, 5/13, 12 and the Learning mention), `docs/superpowers/specs/2026-10-09-school-scenes-design.md` (status line)

- [ ] **Step 1: Docs**

In `README.md`, next to the Marking Room bullet, add: "Classes is a school of classroom tiles, Assignments a teacher's desk, Review the Checker's marking desk and Learning a library: the pictures are controls, with labels on hover, a Show labels switch, a 3 s tour, and film loops that switch off under reduced motion."

In `docs/setup-guide/README.md`: in the step that creates a class, say the button is now **Build a classroom** and that a subject picks the classroom's painting; in the assignments step, mention the folder rack filters the table and the pinboard shows what is due this week; in the review step, mention the trays and drawers; in the Learning mention, the shelves. Screenshots are added after deployment (the guide kit in the scratchpad), not in this task.

Set the spec's status line to `**Status:** implemented (this plan)`.

- [ ] **Step 2: Run everything**

```bash
uv run python -m pytest -q
cd web && npx vitest run && npx tsc --noEmit && npm run build
```

With a scratch Postgres (recipe in the memory note "Test migrations on Postgres"): `SMS_TEST_PG_URL=postgresql+psycopg://sms@127.0.0.1:54329/smstest uv run python -m pytest tests/unit/test_migrations_postgres.py -q`.

Expected: all PASS; the build succeeds.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/setup-guide/README.md docs/superpowers/specs/2026-10-09-school-scenes-design.md
git commit -m "docs: school scenes in the README and the setup guide"
```

---

## Self-review

- **Spec coverage.** §3.1 shared behaviour → Task 3 (labels, Show labels default and storage, Tour once round, film gate with Save-Data and the Film switch, cues, static tier). §3.2 school → Task 4 (tiles by subject with derivation in Task 1, state effects, plot, empty state, archived cards, class page select). §3.3 desk → Task 5 (rack filter with visible chip, pad, pinboard via Task 2's due route, lamp via `/api/room`, row tabs). §3.4 marking desk → Task 6 (trays and drawers, summary route from Task 2, settle and stamp cues). §3.5 library → Task 7 (shelves filter, table and board scroll, trophy from stats, shelve cue). §4.2 art → committed before Task 1. §4.3 backend → Tasks 1 and 2. §5 error handling → decoration calls swallow errors (Tasks 5 to 7), film `onError` (Tasks 3 and 4). §7 testing → each task; Postgres chain in Tasks 1 and 8.
- **Placeholder scan.** Tasks 4 to 7 tell the implementer to read the existing page test and reuse its mocking helper; the assertions are given in full. No TBDs.
- **Type consistency.** `Hotspot`, `Cue`, `Scene` props, `useFilm` and `useSceneLabels` tuples, `ClassTile` props, `ReviewSummary`, `DueClassAssignment` and `subjectColor` are named the same in every task.

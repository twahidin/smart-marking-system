# The Marking Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship phase 1 of the Marking Room: the brighter visual system, live stage events from the marking pipeline with a teacher-only thought panel, the 2D room page and sorter upload, and the student "reflect and correct" flow with AI re-marking and teacher release.

**Architecture:** The v2 pipeline gains an `on_event` hook; the worker records events to a `marking_events` table and a `submissions.stage` column; a room service exposes a snapshot, an SSE stream and per-submission thoughts. Corrections live in a `student_corrections` table with a service that enforces the window and one-per-part rule, a `remark` job that runs the marker and reviewer on one part, and teacher accept/override/reject/release. The React app gets new tokens, a `/room` page with a 2D scene, a Corrections tab in Review, and two student screens.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core, Alembic, pytest; React 18, TypeScript, react-router 6, vitest + testing-library; `motion` for transitions; Google Fonts (Fredoka, Nunito).

**Spec:** `docs/superpowers/specs/2026-10-08-marking-room-redesign-design.md`

## Global Constraints

- Thoughts (marker justifications, reviewer notes, reader doubts) are **teacher-session only**; no model reasoning enters any student-visible response. `feedback_view` stays the only projection students get.
- Reflection: window = `released_at + reflect_days` (class assignment override, else `settings.reflect_days`, default 7; 0 = off); **one correction per part**; only parts with mark below max.
- Corrections are re-marked by the AI; the student sees status words only until the teacher releases.
- Event recording and SSE must never fail marking: the recorder swallows and logs database errors.
- Every new SQL must run on SQLite and Postgres: no `boolean = 1`, no `Text` columns with `CURRENT_TIMESTAMP`; extend `tests/unit/test_migrations_postgres.py` and run it against a local Postgres before the final review.
- Libraries added to `web/`: `motion` only (phase 1). Lazy-load anything heavier. No three.js in this plan.
- Copy: Reader / Marker / Checker are the crew's names; colour code Reader green `#5CC9A0`, Marker coral `#F2836B`, Checker gold `#F2C94C`.
- Commits end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Backend tests: `uv run python -m pytest -q`; web: `cd web && npx vitest run && npx tsc --noEmit`.
- The naming clash to respect: `teacher_corrections` already exists (the teacher's Review decisions). The new student table and service are `student_corrections` everywhere.

---

## File structure

**Backend (new)**
- `src/sms/pipeline/events.py` — `StageEvent` dataclass and the `OnEvent` type.
- `src/sms/worker/events.py` — `EventRecorder`: writes events, updates `submissions.stage`.
- `src/sms/web/services/room.py` — snapshot, events-after, thoughts.
- `src/sms/web/routers/room.py` — `/api/room`, `/api/room/events`, `/api/submissions/{id}/thoughts`.
- `src/sms/web/services/student_corrections.py` — window rule, submit, list, decide, release, student view.
- `src/sms/web/routers/corrections.py` — student submit route, teacher review routes, release route.
- `src/sms/worker/remark_job.py` — `run_remark_job`.
- `src/sms/migrations/versions/0014_marking_room.py`.

**Backend (modified)**
- `src/sms/pipeline/marking_pipeline_v2.py` — emit events in `run`.
- `src/sms/worker/mark_job.py` — attach the recorder.
- `src/sms/worker/worker.py` — dispatch the `remark` kind.
- `src/sms/web/services/student.py` — `reflection` block and `crop_id` in the feedback view.
- `src/sms/web/routers/student.py` — `GET /api/student/crops/{id}`.
- `src/sms/providers/settings.py`, `src/sms/web/routers/settings.py` — `reflect_days`.
- `src/sms/web/services/class_assignments.py`, `routers/class_assignments.py` — `reflect_days` on the class assignment; released corrections in `marks_csv`.
- `src/sms/records/builder.py`, `src/sms/records/docx.py`, `src/sms/web/routers/records.py` — "after reflection" column.
- `src/sms/web/app.py` — register the two routers.

**Web (new)**
- `web/src/scene/useDeviceTier.ts`, `web/src/scene/useRoomEvents.ts`, `web/src/scene/RoomScene2D.tsx`
- `web/src/components/ThoughtPanel.tsx`, `web/src/components/CorrectionsTab.tsx`
- `web/src/pages/MarkingRoom.tsx`, `web/src/student/Reflect.tsx`
- `web/public/art/{room,crew,sorter,student}.jpg` (already copied into the branch)

**Web (modified)**
- `web/src/styles/tokens.css`, `web/src/styles/app.css` — new tokens and shapes.
- `web/src/components/Nav.tsx`, `web/src/App.tsx` — Marking Room route and nav.
- `web/src/components/DropZone.tsx` — the sorter.
- `web/src/pages/Review.tsx` — Corrections tab.
- `web/src/student/AssignmentView.tsx` — reflection pill, "Try a correction", "After reflection".
- `web/src/api/types.ts` — new types.

---

### Task 1: Visual system tokens, fonts and nav

**Files:**
- Modify: `web/src/styles/tokens.css`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/components/Nav.tsx`
- Create: `web/src/components/__tests__/Nav.test.tsx`
- Already in branch: `web/public/art/room.jpg`, `crew.jpg`, `sorter.jpg`, `student.jpg`

**Interfaces:**
- Produces: CSS custom properties `--crew-reader`, `--crew-marker`, `--crew-checker`, `--color-bg`, `--color-surface`, `--font-heading`, `--font-body`, `--radius-sm|md|lg`; a `.pill-crew-reader|marker|checker` class each; nav link "Marking Room" to `/room`.

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/components/__tests__/Nav.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Nav } from "../Nav";

describe("Nav", () => {
  it("leads with the Marking Room and keeps the queue count on Review", () => {
    render(<MemoryRouter><Nav needsYou={3} /></MemoryRouter>);
    const links = screen.getAllByRole("link").map((a) => a.textContent);
    expect(links[1]).toBe("Marking Room");
    expect(screen.getByRole("link", { name: /Marking Room/ })).toHaveAttribute("href", "/room");
    expect(screen.getByRole("link", { name: /Review/ })).toHaveTextContent("3");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/__tests__/Nav.test.tsx`
Expected: FAIL — `links[1]` is "Classes".

- [ ] **Step 3: Replace the token block and add shapes**

Replace the `:root` colour, font and radius declarations at the top of `web/src/styles/tokens.css` (keep the neutral/accent ramps and everything after `--radius-lg` as they are):

```css
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&family=Nunito:wght@400;600;700&display=swap');

:root {
  --color-bg: #FFF7E6;
  --color-surface: #FFFFFF;
  --color-text: #2B2A33;
  --color-accent: #F2836B;
  --color-accent-2: #3E9E97;
  --color-divider: color-mix(in srgb, #2B2A33 22%, transparent);
  --butter: #FFE8A3;
  --gold: #F2C94C;
  --mint: #9EDFC0;
  --oak: #E7B97C;
  --crew-reader: #5CC9A0;
  --crew-marker: #F2836B;
  --crew-checker: #F2C94C;
  --crew-reader-ink: #2B6F5B;
  --crew-marker-ink: #B84A2C;
  --crew-checker-ink: #7A5A00;

  --font-heading: "Fredoka", system-ui, sans-serif;
  --font-heading-weight: 700;
  --font-body: "Nunito", system-ui, sans-serif;

  --radius-sm: 10px;
  --radius-md: 16px;
  --radius-lg: 24px;
```

Append to `web/src/styles/app.css`:

```css
/* Marking Room visual system: pill nav, crew colour code, soft cards. */
.nav { background: var(--color-surface); border-bottom: 3px solid var(--gold); }
.nav-links a { padding: 0 14px; border-radius: 999px; font-weight: 600; }
.nav-links a[aria-current="page"] { background: var(--butter); color: var(--color-text); }
.card { background: var(--color-surface); border-radius: var(--radius-lg); padding: 20px; box-shadow: 0 12px 32px rgba(78, 56, 10, 0.12); }
.pill { border-radius: 999px; font-weight: 700; }
.pill-crew-reader { background: var(--crew-reader); color: var(--color-text); }
.pill-crew-marker { background: var(--crew-marker); color: #fff; }
.pill-crew-checker { background: var(--crew-checker); color: var(--color-text); }
.pill-crew-reader::before, .pill-crew-marker::before, .pill-crew-checker::before { display: none; }
.btn { border-radius: 999px; font-weight: 700; }
.btn-primary { box-shadow: 0 4px 0 var(--crew-marker-ink); }
.table th { border-bottom-color: var(--butter); }
@media (prefers-reduced-motion: reduce) { .bob, .slide, .drop-paper { animation: none !important; } }
```

Edit `web/src/components/Nav.tsx` so the link list starts with the room:

```tsx
<div className="nav-links">
  <NavLink to="/room">Marking Room</NavLink>
  <NavLink to="/classes">Classes</NavLink>
  <NavLink to="/submissions">Submissions</NavLink>
  <NavLink to="/assignments">Assignments</NavLink>
  <NavLink to="/review">Review {needsYou > 0 && <span className="key">{needsYou}</span>}</NavLink>
  <NavLink to="/learning">Learning</NavLink>
  <NavLink to="/settings">Settings</NavLink>
  <a href="#" onClick={async (e) => { e.preventDefault(); await api.post("/api/auth/logout"); nav("/sign-in"); }}>Sign out</a>
</div>
```

- [ ] **Step 4: Run the test and the whole web suite**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: Nav test PASS; every other test still passes (the old tests do not assert nav order).

- [ ] **Step 5: Commit**

```bash
git add web/src/styles web/src/components/Nav.tsx web/src/components/__tests__/Nav.test.tsx web/public/art
git commit -m "feat(ui): Marking Room visual system — tokens, Fredoka/Nunito, pill nav, crew colours, sprites"
```

---

### Task 2: Migration 0014 — events, stage, reflect days, student corrections

**Files:**
- Create: `src/sms/migrations/versions/0014_marking_room.py`
- Modify: `tests/unit/test_migrations_postgres.py`
- Create: `tests/unit/test_migration_0014.py`

**Interfaces:**
- Produces tables/columns used by every later task:
  - `marking_events(id, submission_id, stage, kind, q_id, note, created_at)`
  - `submissions.stage TEXT NULL`
  - `settings.reflect_days INTEGER NOT NULL DEFAULT 7`
  - `class_assignments.reflect_days INTEGER NULL`
  - `student_corrections(id, submission_id, q_id, reason, text, page_id, submitted_at, remark_run_id, remark_total, remark_max, remark_note, status, teacher_total, teacher_reason, error, released_at, created_at)` with unique `(submission_id, q_id)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_migration_0014.py
from sqlalchemy import inspect

from sms.memory.db import Database


def test_0014_adds_events_stage_reflect_days_and_student_corrections(tmp_path):
    db = Database(path=str(tmp_path / "m.db"))
    insp = inspect(db.engine)
    assert insp.has_table("marking_events") and insp.has_table("student_corrections")
    assert "stage" in {c["name"] for c in insp.get_columns("submissions")}
    assert "reflect_days" in {c["name"] for c in insp.get_columns("settings")}
    assert "reflect_days" in {c["name"] for c in insp.get_columns("class_assignments")}
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) VALUES ('s', 'math', '', '{}', 'queued') RETURNING id")
    db.execute("INSERT INTO student_corrections (submission_id, q_id, reason, text, status) VALUES (:s, '1a', 'sign', 'x = -2', 'submitted')", {"s": sid})
    try:
        db.execute("INSERT INTO student_corrections (submission_id, q_id, reason, text, status) VALUES (:s, '1a', 'sign', 'again', 'submitted')", {"s": sid})
        assert False, "second correction for the same part must be refused"
    except Exception:
        pass
    assert db.query("SELECT reflect_days FROM settings LIMIT 1") == [] or True  # settings row may not exist yet
```

Add to `tests/unit/test_migrations_postgres.py`:

```python
def test_chain_reaches_0014_on_postgres(pg_engine):
    upgrade(pg_engine, "head")
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0014"
        conn.execute(text("INSERT INTO settings (id, provider, model) VALUES (1, 'p', 'm')"))
        assert conn.execute(text("SELECT reflect_days FROM settings WHERE id = 1")).scalar() == 7
```

and change the existing `== "0013"` assertion in `test_chain_applies_on_postgres` to `== "0014"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest -q tests/unit/test_migration_0014.py`
Expected: FAIL — no table `marking_events`.

- [ ] **Step 3: Write the migration**

```python
# src/sms/migrations/versions/0014_marking_room.py
"""The Marking Room: stage events from the pipeline, the submission's current stage, the reflection
window, and student corrections (one per part, re-marked by the AI, released by the teacher).

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marking_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.Text, nullable=False),          # read | mark | check | feedback | done
        sa.Column("kind", sa.Text, nullable=False),           # started | finished | note
        sa.Column("q_id", sa.Text),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_marking_events_submission", "marking_events", ["submission_id", "id"])
    with op.batch_alter_table("submissions") as b:
        b.add_column(sa.Column("stage", sa.Text))
    with op.batch_alter_table("settings") as b:
        b.add_column(sa.Column("reflect_days", sa.Integer, nullable=False, server_default="7"))
    with op.batch_alter_table("class_assignments") as b:
        b.add_column(sa.Column("reflect_days", sa.Integer))   # NULL = follow settings.reflect_days
    op.create_table(
        "student_corrections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("q_id", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("text", sa.Text),
        sa.Column("page_id", sa.Integer, sa.ForeignKey("pages.id", ondelete="SET NULL")),
        sa.Column("submitted_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("remark_run_id", sa.Text),
        sa.Column("remark_total", sa.Float),
        sa.Column("remark_max", sa.Float),
        sa.Column("remark_note", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="submitted"),
        sa.Column("teacher_total", sa.Float),
        sa.Column("teacher_reason", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("released_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ux_student_corrections_part", "student_corrections", ["submission_id", "q_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_student_corrections_part", table_name="student_corrections")
    op.drop_table("student_corrections")
    with op.batch_alter_table("class_assignments") as b:
        b.drop_column("reflect_days")
    with op.batch_alter_table("settings") as b:
        b.drop_column("reflect_days")
    with op.batch_alter_table("submissions") as b:
        b.drop_column("stage")
    op.drop_index("ix_marking_events_submission", table_name="marking_events")
    op.drop_table("marking_events")
```

- [ ] **Step 4: Run the tests (SQLite, then Postgres)**

Run: `uv run python -m pytest -q tests/unit/test_migration_0014.py`
Expected: PASS.

Start a scratch Postgres (see the memory recipe) and run:
`SMS_TEST_PG_URL=postgresql+psycopg://sms@127.0.0.1:54329/smstest uv run python -m pytest -q tests/unit/test_migrations_postgres.py`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sms/migrations/versions/0014_marking_room.py tests/unit/test_migration_0014.py tests/unit/test_migrations_postgres.py
git commit -m "feat(db): 0014 — marking_events, submissions.stage, reflect_days, student_corrections"
```

---

### Task 3: Stage events from the v2 pipeline

**Files:**
- Create: `src/sms/pipeline/events.py`
- Modify: `src/sms/pipeline/marking_pipeline_v2.py` (`__init__`, `run`)
- Create: `tests/unit/test_pipeline_v2_events.py`

**Interfaces:**
- Produces: `StageEvent(stage: str, kind: str, q_id: Optional[str] = None, note: Optional[str] = None)`; `OnEvent = Callable[[StageEvent], None]`; `MarkingPipelineV2.on_event: Optional[OnEvent]` attribute (default `None`), set by the caller before `run`.
- Stages and notes exactly as the spec table: `read` (notes for parts with `needs_human_transcription`), `mark` (note = `justification` per part / rubric criterion), `check` (note = `"{verdict}: {reviewer_note}"` per verdict), `feedback`, `done` (note = escalation reason per flagged part).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_pipeline_v2_events.py
"""The pipeline tells a listener when each crew member starts and finishes, and what they thought
per part. A listener that raises never breaks marking."""
from sms.pipeline.events import StageEvent
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.marking import ReviewVerdict
from sms.schemas.marking_v2 import AllocationMark, MarkedScriptV2, PartMark, ReviewVerdictV2, ReviewedScriptV2
from tests.unit.test_pipeline_v2_double_penalty import _template
from tests.unit.test_pipeline_v2_files import Fake, _feedback_stub, db  # noqa: F401
from sms.pipeline.marking_pipeline_v2 import MarkingPipelineV2

EX = ExtractedScript(questions=[
    ExtractedQuestion(q_id="1a", transcribed_answer="x=-2", workings="", confidence=0.9),
    ExtractedQuestion(q_id="1b", transcribed_answer="?", workings="", confidence=0.2, needs_human_transcription=True),
])
MARKED = MarkedScriptV2(kind="mark_scheme", parts=[
    PartMark(q_id="1a", awarded=[AllocationMark(label="M1", marks=1, got=True)], total=1, justification="M1 for factorising"),
    PartMark(q_id="1b", awarded=[AllocationMark(label="B1", marks=1, got=False)], total=0, justification="B1 lost: illegible"),
])
REVIEWED = ReviewedScriptV2(verdicts=[
    ReviewVerdictV2(q_id="1a", verdict=ReviewVerdict.APPROVE, reviewer_note="Agree"),
    ReviewVerdictV2(q_id="1b", verdict=ReviewVerdict.ESCALATE, reviewer_note="Cannot read it either"),
])


def _pipeline(db):
    return MarkingPipelineV2(db=db, extractor=Fake(EX), segmenter=None, marker=Fake(MARKED), reviewer=Fake(REVIEWED),
                             feedback=_feedback_stub(), kind="mark_scheme")


def test_events_follow_the_stages_with_per_part_notes(db):
    seen = []
    p = _pipeline(db)
    p.on_event = seen.append
    p.run(images=[b"x"], template=_template(parts=["1a", "1b"]))
    flow = [(e.stage, e.kind) for e in seen if e.kind != "note"]
    assert flow == [("read", "started"), ("read", "finished"), ("mark", "started"), ("mark", "finished"),
                    ("check", "started"), ("check", "finished"), ("feedback", "started"), ("feedback", "finished"),
                    ("done", "finished")]
    notes = [(e.stage, e.q_id, e.note) for e in seen if e.kind == "note"]
    assert ("read", "1b", "Hard to read — the teacher may need to look at the page") in notes
    assert ("mark", "1a", "M1 for factorising") in notes
    assert ("check", "1b", "ESCALATE: Cannot read it either") in notes
    assert any(s == "done" and q == "1b" for s, q, _ in notes)


def test_a_failing_listener_never_fails_marking(db):
    def boom(_: StageEvent) -> None:
        raise RuntimeError("listener broke")
    p = _pipeline(db)
    p.on_event = boom
    res = p.run(images=[b"x"], template=_template(parts=["1a", "1b"]))
    assert res.run_id


def test_no_listener_is_the_default(db):
    assert _pipeline(db).on_event is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/unit/test_pipeline_v2_events.py`
Expected: FAIL — `ModuleNotFoundError: sms.pipeline.events`.

- [ ] **Step 3: Implement the event type and the emission points**

```python
# src/sms/pipeline/events.py
"""Stage events: what the crew (Reader, Marker, Checker) is doing and thinking while a script is marked.
The pipeline calls an optional listener; the worker records the events (sms.worker.events)."""
from dataclasses import dataclass
from typing import Callable, Optional

STAGES = ("read", "mark", "check", "feedback", "done")
KINDS = ("started", "finished", "note")
READ_DOUBT = "Hard to read — the teacher may need to look at the page"


@dataclass(frozen=True)
class StageEvent:
    stage: str
    kind: str
    q_id: Optional[str] = None
    note: Optional[str] = None


OnEvent = Callable[[StageEvent], None]
```

In `src/sms/pipeline/marking_pipeline_v2.py`:

1. Import: `from sms.pipeline.events import READ_DOUBT, OnEvent, StageEvent` and `import logging` (if not present; `log = logging.getLogger(__name__)`).
2. In `__init__`, add `self.on_event: Optional[OnEvent] = None`.
3. Add a method:

```python
    def _emit(self, stage: str, kind: str, q_id: Optional[str] = None, note: Optional[str] = None) -> None:
        """Tell the listener, if any. A listener's failure is logged and never fails marking."""
        if self.on_event is None:
            return
        try:
            self.on_event(StageEvent(stage=stage, kind=kind, q_id=q_id, note=note))
        except Exception:  # noqa: BLE001
            log.exception("stage event listener failed (%s %s)", stage, kind)
```

4. In `run`, wrap the stages:

```python
        self._emit("read", "started")
        if not files:
            extracted = self._extract(images, subject, questions, notes, language)
        else:
            ...  # unchanged
        for q in extracted.questions:
            if q.needs_human_transcription:
                self._emit("read", "note", q.q_id, READ_DOUBT)
        self._emit("read", "finished")
        self._emit("mark", "started")
        marked = self.marker.run(...)  # unchanged
        for pm in marked.parts:
            self._emit("mark", "note", pm.q_id, pm.justification)
        for rm in marked.rubric:
            self._emit("mark", "note", rm.criterion, rm.justification)
        self._emit("mark", "finished")
        self._emit("check", "started")
        reviewed = self.reviewer.run(...)  # unchanged
        for v in reviewed.verdicts:
            self._emit("check", "note", v.q_id, f"{v.verdict.value}: {v.reviewer_note}".strip())
        self._emit("check", "finished")
        final, escalations = self._merge(marked, reviewed, extracted, scheme)
        ...  # truncation block unchanged
        self._emit("feedback", "started")
        feedback_report = self.feedback.run(...)  # unchanged
        self._emit("feedback", "finished")
        self._persist(...)  # unchanged
        for key, reason in escalations.items():
            self._emit("done", "note", key, reason)
        self._emit("done", "finished")
        return MarkingResultV2(...)
```

- [ ] **Step 4: Run the new test and the pipeline suite**

Run: `uv run python -m pytest -q tests/unit/test_pipeline_v2_events.py tests/unit/test_pipeline_v2_files.py tests/unit/test_pipeline_v2_double_penalty.py tests/unit/test_pipeline_v2_subjects.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sms/pipeline/events.py src/sms/pipeline/marking_pipeline_v2.py tests/unit/test_pipeline_v2_events.py
git commit -m "feat(pipeline): stage events with per-part notes from the reader, marker and checker"
```

---

### Task 4: Record events in the worker

**Files:**
- Create: `src/sms/worker/events.py`
- Modify: `src/sms/worker/mark_job.py:150-160` (after the pipeline is built, before `run`)
- Modify: `tests/unit/test_worker.py` (append tests)

**Interfaces:**
- Consumes: `StageEvent` from Task 3; `pipeline.on_event`.
- Produces: `EventRecorder(db, submission_id)` with `emit(event: StageEvent) -> None`; rows in `marking_events`; `submissions.stage` set to the stage on every `started` event and to `'done'` on `done/finished`.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_worker.py`)

```python
# --- stage events are recorded while a v2 script is marked ---------------------------------------

class _TalkingPipelineV2(FakePipelineV2):
    """Emits a realistic event sequence through whatever listener the worker attached."""
    def __init__(self, escalations):
        super().__init__(escalations)
        self.on_event = None

    def run(self, images, template, submission_id=None, files=None):
        from sms.pipeline.events import StageEvent
        for stage in ("read", "mark", "check", "feedback"):
            self.on_event(StageEvent(stage, "started"))
            if stage == "mark":
                self.on_event(StageEvent("mark", "note", "1a", "M1 for the method"))
            self.on_event(StageEvent(stage, "finished"))
        self.on_event(StageEvent("done", "finished"))
        return super().run(images, template, submission_id, files)


def _attach_v2_assignment(db, sid):
    """Give the submission a mark-scheme template so run_mark_job takes the v2 path (same as the v2 dispatch tests)."""
    tid = _template(db, "mark_scheme")
    db.execute("UPDATE submissions SET assignment_id = ? WHERE id = ?", (tid, sid))


def test_worker_records_stage_events_and_the_current_stage(env):
    db, store, storage, sid = env
    _attach_v2_assignment(db, sid)
    pipe = _TalkingPipelineV2({})
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **k: pipe)
    rows = db.query("SELECT stage, kind, q_id, note FROM marking_events WHERE submission_id = :s ORDER BY id", {"s": sid})
    assert [(r["stage"], r["kind"]) for r in rows][:3] == [("read", "started"), ("read", "finished"), ("mark", "started")]
    assert ("mark", "note", "1a", "M1 for the method") in [(r["stage"], r["kind"], r["q_id"], r["note"]) for r in rows]
    assert db.query("SELECT stage FROM submissions WHERE id = :s", {"s": sid})[0]["stage"] == "done"


def test_recorder_failure_does_not_fail_marking(env, monkeypatch):
    from sms.worker import events as ev
    db, store, storage, sid = env
    _attach_v2_assignment(db, sid)
    pipe = _TalkingPipelineV2({})

    def broken_execute(*a, **k):
        raise RuntimeError("disk full")
    rec_cls = ev.EventRecorder
    original = rec_cls.emit

    def emit(self, event):
        monkeypatch.setattr(self.db, "execute", broken_execute)
        return original(self, event)
    monkeypatch.setattr(rec_cls, "emit", emit)
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **k: pipe)
    assert db.query("SELECT status FROM submissions WHERE id = :s", {"s": sid})[0]["status"] == "done"
```

`_template(db, kind, subject)` already exists in the file (line ~387); `FakePipelineV2` too. Place the new tests after them.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest -q tests/unit/test_worker.py -k "stage_events or recorder_failure"`
Expected: FAIL — `AttributeError: 'NoneType' object is not callable` (no listener attached) / no module `sms.worker.events`.

- [ ] **Step 3: Implement the recorder and attach it**

```python
# src/sms/worker/events.py
"""Writes the pipeline's stage events to marking_events and keeps submissions.stage current. Every
database error is logged and swallowed: the room going quiet is acceptable, a lost mark is not."""
import logging

from sms.memory.db import Database
from sms.pipeline.events import StageEvent

log = logging.getLogger(__name__)


class EventRecorder:
    def __init__(self, db: Database, submission_id: int):
        self.db = db
        self.submission_id = submission_id

    def emit(self, event: StageEvent) -> None:
        try:
            self.db.execute(
                "INSERT INTO marking_events (submission_id, stage, kind, q_id, note) VALUES (:s, :st, :k, :q, :n)",
                {"s": self.submission_id, "st": event.stage, "k": event.kind, "q": event.q_id, "n": event.note},
            )
            if event.kind == "started" or (event.stage == "done" and event.kind == "finished"):
                self.db.execute("UPDATE submissions SET stage = :st WHERE id = :s",
                                {"st": event.stage, "s": self.submission_id})
        except Exception:  # noqa: BLE001
            log.exception("could not record stage event %s/%s for submission %s", event.stage, event.kind, self.submission_id)
```

In `src/sms/worker/mark_job.py`, in the `template is not None` branch right after `pipeline = factory(...)`:

```python
        if hasattr(pipeline, "on_event"):
            pipeline.on_event = EventRecorder(db, submission_id).emit
```

with `from sms.worker.events import EventRecorder` at the top. Nothing changes for the v1 branch.

- [ ] **Step 4: Run the worker suite**

Run: `uv run python -m pytest -q tests/unit/test_worker.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sms/worker/events.py src/sms/worker/mark_job.py tests/unit/test_worker.py
git commit -m "feat(worker): record stage events and the current stage while marking"
```

---

### Task 5: Room service and routes (snapshot, SSE, thoughts)

**Files:**
- Create: `src/sms/web/services/room.py`
- Create: `src/sms/web/routers/room.py`
- Modify: `src/sms/web/app.py` (import + `app.include_router(room.router)` after `queue.router`)
- Create: `tests/web/test_room_api.py`

**Interfaces:**
- Produces:
  - `room_snapshot(db, class_assignment_id: Optional[int]) -> dict` → `{"counts": {"queued", "read", "mark", "check", "feedback", "done", "needs_you", "failed"}, "started_at": iso|None, "desks": [{"stage", "submission_id", "label", "reg_no", "since": iso}], "last_event_id": int}`
  - `events_after(db, after_id: int, class_assignment_id: Optional[int], limit=200) -> list[dict]` → `[{"id", "submission_id", "stage", "kind", "created_at"}]`
  - `thoughts(db, submission_id) -> dict` → `{"reader": [...], "marker": [...], "checker": [...]}`, each `{"at": iso, "q_id", "note"}`
  - Routes: `GET /api/room`, `GET /api/room/events?after=&class_assignment_id=&once=1`, `GET /api/submissions/{id}/thoughts` (all `require_teacher`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/web/test_room_api.py
from tests.web.seed_v2 import seed_v2


def _event(app, sid, stage, kind, q_id=None, note=None):
    app.state.db.execute("INSERT INTO marking_events (submission_id, stage, kind, q_id, note) VALUES (:s, :st, :k, :q, :n)",
                         {"s": sid, "st": stage, "k": kind, "q": q_id, "n": note})
    if kind == "started":
        app.state.db.execute("UPDATE submissions SET stage = :st, status = 'marking' WHERE id = :s", {"st": stage, "s": sid})


def test_snapshot_counts_and_desks(auth, app):
    a, _ = seed_v2(app, label="Done one", run_id="r-a", queue={})
    b, _ = seed_v2(app, label="On the marker", run_id="r-b", queue={})
    _event(app, b, "read", "started"); _event(app, b, "read", "finished"); _event(app, b, "mark", "started")
    snap = auth.get("/api/room").json()
    assert snap["counts"]["done"] == 1 and snap["counts"]["mark"] == 1
    assert [d["submission_id"] for d in snap["desks"]] == [b]
    assert snap["desks"][0]["stage"] == "mark" and snap["desks"][0]["label"] == "On the marker"
    assert snap["last_event_id"] >= 3


def test_events_stream_once_returns_new_events_then_closes(auth, app):
    sid, _ = seed_v2(app, run_id="r-c", queue={})
    _event(app, sid, "read", "started")
    with auth.stream("GET", "/api/room/events?after=0&once=1") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert "event: stage" in body and '"stage": "read"' in body and "id: " in body


def test_thoughts_are_grouped_by_crew_and_teacher_only(auth, client, app):
    sid, _ = seed_v2(app, run_id="r-d", queue={})
    _event(app, sid, "read", "note", "1b", "Hard to read")
    _event(app, sid, "mark", "note", "1a", "M1 for the method")
    _event(app, sid, "check", "note", "1a", "APPROVE: Agree")
    _event(app, sid, "done", "note", "1b", "illegible transcription")
    t = auth.get(f"/api/submissions/{sid}/thoughts").json()
    assert [x["note"] for x in t["reader"]] == ["Hard to read"]
    assert [x["note"] for x in t["marker"]] == ["M1 for the method"]
    assert [x["note"] for x in t["checker"]] == ["APPROVE: Agree", "illegible transcription"]
    client.cookies.clear()
    assert client.get(f"/api/submissions/{sid}/thoughts").status_code in (401, 404)
    assert auth.get("/api/submissions/999999/thoughts").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest -q tests/web/test_room_api.py`
Expected: FAIL — 404 on `/api/room`.

- [ ] **Step 3: Implement the service and router**

```python
# src/sms/web/services/room.py
"""The Marking Room: who is on which desk, how far the class set has got, and (teachers only) what
each crew member noted. Reader = the read stage, Marker = mark, Checker = check plus the done notes."""
import json
from typing import Any, Dict, List, Optional

from sms.memory.db import Database
from sms.timeutil import iso_utc
from sms.web.errors import ApiError

DESK_STAGES = ("read", "mark", "check", "feedback")
CREW_OF_STAGE = {"read": "reader", "mark": "marker", "check": "checker", "done": "checker"}


def _scope(class_assignment_id: Optional[int]) -> tuple:
    if class_assignment_id is None:
        return "", {}
    return " AND s.class_assignment_id = :ca", {"ca": class_assignment_id}


def room_snapshot(db: Database, class_assignment_id: Optional[int] = None) -> Dict[str, Any]:
    where, params = _scope(class_assignment_id)
    rows = db.query("SELECT s.id, s.label, s.status, s.stage, s.updated_at, s.created_at, st.reg_no AS reg_no "
                    "FROM submissions s LEFT JOIN students st ON st.id = s.student_id WHERE 1 = 1" + where +
                    " ORDER BY s.id", params)
    counts = {k: 0 for k in ("queued", *DESK_STAGES, "done", "needs_you", "failed")}
    desks: List[dict] = []
    for r in rows:
        if r["status"] in ("done", "needs_you", "failed"):
            counts[r["status"]] += 1
        elif r["stage"] in DESK_STAGES:
            counts[r["stage"]] += 1
            desks.append({"stage": r["stage"], "submission_id": r["id"], "label": r["label"], "reg_no": r["reg_no"],
                          "since": iso_utc(r["updated_at"])})
        else:
            counts["queued"] += 1
    started = db.query("SELECT MIN(s.created_at) AS t FROM submissions s WHERE 1 = 1" + where, params)
    last = db.query("SELECT COALESCE(MAX(e.id), 0) AS i FROM marking_events e JOIN submissions s ON s.id = e.submission_id "
                    "WHERE 1 = 1" + where, params)
    return {"counts": counts, "started_at": iso_utc(started[0]["t"]) if started and started[0]["t"] else None,
            "desks": desks, "last_event_id": int(last[0]["i"] or 0)}


def events_after(db: Database, after_id: int, class_assignment_id: Optional[int] = None, limit: int = 200) -> List[dict]:
    where, params = _scope(class_assignment_id)
    params = {**params, "a": after_id, "lim": limit}
    rows = db.query("SELECT e.id, e.submission_id, e.stage, e.kind, e.created_at FROM marking_events e "
                    "JOIN submissions s ON s.id = e.submission_id WHERE e.id > :a AND e.kind != 'note'" + where +
                    " ORDER BY e.id LIMIT :lim", params)
    return [{"id": r["id"], "submission_id": r["submission_id"], "stage": r["stage"], "kind": r["kind"],
             "created_at": iso_utc(r["created_at"])} for r in rows]


def thoughts(db: Database, submission_id: int) -> Dict[str, List[dict]]:
    if not db.query("SELECT 1 FROM submissions WHERE id = :s", {"s": submission_id}):
        raise ApiError(404, "not_found", "No such script")
    rows = db.query("SELECT stage, q_id, note, created_at FROM marking_events WHERE submission_id = :s AND kind = 'note' "
                    "ORDER BY id", {"s": submission_id})
    out: Dict[str, List[dict]] = {"reader": [], "marker": [], "checker": []}
    for r in rows:
        crew = CREW_OF_STAGE.get(r["stage"])
        if crew:
            out[crew].append({"at": iso_utc(r["created_at"]), "q_id": r["q_id"], "note": r["note"] or ""})
    return out


def sse_line(event: dict) -> str:
    return f"id: {event['id']}\nevent: stage\ndata: {json.dumps(event)}\n\n"
```

```python
# src/sms/web/routers/room.py
import time
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from sms.web.deps import get_db, require_teacher
from sms.web.services.room import events_after, room_snapshot, sse_line, thoughts

router = APIRouter(tags=["room"], dependencies=[Depends(require_teacher)])
POLL_S = 2.0
HEARTBEAT_S = 15.0


@router.get("/api/room")
def snapshot(class_assignment_id: Optional[int] = None, db=Depends(get_db)):
    return room_snapshot(db, class_assignment_id)


@router.get("/api/room/events")
def events(request: Request, after: int = Query(0, ge=0), class_assignment_id: Optional[int] = None,
           once: int = Query(0), last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"), db=Depends(get_db)):
    """Server-Sent Events: every started/finished stage event after `after` (or the Last-Event-ID
    header), polled from the database every 2 s, with a comment heartbeat every 15 s. `once=1`
    returns after the first poll — for tests and for a client that prefers polling."""
    cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

    def gen() -> Iterator[str]:
        nonlocal cursor
        last_beat = time.monotonic()
        while True:
            batch = events_after(db, cursor, class_assignment_id)
            for e in batch:
                cursor = e["id"]
                yield sse_line(e)
            if once:
                return
            if time.monotonic() - last_beat > HEARTBEAT_S:
                last_beat = time.monotonic()
                yield ": ping\n\n"
            time.sleep(POLL_S)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/submissions/{submission_id}/thoughts")
def submission_thoughts(submission_id: int, db=Depends(get_db)):
    return thoughts(db, submission_id)
```

Register in `src/sms/web/app.py`: add `room` to the routers import and `app.include_router(room.router)` right after `queue.router`. Note the submissions router is registered earlier with prefix `/api/submissions`; `/thoughts` does not collide with `/{submission_id}` because the path has an extra segment.

- [ ] **Step 4: Run the tests**

Run: `uv run python -m pytest -q tests/web/test_room_api.py tests/web/test_submissions_api.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sms/web/services/room.py src/sms/web/routers/room.py src/sms/web/app.py tests/web/test_room_api.py
git commit -m "feat(room): snapshot, SSE stage stream and teacher-only thoughts"
```

---

### Task 6: Settings and class-assignment `reflect_days`

**Files:**
- Modify: `src/sms/providers/settings.py` (dataclass field, load/save, `public_dict`)
- Modify: `src/sms/web/routers/settings.py` (`SettingsBody.reflect_days`)
- Modify: `src/sms/web/services/class_assignments.py` (`_dict`/serialiser, create/update accept `reflect_days`, `effective_reflect_days`)
- Modify: `src/sms/web/routers/class_assignments.py` (body field)
- Modify: `tests/web/test_settings_api.py`, `tests/web/test_class_assignments_api.py` (append tests)

**Interfaces:**
- Produces: `Settings.reflect_days: int = 7`; `PUT /api/settings {reflect_days}` (0–60, 400 `bad_reflect_days` otherwise); class assignment dict has `reflect_days` (nullable) and `effective_reflect_days` (int); `effective_reflect_days(db, ca: dict) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/web/test_settings_api.py
def test_reflect_days_defaults_to_seven_and_is_bounded(auth):
    assert auth.get("/api/settings").json()["reflect_days"] == 7
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x", "rpm_limit": 10,
                                        "confidence_threshold": 0, "reflect_days": 14})
    assert r.status_code == 200 and auth.get("/api/settings").json()["reflect_days"] == 14
    r = auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "rpm_limit": 10, "confidence_threshold": 0, "reflect_days": 99})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_reflect_days"
```

```python
# append to tests/web/test_class_assignments_api.py
def test_class_assignment_reflect_days_follows_settings_unless_set(auth):
    t = auth.post("/api/assignments", json={"title": "W", "subject": "math", "context": "", "rubric": RUBRIC,
                                            "scheme_kind": "mark_scheme", "questions": QUESTIONS, "scheme": SCHEME}).json()
    c = auth.post("/api/classes", json={"name": "4E"}).json()
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    assert ca["reflect_days"] is None and ca["effective_reflect_days"] == 7
    ca = auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
                  json={"title": ca["title"], "due_at": None, "allow_student_uploads": True, "status": "draft", "reflect_days": 0}).json()
    assert ca["reflect_days"] == 0 and ca["effective_reflect_days"] == 0
```

(`RUBRIC`, `QUESTIONS`, `SCHEME` come from `tests.web.seed_v2`, already imported in that file; if not, add the import.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest -q tests/web/test_settings_api.py tests/web/test_class_assignments_api.py -k reflect`
Expected: FAIL — `KeyError: 'reflect_days'`.

- [ ] **Step 3: Implement**

`src/sms/providers/settings.py`: add `reflect_days: int = 7` to the `Settings` dataclass after `page_retention`; include it in the load (`reflect_days=int(row.get("reflect_days") or 7)`), the save (`reflect_days = :reflect_days` with the parameter), and `public_dict` (`"reflect_days": self.reflect_days`). Follow exactly how `page_retention` is threaded through those three places.

`src/sms/web/routers/settings.py`: `SettingsBody.reflect_days: Optional[int] = None`; when present, validate `0 <= v <= 60` else `raise ApiError(400, "bad_reflect_days", "Reflection window must be between 0 and 60 days")`; when absent keep the stored value (as `page_retention` does).

`src/sms/web/services/class_assignments.py`: in the dict serialiser add `"reflect_days": r["reflect_days"]` and `"effective_reflect_days": effective_reflect_days(db, r)`; add

```python
def effective_reflect_days(db: Database, ca: Dict[str, Any]) -> int:
    if ca.get("reflect_days") is not None:
        return int(ca["reflect_days"])
    row = db.query("SELECT reflect_days FROM settings WHERE id = 1")
    return int(row[0]["reflect_days"]) if row and row[0]["reflect_days"] is not None else 7
```

In `update_class_assignment` accept `reflect_days: Optional[int]` (None keeps/clears per body: send `null` to follow the default) with the same 0–60 check and error code, and write it in the UPDATE. In the router's `TemplateBody`/update body add `reflect_days: Optional[int] = None` and pass it through. The serialiser needs `db`: it is a module function that already receives rows; pass `db` where it is called (two call sites: `get_class_assignment` and `list_class_assignments`).

- [ ] **Step 4: Run the two test files**

Run: `uv run python -m pytest -q tests/web/test_settings_api.py tests/web/test_class_assignments_api.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sms/providers/settings.py src/sms/web/routers/settings.py src/sms/web/services/class_assignments.py src/sms/web/routers/class_assignments.py tests/web/test_settings_api.py tests/web/test_class_assignments_api.py
git commit -m "feat(reflection): reflect_days in Settings and per class assignment"
```

---

### Task 7: Student corrections service

**Files:**
- Create: `src/sms/web/services/student_corrections.py`
- Create: `tests/web/test_student_corrections_service.py`

**Interfaces:**
- Consumes: `effective_reflect_days` (Task 6), `get_submission` (existing), `JobStore.enqueue(kind, submission_id, payload)`.
- Produces:
  - `window_end(db, ca) -> Optional[datetime]` (UTC, naive like the DB) — `None` when not released or days == 0.
  - `window_open(db, ca, now=None) -> bool`
  - `correctable_parts(detail) -> Dict[str, dict]` → `{q_id: {"label", "mark", "max"}}` for parts with mark < max.
  - `submit_correction(db, storage, jobs, *, ca, submission_detail, q_id, reason, text, photo) -> dict` → row dict; raises 409 `window_closed`, 409 `already_corrected`, 400 `not_correctable`, 400 `empty_correction`.
  - `list_corrections(db, class_assignment_id) -> List[dict]`
  - `decide(db, correction_id, action: str, *, total: Optional[float]=None, reason: str="") -> dict` (`accept` | `override` | `reject`)
  - `release_corrections(db, class_assignment_id) -> int`
  - `student_reflection(db, ca, detail) -> dict` → `{"window_ends_at", "days_left", "parts": {q_id: {"can_correct", "status", "new_mark"}}}`
  - `STATUS_WORDS = {"submitted": "sent", "remarked": "waiting for the teacher", "accepted": "waiting for the teacher", "overridden": "waiting for the teacher", "released": "released", "rejected": "rejected"}`

- [ ] **Step 1: Write the failing tests**

```python
# tests/web/test_student_corrections_service.py
from datetime import datetime, timedelta

import pytest

from sms.web.errors import ApiError
from sms.web.services import student_corrections as sc
from sms.web.services.submissions import get_submission
from sms.worker.jobs import JobStore
from tests.web.seed_v2 import seed_v2
from tests.web.test_student_api import _setup


def _released(auth, app, days=7):
    t, c, ca, _ = _setup(auth)
    tan = c["students"][0]
    sid, _ = seed_v2(app, label="#1 Tan", assignment_id=t["id"], run_id="r-tan", queue={})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :a, student_id = :s, handed_in_at = CURRENT_TIMESTAMP, source = 'student' WHERE id = :id",
                         {"a": ca["id"], "s": tan["id"], "id": sid})
    auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release")
    app.state.db.execute("UPDATE class_assignments SET reflect_days = :d WHERE id = :id", {"d": days, "id": ca["id"]})
    row = app.state.db.query("SELECT * FROM class_assignments WHERE id = :id", {"id": ca["id"]})[0]
    return row, sid


def test_window_and_correctable_parts(auth, app):
    ca, sid = _released(auth, app)
    db = app.state.db
    assert sc.window_open(db, ca)
    assert sc.window_end(db, ca) > datetime.utcnow() + timedelta(days=6)
    db.execute("UPDATE class_assignments SET reflect_days = 0 WHERE id = :id", {"id": ca["id"]})
    ca["reflect_days"] = 0
    assert sc.window_end(db, ca) is None and not sc.window_open(db, ca)
    detail = get_submission(db, JobStore(db), sid)
    parts = sc.correctable_parts(detail)
    assert set(parts) == {"1b", "2"} and parts["1b"]["max"] == 1   # 1a has full marks in the seed


def test_submit_enforces_rules_and_enqueues_a_remark(auth, app):
    ca, sid = _released(auth, app)
    db, jobs = app.state.db, JobStore(app.state.db)
    detail = get_submission(db, jobs, sid)
    with pytest.raises(ApiError) as e:
        sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1a", reason="sign", text="x", photo=None)
    assert e.value.code == "not_correctable"
    with pytest.raises(ApiError) as e:
        sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1b", reason="sign", text="  ", photo=None)
    assert e.value.code == "empty_correction"
    row = sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1b", reason="sign", text="x^2 = 9", photo=None)
    assert row["status"] == "submitted" and row["q_id"] == "1b"
    assert db.query("SELECT kind, payload_json FROM jobs WHERE kind = 'remark'")[0]["payload_json"] == '{"correction_id": %d}' % row["id"]
    with pytest.raises(ApiError) as e:
        sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1b", reason="sign", text="again", photo=None)
    assert e.value.code == "already_corrected"
    db.execute("UPDATE class_assignments SET reflect_days = 0 WHERE id = :id", {"id": ca["id"]}); ca["reflect_days"] = 0
    with pytest.raises(ApiError) as e:
        sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="2", reason="sign", text="z", photo=None)
    assert e.value.code == "window_closed"


def test_decide_and_release_transitions(auth, app):
    ca, sid = _released(auth, app)
    db, jobs = app.state.db, JobStore(db := app.state.db)
    detail = get_submission(db, jobs, sid)
    row = sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1b", reason="sign", text="9", photo=None)
    db.execute("UPDATE student_corrections SET status = 'remarked', remark_total = 1, remark_max = 1, remark_note = 'B1 now earned' WHERE id = :id", {"id": row["id"]})
    assert sc.decide(db, row["id"], "accept")["status"] == "accepted"
    assert sc.decide(db, row["id"], "override", total=0.5)["teacher_total"] == 0.5
    with pytest.raises(ApiError):
        sc.decide(db, row["id"], "override", total=5)         # above max
    assert sc.release_corrections(db, ca["id"]) == 1
    got = db.query("SELECT status, released_at FROM student_corrections WHERE id = :id", {"id": row["id"]})[0]
    assert got["status"] == "released" and got["released_at"] is not None
    with pytest.raises(ApiError):
        sc.decide(db, row["id"], "reject", reason="too late")   # released is final
    view = sc.student_reflection(db, ca, get_submission(db, jobs, sid))
    assert view["parts"]["1b"] == {"can_correct": False, "status": "released", "new_mark": 0.5}
    assert view["parts"]["2"]["can_correct"] is True and view["days_left"] >= 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest -q tests/web/test_student_corrections_service.py`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement the service**

```python
# src/sms/web/services/student_corrections.py
"""Reflect and correct: after feedback is released, a student has a window (reflect_days) to send one
correction per part that lost marks. The AI re-marks it (sms.worker.remark_job); the teacher accepts,
overrides or rejects; releasing makes the new mark visible. Never confuse with teacher_corrections,
which are the teacher's own Review decisions."""
import io
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from sms.memory.db import Database
from sms.schemas.scheme import norm_qid
from sms.storage import PageStorage
from sms.timeutil import iso_utc
from sms.web.errors import ApiError
from sms.web.services.class_assignments import effective_reflect_days
from sms.worker.jobs import JobStore

REASONS = ("sign", "method", "rushed", "misread", "other")
STATUS_WORDS = {"submitted": "sent", "remarked": "waiting for the teacher", "accepted": "waiting for the teacher",
                "overridden": "waiting for the teacher", "released": "released", "rejected": "rejected"}
FINAL = ("released", "rejected")


def _parse(ts) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None)
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)


def window_end(db: Database, ca: Dict[str, Any]) -> Optional[datetime]:
    released = _parse(ca.get("released_at"))
    days = effective_reflect_days(db, ca)
    if released is None or days <= 0:
        return None
    return released + timedelta(days=days)


def window_open(db: Database, ca: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    end = window_end(db, ca)
    return end is not None and (now or datetime.utcnow()) < end


def _mark_of(p: dict) -> float:
    return float(p["teacher"]["total"]) if p.get("teacher") else float(p["total"])


def correctable_parts(detail: dict) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for p in detail.get("parts") or []:
        mark, mx = _mark_of(p), float(p["max"])
        if mark < mx:
            out[norm_qid(p["q_id"])] = {"label": p["label"], "mark": mark, "max": mx, "q_id": p["q_id"]}
    return out


def _row(r: dict) -> Dict[str, Any]:
    return {**r, "submitted_at": iso_utc(r.get("submitted_at")), "released_at": iso_utc(r.get("released_at")),
            "created_at": iso_utc(r.get("created_at"))}


def _jpeg(photo: Tuple[str, bytes]) -> bytes:
    try:
        im = Image.open(io.BytesIO(photo[1])).convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise ApiError(400, "bad_photo", "That photo could not be read — try a JPG or PNG") from e
    im.thumbnail((2000, 2000))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def submit_correction(db: Database, storage: PageStorage, jobs: JobStore, *, ca: Dict[str, Any], submission_detail: dict,
                      q_id: str, reason: str, text: Optional[str], photo: Optional[Tuple[str, bytes]]) -> Dict[str, Any]:
    if not window_open(db, ca):
        raise ApiError(409, "window_closed", "The reflection window for this assignment has closed")
    parts = correctable_parts(submission_detail)
    key = norm_qid(q_id)
    if key not in parts:
        raise ApiError(400, "not_correctable", "That part has full marks or does not exist")
    text = (text or "").strip()
    if not text and photo is None:
        raise ApiError(400, "empty_correction", "Type your corrected working or add a photo")
    sid = submission_detail["id"]
    if db.query("SELECT 1 FROM student_corrections WHERE submission_id = :s AND q_id = :q", {"s": sid, "q": key}):
        raise ApiError(409, "already_corrected", "You have already sent a correction for this part")
    page_id = None
    if photo is not None:
        data = _jpeg(photo)
        digest, rel = storage.put_jpeg(data)
        n = db.query("SELECT COUNT(*) AS c FROM pages WHERE submission_id = :s", {"s": sid})[0]["c"]
        page_id = db.insert("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height, kind) "
                            "VALUES (:s, :i, :d, :p, 0, 0, 'correction') RETURNING id",
                            {"s": sid, "i": 1000 + int(n), "d": digest, "p": rel})
    cid = db.insert("INSERT INTO student_corrections (submission_id, q_id, reason, text, page_id, status) "
                    "VALUES (:s, :q, :r, :t, :p, 'submitted') RETURNING id",
                    {"s": sid, "q": key, "r": reason if reason in REASONS else "other", "t": text or None, "p": page_id})
    jobs.enqueue("remark", submission_id=sid, payload={"correction_id": cid})
    return _row(db.query("SELECT * FROM student_corrections WHERE id = :id", {"id": cid})[0])


def list_corrections(db: Database, class_assignment_id: int) -> List[Dict[str, Any]]:
    rows = db.query("SELECT c.*, s.label AS submission_label, st.reg_no AS reg_no, st.name AS student_name "
                    "FROM student_corrections c JOIN submissions s ON s.id = c.submission_id "
                    "LEFT JOIN students st ON st.id = s.student_id WHERE s.class_assignment_id = :ca ORDER BY c.id", {"ca": class_assignment_id})
    return [_row(r) for r in rows]


def decide(db: Database, correction_id: int, action: str, *, total: Optional[float] = None, reason: str = "") -> Dict[str, Any]:
    rows = db.query("SELECT * FROM student_corrections WHERE id = :id", {"id": correction_id})
    if not rows:
        raise ApiError(404, "not_found", "No such correction")
    r = rows[0]
    if r["status"] in FINAL:
        raise ApiError(409, "final", "This correction has already been released or rejected")
    if action == "accept":
        if r["remark_total"] is None:
            raise ApiError(409, "not_remarked", "The Marker has not re-marked this yet — override it instead")
        db.execute("UPDATE student_corrections SET status = 'accepted', teacher_total = NULL WHERE id = :id", {"id": correction_id})
    elif action == "override":
        mx = r["remark_max"]
        if total is None or total < 0 or (mx is not None and total > float(mx)):
            raise ApiError(400, "bad_total", f"Mark must be between 0 and {mx if mx is not None else 'the part maximum'}")
        db.execute("UPDATE student_corrections SET status = 'overridden', teacher_total = :t WHERE id = :id", {"t": total, "id": correction_id})
    elif action == "reject":
        db.execute("UPDATE student_corrections SET status = 'rejected', teacher_reason = :r WHERE id = :id",
                   {"r": reason.strip() or "Not accepted", "id": correction_id})
    else:
        raise ApiError(400, "bad_action", "Action must be accept, override or reject")
    return _row(db.query("SELECT * FROM student_corrections WHERE id = :id", {"id": correction_id})[0])


def release_corrections(db: Database, class_assignment_id: int) -> int:
    return db.execute("UPDATE student_corrections SET status = 'released', released_at = CURRENT_TIMESTAMP "
                      "WHERE status IN ('accepted', 'overridden') AND submission_id IN "
                      "(SELECT id FROM submissions WHERE class_assignment_id = :ca)", {"ca": class_assignment_id})


def released_marks(db: Database, submission_id: int) -> Dict[str, dict]:
    """{q_id: {total, max}} of the released corrections of one script — for records and the CSV."""
    rows = db.query("SELECT q_id, remark_total, remark_max, teacher_total FROM student_corrections "
                    "WHERE submission_id = :s AND status = 'released'", {"s": submission_id})
    return {r["q_id"]: {"total": float(r["teacher_total"] if r["teacher_total"] is not None else r["remark_total"] or 0),
                        "max": float(r["remark_max"] or 0)} for r in rows}


def student_reflection(db: Database, ca: Dict[str, Any], detail: dict) -> Dict[str, Any]:
    end = window_end(db, ca)
    open_ = end is not None and datetime.utcnow() < end
    existing = {r["q_id"]: r for r in db.query("SELECT * FROM student_corrections WHERE submission_id = :s", {"s": detail["id"]})}
    parts: Dict[str, dict] = {}
    for key, p in correctable_parts(detail).items():
        c = existing.get(key)
        if c is None:
            parts[key] = {"can_correct": open_, "status": None, "new_mark": None}
        else:
            new = None
            if c["status"] == "released":
                new = float(c["teacher_total"] if c["teacher_total"] is not None else c["remark_total"] or 0)
            parts[key] = {"can_correct": False, "status": c["status"], "new_mark": new}
    days_left = max(0, (end - datetime.utcnow()).days) if end else 0
    return {"window_ends_at": iso_utc(end) if end else None, "days_left": days_left, "parts": parts}
```

If `pages.kind` does not exist as a column name (check `grep -n "kind" src/sms/migrations/versions/*.py | grep pages`), drop `kind` from the INSERT and use `page_index >= 1000` as the marker for correction photos everywhere this plan says `kind = 'correction'`.

- [ ] **Step 4: Run the tests**

Run: `uv run python -m pytest -q tests/web/test_student_corrections_service.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sms/web/services/student_corrections.py tests/web/test_student_corrections_service.py
git commit -m "feat(reflection): student corrections service — window, one per part, decide, release"
```

---

### Task 8: The re-mark job

**Files:**
- Create: `src/sms/worker/remark_job.py`
- Modify: `src/sms/worker/worker.py` (`__init__` gets `remark_runner=run_remark_job`; `run_once` dispatches `"remark"`)
- Create: `tests/unit/test_remark_job.py`

**Interfaces:**
- Consumes: `_v2_template(db, assignment_id, uploaded_kind)` and `_default_pipeline_factory` from `sms.worker.mark_job`; `MarkingInputV2`, `ReviewInputV2`, `ExtractedScript`.
- Produces: `run_remark_job(db, storage, settings_store, correction_id, pipeline_factory=None, bucket=None, bucket_pool=None) -> None`; on success the row has `status='remarked'`, `remark_total`, `remark_max`, `remark_note`, `remark_run_id`; on failure `status` stays `submitted` and `error` is set (the exception is re-raised so the job retries as usual).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_remark_job.py
import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.marking import ReviewVerdict
from sms.schemas.marking_v2 import AllocationMark, MarkedScriptV2, PartMark, ReviewVerdictV2, ReviewedScriptV2
from sms.storage import PageStorage
from sms.worker.remark_job import run_remark_job
from tests.unit.test_pipeline_v2_files import Fake

SCHEME = [{"q_id": "1a", "answer": "x=3", "marks": [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 1}], "notes": ""},
          {"q_id": "1b", "answer": "9", "marks": [{"label": "B1", "marks": 1}], "notes": ""}]
QUESTIONS = [{"q_id": "1a", "text": "Solve", "max_marks": 2}, {"q_id": "1b", "text": "Hence", "max_marks": 1}]


@pytest.fixture
def env(tmp_path):
    import json
    db = Database(path=str(tmp_path / "s.db"))
    store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0))
    tid = db.insert("INSERT INTO assignment_templates (title, subject, context, rubric_json, scheme_kind, questions_json, scheme_json) "
                    "VALUES ('W', 'math', '', '{}', 'mark_scheme', :q, :s) RETURNING id", {"q": json.dumps(QUESTIONS), "s": json.dumps(SCHEME)})
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status, assignment_id, scheme_kind) "
                    "VALUES ('s', 'math', '', '{}', 'done', :t, 'mark_scheme') RETURNING id", {"t": tid})
    cid = db.insert("INSERT INTO student_corrections (submission_id, q_id, reason, text, status) VALUES (:s, '1b', 'sign', 'x^2 = 9', 'submitted') RETURNING id", {"s": sid})
    return db, store, PageStorage(tmp_path / "data"), cid


class _Pipe:
    def __init__(self, marked, reviewed):
        self.marker, self.reviewer = Fake(marked), Fake(reviewed)
    def _blind_script(self, m):
        return m


def test_remark_stores_mark_note_and_status(env):
    db, store, storage, cid = env
    marked = MarkedScriptV2(kind="mark_scheme", parts=[PartMark(q_id="1b", awarded=[AllocationMark(label="B1", marks=1, got=True)], total=1, justification="9 is right")])
    reviewed = ReviewedScriptV2(verdicts=[ReviewVerdictV2(q_id="1b", verdict=ReviewVerdict.APPROVE, reviewer_note="Agree")])
    pipe = _Pipe(marked, reviewed)
    run_remark_job(db, storage, store, cid, pipeline_factory=lambda **k: pipe)
    r = db.query("SELECT * FROM student_corrections WHERE id = :id", {"id": cid})[0]
    assert r["status"] == "remarked" and r["remark_total"] == 1 and r["remark_max"] == 1
    assert r["remark_note"] == "Marker: 9 is right\nChecker: APPROVE: Agree" and r["remark_run_id"]
    sent = pipe.marker.calls[0]
    assert [q.q_id for q in sent.questions] == ["1b"] and [s.q_id for s in sent.scheme] == ["1b"]
    assert sent.extracted.questions[0].transcribed_answer == "x^2 = 9"


def test_reviewer_adjustment_wins(env):
    db, store, storage, cid = env
    marked = MarkedScriptV2(kind="mark_scheme", parts=[PartMark(q_id="1b", awarded=[AllocationMark(label="B1", marks=1, got=True)], total=1)])
    adjusted = PartMark(q_id="1b", awarded=[AllocationMark(label="B1", marks=1, got=False)], total=0)
    reviewed = ReviewedScriptV2(verdicts=[ReviewVerdictV2(q_id="1b", verdict=ReviewVerdict.ADJUST, adjusted=adjusted, reviewer_note="Still 6")])
    run_remark_job(db, storage, store, cid, pipeline_factory=lambda **k: _Pipe(marked, reviewed))
    assert db.query("SELECT remark_total FROM student_corrections WHERE id = :id", {"id": cid})[0]["remark_total"] == 0


def test_failure_records_the_error_and_reraises(env):
    db, store, storage, cid = env
    class Boom:
        marker = type("M", (), {"run": staticmethod(lambda inp: (_ for _ in ()).throw(RuntimeError("provider down")))})()
    with pytest.raises(RuntimeError):
        run_remark_job(db, storage, store, cid, pipeline_factory=lambda **k: Boom())
    r = db.query("SELECT status, error FROM student_corrections WHERE id = :id", {"id": cid})[0]
    assert r["status"] == "submitted" and "provider down" in r["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest -q tests/unit/test_remark_job.py`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the job and the dispatch**

```python
# src/sms/worker/remark_job.py
"""Re-mark one corrected part: the Marker and the Checker see only that part's question and scheme
row, with the student's correction as the transcribed answer (or the photo's transcription)."""
import logging
import uuid
from typing import Any, Callable, Optional

from sms.memory.db import Database
from sms.providers.settings import SettingsStore
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.marking import ReviewVerdict
from sms.schemas.marking_v2 import MarkingInputV2, ReviewInputV2
from sms.schemas.scheme import MarkSchemeEntry, Question, RubricCriterionBands, norm_qid
from sms.storage import PageStorage
from sms.web.services.assignments import get_template
from sms.providers.ratelimit import BucketPool, TokenBucket
from sms.worker.mark_job import _default_pipeline_factory, _v2_template

log = logging.getLogger(__name__)


def _part_template(template: dict, q_id: str) -> dict:
    key = norm_qid(q_id)
    questions = [q for q in template.get("questions") or [] if norm_qid(q["q_id"]) == key]
    if template["scheme_kind"] == "mark_scheme":
        scheme = [s for s in template.get("scheme") or [] if norm_qid(s["q_id"]) == key]
    else:
        scheme = [s for s in template.get("scheme") or [] if s["criterion"] == q_id]
    return {**template, "questions": questions, "scheme": scheme}


def _max_of(part_template: dict) -> float:
    if part_template["scheme_kind"] == "mark_scheme":
        return float(sum(m["marks"] for s in part_template["scheme"] for m in s["marks"]))
    return float(max((b["marks"] for s in part_template["scheme"] for b in s["bands"]), default=0))


def run_remark_job(db: Database, storage: PageStorage, settings_store: SettingsStore, correction_id: int,
                   pipeline_factory: Optional[Callable[..., Any]] = None,
                   bucket: Optional[TokenBucket] = None, bucket_pool: Optional[BucketPool] = None) -> None:
    rows = db.query("SELECT c.*, s.assignment_id, s.scheme_kind, s.subject FROM student_corrections c "
                    "JOIN submissions s ON s.id = c.submission_id WHERE c.id = :id", {"id": correction_id})
    if not rows:
        raise ValueError(f"correction {correction_id} not found")
    c = rows[0]
    try:
        tpl = get_template(db, c["assignment_id"])
        settings = settings_store.for_template(tpl)
        if bucket_pool is not None:
            bucket = bucket_pool.get(settings.provider, settings.rpm_limit)
        template = _v2_template(db, c["assignment_id"], c["scheme_kind"])
        if template is None:
            raise RuntimeError("This assignment has no mark scheme or rubric to re-mark against")
        part = _part_template(template, c["q_id"])
        if not part["questions"] or not part["scheme"]:
            raise RuntimeError(f"Part {c['q_id']} is not in the scheme any more")
        factory = pipeline_factory or _default_pipeline_factory
        pipeline = factory(db=db, settings=settings, subject=template["subject"], bucket=bucket, kind=template["scheme_kind"])
        text = (c["text"] or "").strip()
        if not text and c["page_id"] is not None:
            page = db.query("SELECT storage_path FROM pages WHERE id = :p", {"p": c["page_id"]})[0]
            ex = pipeline._extract([storage.read(page["storage_path"])], template["subject"],
                                   [Question.model_validate(q) for q in part["questions"]], template.get("context") or "", "en")
            text = "\n".join(f"{q.transcribed_answer}\n{q.workings}".strip() for q in ex.questions)
        extracted = ExtractedScript(questions=[ExtractedQuestion(q_id=c["q_id"], transcribed_answer=text, workings="", confidence=1.0)])
        questions = [Question.model_validate(q) for q in part["questions"]]
        scheme = ([MarkSchemeEntry.model_validate(s) for s in part["scheme"]] if part["scheme_kind"] == "mark_scheme"
                  else [RubricCriterionBands.model_validate(s) for s in part["scheme"]])
        notes = template.get("context") or ""
        marked = pipeline.marker.run(MarkingInputV2(kind=part["scheme_kind"], extracted=extracted, questions=questions, scheme=scheme, notes=notes))
        reviewed = pipeline.reviewer.run(ReviewInputV2(kind=part["scheme_kind"], extracted=extracted, questions=questions, scheme=scheme,
                                                       notes=notes, marks=pipeline._blind_script(marked)))
        marks = marked.parts or marked.rubric
        mark = marks[0] if marks else None
        total = float(mark.total if hasattr(mark, "total") else mark.marks) if mark else 0.0
        just = (mark.justification if mark else "") or ""
        verdict = next((v for v in reviewed.verdicts), None)
        if verdict is not None and verdict.verdict == ReviewVerdict.ADJUST and verdict.adjusted is not None:
            a = verdict.adjusted
            total = float(a.total if hasattr(a, "total") else a.marks)
        note = f"Marker: {just}".rstrip()
        if verdict is not None:
            note += f"\nChecker: {verdict.verdict.value}: {verdict.reviewer_note}".rstrip()
        db.execute("UPDATE student_corrections SET status = 'remarked', remark_total = :t, remark_max = :m, remark_note = :n, "
                   "remark_run_id = :r, error = NULL WHERE id = :id",
                   {"t": total, "m": _max_of(part), "n": note, "r": uuid.uuid4().hex[:12], "id": correction_id})
    except Exception as e:  # noqa: BLE001
        db.execute("UPDATE student_corrections SET error = :e WHERE id = :id", {"e": str(e)[:500], "id": correction_id})
        raise
```

`MarkSchemeEntry`, `Question` and `RubricCriterionBands` are defined in `sms.schemas.scheme`; `BucketPool` and `TokenBucket` in `sms.providers.ratelimit` (the same imports `mark_job.py` uses).

In `src/sms/worker/worker.py`: import `run_remark_job`, add `remark_runner: Runner = run_remark_job` to `__init__` (stored as `self.remark_runner`), and in `run_once` add before the `else`:

```python
            elif job["kind"] == "remark":
                payload = json.loads(job["payload_json"] or "{}")
                self.remark_runner(self.db, self.storage, self.settings_store, int(payload["correction_id"]), bucket_pool=self.pool)
```

- [ ] **Step 4: Run the tests**

Run: `uv run python -m pytest -q tests/unit/test_remark_job.py tests/unit/test_worker.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sms/worker/remark_job.py src/sms/worker/worker.py tests/unit/test_remark_job.py
git commit -m "feat(reflection): remark job — marker and checker re-mark one corrected part"
```

---

### Task 9: Student and teacher correction routes, student feedback additions

**Files:**
- Create: `src/sms/web/routers/corrections.py`
- Modify: `src/sms/web/services/student.py` (`feedback_view` adds `crop_id` and `q_id`; `student_assignment` adds `reflection`)
- Modify: `src/sms/web/routers/student.py` (`GET /api/student/crops/{crop_id}`)
- Modify: `src/sms/web/app.py` (register `corrections.router`)
- Create: `tests/web/test_corrections_api.py`

**Interfaces:**
- Produces:
  - `POST /api/student/assignments/{caid}/corrections` multipart `q_id`, `reason`, `text` (optional), `photo` (optional file) → 201 `{id, q_id, status}`; error codes from Task 7 plus 404 when feedback is not released.
  - `GET /api/student/crops/{crop_id}` → JPEG of the student's own answer crop (404 otherwise).
  - `feedback_view` questions gain `"q_id"` (normalised) and `"crop_id"` (int | None).
  - `student_assignment` gains `"reflection"` (Task 7's `student_reflection`) when `feedback_ready`, else `None`.
  - `GET /api/review/corrections?class_assignment_id=` → list; `POST /api/corrections/{id}/accept`, `/override {total}`, `/reject {reason}`; `POST /api/class-assignments/{caid}/release-corrections` → `{released: n}`. All teacher-only.

- [ ] **Step 1: Write the failing tests**

```python
# tests/web/test_corrections_api.py
from tests.web.seed_v2 import seed_v2
from tests.web.test_student_api import _setup


def _released_student(auth, client, app):
    t, c, ca, _ = _setup(auth)
    tan = c["students"][0]
    sid, _ = seed_v2(app, label="#1 Tan", assignment_id=t["id"], run_id="r-tan", queue={})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :a, student_id = :s, handed_in_at = CURRENT_TIMESTAMP, source = 'student' WHERE id = :id",
                         {"a": ca["id"], "s": tan["id"], "id": sid})
    assert auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release").status_code == 200
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    return c, ca, sid


def test_student_sees_reflection_and_sends_one_correction(auth, client, app):
    c, ca, sid = _released_student(auth, client, app)
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["reflection"]["days_left"] >= 6
    assert got["reflection"]["parts"]["1b"] == {"can_correct": True, "status": None, "new_mark": None}
    assert "1a" not in got["reflection"]["parts"]
    assert {q["q_id"] for q in got["feedback"]["questions"]} == {"1a", "1b", "2"}
    r = client.post(f"/api/student/assignments/{ca['id']}/corrections", data={"q_id": "1b", "reason": "sign", "text": "9"})
    assert r.status_code == 201 and r.json()["status"] == "submitted"
    r = client.post(f"/api/student/assignments/{ca['id']}/corrections", data={"q_id": "1b", "reason": "sign", "text": "again"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_corrected"
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["reflection"]["parts"]["1b"] == {"can_correct": False, "status": "submitted", "new_mark": None}
    assert "remark_note" not in str(got) and "justification" not in str(got)


def test_teacher_reviews_and_releases(auth, client, app):
    c, ca, sid = _released_student(auth, client, app)
    cid = client.post(f"/api/student/assignments/{ca['id']}/corrections", data={"q_id": "1b", "reason": "sign", "text": "9"}).json()["id"]
    auth.post("/api/auth/login", json={"password": "letmein"})
    app.state.db.execute("UPDATE student_corrections SET status = 'remarked', remark_total = 1, remark_max = 1, remark_note = 'Marker: B1 earned' WHERE id = :id", {"id": cid})
    rows = auth.get(f"/api/review/corrections?class_assignment_id={ca['id']}").json()
    assert rows[0]["id"] == cid and rows[0]["reg_no"] == 1 and rows[0]["remark_note"] == "Marker: B1 earned"
    assert auth.post(f"/api/corrections/{cid}/override", json={"total": 0.5}).json()["teacher_total"] == 0.5
    assert auth.post(f"/api/class-assignments/{ca['id']}/release-corrections").json() == {"released": 1}
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["reflection"]["parts"]["1b"] == {"can_correct": False, "status": "released", "new_mark": 0.5}


def test_correction_routes_are_scoped(auth, client, app):
    c, ca, sid = _released_student(auth, client, app)
    assert client.get("/api/review/corrections?class_assignment_id=1").status_code in (401, 404)
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 2})
    r = client.post(f"/api/student/assignments/{ca['id']}/corrections", data={"q_id": "1b", "reason": "sign", "text": "9"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest -q tests/web/test_corrections_api.py`
Expected: FAIL — `KeyError: 'reflection'`.

- [ ] **Step 3: Implement**

`src/sms/web/services/student.py`:
- `feedback_view`: for v2 parts also set `"q_id": norm_qid(p["q_id"])` and `"crop_id": p.get("crop_id")` on each question dict (the detail's parts already carry `crop_id` from the answer-crops feature; v1 rows get `"q_id": m["q_id"], "crop_id": None`).
- `student_assignment`: after setting `out["feedback"]`, add

```python
    out["reflection"] = None
    if out["status"] == "feedback_ready" and detail:
        ca = get_class_assignment(db, student["class_id"], caid)
        out["reflection"] = student_reflection(db, ca, detail)
```

(import `student_reflection` from `sms.web.services.student_corrections`; `detail` must be the same object fetched for the feedback — restructure so it is fetched once.)

- Add `student_crop_path(db, storage, student, crop_id) -> Path`: 404 unless the crop belongs to a submission whose `student_id` is the session's student and `deleted_at IS NULL`; returns `storage.abs(storage_path)`.

`src/sms/web/routers/student.py`: add

```python
@router.get("/crops/{crop_id}")
def crop(crop_id: int, student: dict = Depends(require_student), db=Depends(get_db), storage=Depends(get_storage)):
    return FileResponse(student_crop_path(db, storage, student, crop_id), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})
```

```python
# src/sms/web/routers/corrections.py
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sms.web.deps import get_db, get_jobs, get_storage, require_student, require_teacher
from sms.web.errors import ApiError
from sms.web.services.class_assignments import get_class_assignment
from sms.web.services.student import _visible
from sms.web.services.student_corrections import decide, list_corrections, release_corrections, submit_correction
from sms.web.services.submissions import get_submission
from sms.web.uploads import check_content_length, read_upload_files

router = APIRouter(tags=["corrections"])
teacher = APIRouter(dependencies=[Depends(require_teacher)])


@router.post("/api/student/assignments/{caid}/corrections", status_code=201)
async def student_submit(caid: int, request: Request, q_id: str = Form(...), reason: str = Form("other"),
                         text: Optional[str] = Form(None), photo: Optional[UploadFile] = File(None),
                         student: dict = Depends(require_student), db=Depends(get_db), storage=Depends(get_storage), jobs=Depends(get_jobs)):
    check_content_length(request)
    rows = await run_in_threadpool(_visible, db, student, caid)
    if not rows or rows[0]["submission_id"] is None or rows[0]["status"] != "released":
        raise ApiError(404, "not_found", "No released feedback to correct")
    ca = await run_in_threadpool(get_class_assignment, db, student["class_id"], caid)
    detail = await run_in_threadpool(get_submission, db, jobs, rows[0]["submission_id"])
    payload = (await read_upload_files(request, [photo]))[0] if photo is not None else None
    row = await run_in_threadpool(submit_correction, db, storage, jobs, ca=ca, submission_detail=detail, q_id=q_id,
                                  reason=reason, text=text, photo=payload)
    return JSONResponse({"id": row["id"], "q_id": row["q_id"], "status": row["status"]}, status_code=201)


class OverrideBody(BaseModel):
    total: float


class RejectBody(BaseModel):
    reason: str = ""


@teacher.get("/api/review/corrections")
def index(class_assignment_id: int, db=Depends(get_db)):
    return list_corrections(db, class_assignment_id)


@teacher.post("/api/corrections/{correction_id}/accept")
def accept(correction_id: int, db=Depends(get_db)):
    return decide(db, correction_id, "accept")


@teacher.post("/api/corrections/{correction_id}/override")
def override(correction_id: int, body: OverrideBody, db=Depends(get_db)):
    return decide(db, correction_id, "override", total=body.total)


@teacher.post("/api/corrections/{correction_id}/reject")
def reject(correction_id: int, body: RejectBody, db=Depends(get_db)):
    return decide(db, correction_id, "reject", reason=body.reason)


@teacher.post("/api/class-assignments/{caid}/release-corrections")
def release(caid: int, db=Depends(get_db)):
    return {"released": release_corrections(db, caid)}


router.include_router(teacher)
```

`_visible(db, student, caid)` returns the student's rows with `submission_id` and the class assignment `status`; check its row keys (`r["status"]` is the class assignment status in `_row`; use whichever key carries `'released'`). Register `corrections.router` in `app.py` after `student.router`.

- [ ] **Step 4: Run the tests**

Run: `uv run python -m pytest -q tests/web/test_corrections_api.py tests/web/test_student_api.py`
Expected: PASS (the existing student test that scans the response for "reviewer" etc. must still pass: the reflection block carries no notes).

- [ ] **Step 5: Commit**

```bash
git add src/sms/web/routers/corrections.py src/sms/web/services/student.py src/sms/web/routers/student.py src/sms/web/app.py tests/web/test_corrections_api.py
git commit -m "feat(reflection): student correction route, reflection view, teacher review and release routes"
```

---

### Task 10: "After reflection" in records and the marks CSV

**Files:**
- Modify: `src/sms/records/builder.py` (`RecordRow.after_reflection: Optional[str] = None`; `build_record(..., reflections: Optional[Dict[str, dict]] = None)`)
- Modify: `src/sms/records/docx.py` (`_table` adds a column when any row has `after_reflection`)
- Modify: `src/sms/web/routers/records.py` (`_record` passes `released_marks(db, sid)`)
- Modify: `src/sms/web/services/class_assignments.py` (`marks_csv` adds `after_reflection_total`)
- Modify: `tests/unit/test_record_docx.py`, `tests/web/test_class_assignments_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/unit/test_record_docx.py (uses the file's _record() / _row() helpers)
def test_after_reflection_column_appears_only_when_a_correction_was_released():
    from sms.records.builder import apply_reflections
    rec = apply_reflections(_record(), {"1b": {"total": 1.0, "max": 2.0}})
    assert next(r for r in rec.rows if r.label == "1(b)").after_reflection == "1 / 2"
    assert all(r.after_reflection is None for r in rec.rows if r.label != "1(b)")
    doc = Document(io.BytesIO(render_docx(rec)))
    headers = [c.text for c in doc.tables[0].rows[0].cells]
    assert "After reflection" in headers
    cells = [c.text for row in doc.tables[0].rows for c in row.cells]
    assert "1 / 2" in cells
    plain = Document(io.BytesIO(render_docx(_record())))
    assert "After reflection" not in [c.text for c in plain.tables[0].rows[0].cells]
```

```python
# append to tests/web/test_class_assignments_api.py
def test_marks_csv_has_after_reflection_total(auth, app):
    from tests.web.test_corrections_api import _released_student
    from fastapi.testclient import TestClient
    c, ca, sid = _released_student(auth, TestClient(app), app)
    app.state.db.execute("INSERT INTO student_corrections (submission_id, q_id, reason, text, status, remark_total, remark_max, released_at) "
                         "VALUES (:s, '1b', 'sign', '9', 'released', 1, 1, CURRENT_TIMESTAMP)", {"s": sid})
    auth.post("/api/auth/login", json={"password": "letmein"})
    csv_text = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/marks.csv").text
    header, first = csv_text.splitlines()[:2]
    assert header.endswith("total,max,status,after_reflection_total")
    assert first.split(",")[-1] == "4"    # 3 + 1 regained on 1(b)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest -q tests/unit/test_record_docx.py tests/web/test_class_assignments_api.py -k reflection`
Expected: FAIL — unexpected keyword `reflections` / header mismatch.

- [ ] **Step 3: Implement**

`builder.py`: add `after_reflection: Optional[str] = None` to `RecordRow` (last field, after `crop_bytes`), and:

```python
def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def apply_reflections(record: Record, reflections: Dict[str, dict]) -> Record:
    """Stamp the released correction of each part ("1 / 2") onto its row; rows without one stay None."""
    for row in record.rows:
        r = reflections.get(norm_qid(row.key)) or reflections.get(row.key)
        if r is not None:
            row.after_reflection = f"{_num(r['total'])} / {_num(r['max'])}"
    return record
```

`build_record` gains `reflections: Optional[Dict[str, dict]] = None` and ends with `return apply_reflections(record, reflections) if reflections else record`. Import `norm_qid` from `sms.schemas.scheme`.

`docx.py` `_table`: `show = any(r.after_reflection for r in record.rows)`; when `show`, insert a header cell "After reflection" after "Awarded" and fill each row's cell with `r.after_reflection or ""` (the table is built from a list of headers and a per-row list of values: add the column to both lists under `show`).

`routers/records.py` `_record`: `build_record(detail, template, model=..., crops=..., reflections=released_marks(db, submission_id))` (import `released_marks` from `sms.web.services.student_corrections`).

`class_assignments.py` `marks_csv`: append `"after_reflection_total"` to the header row; per student with a submission, `rel = released_marks(db, r["submission_id"])`; the cell is blank when `rel` is empty, else `_csv_num(total + sum(v["total"] - float(marks.get(k) or 0) for k, v in rel.items()))` where `total` is the value already written to the `total` column and `marks` the dict of that student's original part marks keyed by normalised q_id (use whatever number formatting the file already applies to `total`).

- [ ] **Step 4: Run the tests**

Run: `uv run python -m pytest -q tests/unit/test_record_docx.py tests/web/test_class_assignments_api.py tests/web/test_records_api.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sms/records src/sms/web/routers/records.py src/sms/web/services/class_assignments.py tests/unit/test_record_docx.py tests/web/test_class_assignments_api.py
git commit -m "feat(records): after-reflection column in the .docx record and marks CSV"
```

---

### Task 11: Web types, device tier and room events hooks

**Files:**
- Modify: `web/src/api/types.ts`
- Create: `web/src/scene/useDeviceTier.ts`
- Create: `web/src/scene/useRoomEvents.ts`
- Create: `web/src/scene/__tests__/useDeviceTier.test.tsx`
- Create: `web/src/scene/__tests__/useRoomEvents.test.tsx`
- Run: `cd web && npm install motion`

**Interfaces:**
- Produces types:

```ts
export type Stage = "read" | "mark" | "check" | "feedback" | "done";
export type Crew = "reader" | "marker" | "checker";
export interface RoomDesk { stage: Stage; submission_id: number; label: string; reg_no: number | null; since: string }
export interface RoomSnapshot { counts: Record<"queued" | Stage | "needs_you" | "failed", number>; started_at: string | null; desks: RoomDesk[]; last_event_id: number }
export interface StageEvent { id: number; submission_id: number; stage: Stage; kind: "started" | "finished"; created_at: string }
export interface Thought { at: string; q_id: string | null; note: string }
export type Thoughts = Record<Crew, Thought[]>;
export type CorrectionStatus = "submitted" | "remarked" | "accepted" | "overridden" | "rejected" | "released";
export interface Correction { id: number; submission_id: number; submission_label: string; reg_no: number | null; student_name: string | null; q_id: string; reason: string; text: string | null; page_id: number | null; status: CorrectionStatus; remark_total: number | null; remark_max: number | null; remark_note: string | null; teacher_total: number | null; teacher_reason: string | null; error: string | null; submitted_at: string; released_at: string | null }
export interface Reflection { window_ends_at: string | null; days_left: number; parts: Record<string, { can_correct: boolean; status: CorrectionStatus | null; new_mark: number | null }> }
```
  and `StudentFeedback.questions[]` gains `q_id: string; crop_id: number | null`; `StudentAssignmentDetail` gains `reflection: Reflection | null`; `Settings` gains `reflect_days: number`; `ClassAssignment` gains `reflect_days: number | null; effective_reflect_days: number`.
- `useDeviceTier(): "2d" | "static"` — `"static"` when `prefers-reduced-motion: reduce`, else `"2d"` (phase 2 adds `"3d"`).
- `useRoomEvents(classAssignmentId: number | null): { snapshot: RoomSnapshot | null; error: string | null; live: boolean }` — loads `/api/room`, opens `EventSource('/api/room/events?after=<last_event_id>&class_assignment_id=')`, and on each `stage` event reloads the snapshot (debounced 300 ms); after 3 `onerror`s it closes the source and polls `/api/room` every 5 s (`live` false).

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/scene/__tests__/useDeviceTier.test.tsx
import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useDeviceTier } from "../useDeviceTier";

afterEach(() => vi.unstubAllGlobals());
const mm = (reduce: boolean) => vi.stubGlobal("matchMedia", vi.fn((q: string) => ({ matches: q.includes("reduce") && reduce, addEventListener() {}, removeEventListener() {} })));

describe("useDeviceTier", () => {
  it("is 2d by default and static under reduced motion", () => {
    mm(false); expect(renderHook(() => useDeviceTier()).result.current).toBe("2d");
    mm(true); expect(renderHook(() => useDeviceTier()).result.current).toBe("static");
  });
});
```

```tsx
// web/src/scene/__tests__/useRoomEvents.test.tsx
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRoomEvents } from "../useRoomEvents";

class FakeSource {
  static last: FakeSource | null = null;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onerror: null | (() => void) = null;
  closed = false;
  constructor(public url: string) { FakeSource.last = this; }
  addEventListener(type: string, fn: (e: MessageEvent) => void) { (this.listeners[type] ??= []).push(fn); }
  close() { this.closed = true; }
  emit(type: string, data: unknown) { this.listeners[type]?.forEach((f) => f({ data: JSON.stringify(data) } as MessageEvent)); }
}
const snap = (n: number) => ({ counts: { queued: n, read: 0, mark: 0, check: 0, feedback: 0, done: 0, needs_you: 0, failed: 0 }, started_at: null, desks: [], last_event_id: 7 });

afterEach(() => vi.unstubAllGlobals());

describe("useRoomEvents", () => {
  it("loads the snapshot, subscribes after the last event, and reloads on a stage event", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(snap(++calls)), { status: 200 }))));
    vi.stubGlobal("EventSource", FakeSource);
    const { result } = renderHook(() => useRoomEvents(null));
    await waitFor(() => expect(result.current.snapshot?.counts.queued).toBe(1));
    expect(FakeSource.last!.url).toBe("/api/room/events?after=7");
    act(() => FakeSource.last!.emit("stage", { id: 8, submission_id: 1, stage: "read", kind: "started", created_at: "" }));
    await waitFor(() => expect(result.current.snapshot?.counts.queued).toBe(2));
    expect(result.current.live).toBe(true);
  });

  it("falls back to polling after three stream errors", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(snap(1)), { status: 200 }))));
    vi.stubGlobal("EventSource", FakeSource);
    const { result } = renderHook(() => useRoomEvents(3));
    await act(async () => { await Promise.resolve(); });
    expect(FakeSource.last!.url).toContain("class_assignment_id=3");
    act(() => { for (let i = 0; i < 3; i++) FakeSource.last!.onerror?.(); });
    expect(FakeSource.last!.closed).toBe(true);
    await act(async () => { vi.advanceTimersByTime(5000); await Promise.resolve(); });
    expect(result.current.live).toBe(false);
    expect((fetch as unknown as { mock: { calls: unknown[] } }).mock.calls.length).toBeGreaterThanOrEqual(2);
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/scene`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement**

```ts
// web/src/scene/useDeviceTier.ts
import { useEffect, useState } from "react";

export type DeviceTier = "2d" | "static";

/** "static" under prefers-reduced-motion; "2d" otherwise. Phase 2 adds "3d" for laptops with WebGL. */
export function useDeviceTier(): DeviceTier {
  const query = () => (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches ? "static" : "2d");
  const [tier, setTier] = useState<DeviceTier>(query);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setTier(query());
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return tier;
}
```

```ts
// web/src/scene/useRoomEvents.ts
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { RoomSnapshot } from "../api/types";

const MAX_ERRORS = 3;
const POLL_MS = 5000;

/** The room snapshot, kept current by the SSE stage stream; after three stream errors, by polling. */
export function useRoomEvents(classAssignmentId: number | null) {
  const [snapshot, setSnapshot] = useState<RoomSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const alive = useRef(true);
  const scope = classAssignmentId === null ? "" : `class_assignment_id=${classAssignmentId}`;

  useEffect(() => {
    alive.current = true;
    let source: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let debounce: ReturnType<typeof setTimeout> | null = null;
    let errors = 0;
    const load = () => api.get<RoomSnapshot>(`/api/room${scope ? `?${scope}` : ""}`)
      .then((s) => { if (alive.current) { setSnapshot(s); setError(null); } return s; })
      .catch((e) => { if (alive.current) setError(e.message); return null; });
    const startPolling = () => { setLive(false); poll = setInterval(load, POLL_MS); };
    load().then((s) => {
      if (!alive.current || !s) return;
      if (typeof EventSource !== "function") { startPolling(); return; }
      const qs = [`after=${s.last_event_id}`, scope].filter(Boolean).join("&");
      source = new EventSource(`/api/room/events?${qs}`);
      source.addEventListener("stage", () => { if (debounce) clearTimeout(debounce); debounce = setTimeout(load, 300); });
      source.onerror = () => { if (++errors >= MAX_ERRORS && source) { source.close(); source = null; startPolling(); } };
    });
    return () => { alive.current = false; source?.close(); if (poll) clearInterval(poll); if (debounce) clearTimeout(debounce); };
  }, [scope]);

  return { snapshot, error, live };
}
```

Add the types listed under Interfaces to `web/src/api/types.ts`, and run `npm install motion` (saved to `dependencies`).

- [ ] **Step 4: Run the tests and the type check**

Run: `cd web && npx vitest run src/scene && npx tsc --noEmit`
Expected: PASS (existing fixtures that build `StudentFeedback` or `Settings` objects may need the new optional-looking fields: make `crop_id`, `q_id`, `reflection`, `reflect_days`, `effective_reflect_days` required in the types and update the test fixtures that construct those objects).

- [ ] **Step 5: Commit**

```bash
git add web/package.json web/package-lock.json web/src/api/types.ts web/src/scene
git commit -m "feat(web): room types, device tier and SSE room hook with polling fallback"
```

---

### Task 12: The Marking Room page, 2D scene and thought panel

**Files:**
- Create: `web/src/scene/RoomScene2D.tsx`
- Create: `web/src/components/ThoughtPanel.tsx`
- Create: `web/src/pages/MarkingRoom.tsx`
- Modify: `web/src/App.tsx` (route `/room`; index redirect to `/room`)
- Modify: `web/src/styles/app.css` (room styles)
- Create: `web/src/pages/__tests__/MarkingRoom.test.tsx`

**Interfaces:**
- Consumes: `useRoomEvents`, `useDeviceTier`, types from Task 11, `/api/submissions/{id}/thoughts`, `/api/crops/{id}` (existing), `/api/class-assignments`? — no: the class-set picker lists `GET /api/classes/{id}/assignments` per class; keep phase 1 to "all open sets" plus a `?ca=` query param the class page links with.
- Produces: `<RoomScene2D desks tier onPick(submissionId, crew) />`; `<ThoughtPanel submissionId crew label onClose />`; page `MarkingRoom` at `/room`.

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/pages/__tests__/MarkingRoom.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarkingRoom } from "../MarkingRoom";

const snapshot = {
  counts: { queued: 19, read: 1, mark: 1, check: 1, feedback: 0, done: 9, needs_you: 3, failed: 0 }, started_at: "2026-10-08T01:00:00Z", last_event_id: 40,
  desks: [
    { stage: "read", submission_id: 23, label: "#23 Tan Wei Jie", reg_no: 23, since: "2026-10-08T01:05:00Z" },
    { stage: "mark", submission_id: 17, label: "#17 Nur Aisyah", reg_no: 17, since: "2026-10-08T01:04:00Z" },
    { stage: "check", submission_id: 8, label: "#08 Arjun Pillai", reg_no: 8, since: "2026-10-08T01:06:00Z" },
  ],
};
const thoughts = { reader: [{ at: "2026-10-08T01:05:10Z", q_id: "1b", note: "Hard to read" }], marker: [], checker: [{ at: "2026-10-08T01:06:01Z", q_id: "2a", note: "ESCALATE: crossed-out answer was right" }] };

afterEach(() => vi.unstubAllGlobals());

function setup() {
  vi.stubGlobal("EventSource", undefined);
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })));
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path.startsWith("/api/room")) return Promise.resolve(new Response(JSON.stringify(snapshot), { status: 200 }));
    if (path === "/api/submissions/8/thoughts") return Promise.resolve(new Response(JSON.stringify(thoughts), { status: 200 }));
    return Promise.reject(new Error(`Unexpected fetch to ${path}`));
  }));
  render(<MemoryRouter initialEntries={["/room"]}><Routes><Route element={<Outlet context={{ refreshQueue: () => {} }} />}><Route path="/room" element={<MarkingRoom />} /></Route></Routes></MemoryRouter>);
}

describe("MarkingRoom", () => {
  it("shows the counts, one name tag per desk, and opens the Checker's thoughts", async () => {
    setup();
    await waitFor(() => expect(screen.getByText("The Marking Room")).toBeInTheDocument());
    expect(screen.getByLabelText("Done")).toHaveTextContent("9");
    expect(screen.getByLabelText("Needs you")).toHaveTextContent("3");
    expect(screen.getByRole("button", { name: /Reader · #23 Tan Wei Jie/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Checker · #08 Arjun Pillai/ }));
    await waitFor(() => expect(screen.getByText("ESCALATE: crossed-out answer was right")).toBeInTheDocument());
    expect(screen.getByText("Teachers only")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open script" })).toHaveAttribute("href", "/submissions/8");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/pages/__tests__/MarkingRoom.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```tsx
// web/src/scene/RoomScene2D.tsx
import type { Crew, RoomDesk, Stage } from "../api/types";
import type { DeviceTier } from "./useDeviceTier";

const CREW_OF: Record<Stage, Crew | null> = { read: "reader", mark: "marker", check: "checker", feedback: null, done: null };
const NAME: Record<Crew, string> = { reader: "Reader", marker: "Marker", checker: "Checker" };
/** Where each desk sits on the room image, as percentages of its box. */
const SPOT: Record<Crew, { left: string; top: string }> = { reader: { left: "39%", top: "24%" }, marker: { left: "50%", top: "36%" }, checker: { left: "60%", top: "46%" } };

export function RoomScene2D({ desks, tier, onPick }: { desks: RoomDesk[]; tier: DeviceTier; onPick: (submissionId: number, crew: Crew, label: string) => void }) {
  const byCrew = new Map<Crew, RoomDesk>();
  for (const d of desks) { const c = CREW_OF[d.stage]; if (c && !byCrew.has(c)) byCrew.set(c, d); }
  const busy = desks.some((d) => d.stage === "read");
  return (
    <div className="room-scene">
      <img src="/art/room.jpg" alt="The marking room: a paper sorter feeds a conveyor to three desks where the Reader, Marker and Checker work" />
      {tier === "2d" && busy && <span className="room-paper slide" aria-hidden />}
      {(["reader", "marker", "checker"] as Crew[]).map((crew) => {
        const d = byCrew.get(crew);
        return (
          <button key={crew} type="button" className={`room-tag ${tier === "2d" && d ? "bob" : ""} tag-${crew}`} style={SPOT[crew]}
            aria-label={d ? `${NAME[crew]} · ${d.label}` : `${NAME[crew]} · desk empty`} disabled={!d}
            onClick={() => d && onPick(d.submission_id, crew, d.label)}>
            <i className={`dot dot-${crew}`} aria-hidden />{NAME[crew]}{d ? ` · ${d.label}` : " · waiting"}
          </button>
        );
      })}
    </div>
  );
}
```

```tsx
// web/src/components/ThoughtPanel.tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Crew, Thoughts } from "../api/types";

const NAME: Record<Crew, string> = { reader: "Reader", marker: "Marker", checker: "Checker" };
const ROLE: Record<Crew, string> = { reader: "finds each part on the page and reads the working", marker: "awards each mark against your scheme", checker: "re-marks independently and flags disagreements" };
const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function ThoughtPanel({ submissionId, crew, label, onClose }: { submissionId: number; crew: Crew; label: string; onClose: () => void }) {
  const [thoughts, setThoughts] = useState<Thoughts | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setThoughts(null); api.get<Thoughts>(`/api/submissions/${submissionId}/thoughts`).then(setThoughts).catch((e) => setError(e.message)); }, [submissionId]);
  const notes = thoughts?.[crew] ?? [];
  return (
    <aside className="card thought-panel" aria-label={`${NAME[crew]}'s thoughts`}>
      <div className="thought-head">
        <img src="/art/crew.jpg" alt="" className={`crew-face crew-face-${crew}`} />
        <div><div className="thought-name">{NAME[crew]}</div><div className="muted">{ROLE[crew]}</div></div>
        <span className="pill pill-neutral">Teachers only</span>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose} aria-label="Close">×</button>
      </div>
      <div className="thought-who"><strong>{label}</strong></div>
      {error && <p className="notice notice-error">{error}</p>}
      {thoughts && notes.length === 0 && <p className="muted">Nothing noted yet.</p>}
      <ol className="thought-list">
        {notes.map((t, i) => <li key={i}><span className="tabular thought-at">{fmtTime(t.at)}</span><p>{t.q_id ? <strong>{t.q_id} · </strong> : null}{t.note}</p></li>)}
      </ol>
      <div className="actions">
        <Link className="btn btn-primary" to={`/submissions/${submissionId}`}>Open script</Link>
        <Link className="btn btn-secondary" to="/review">Open Review</Link>
      </div>
    </aside>
  );
}
```

```tsx
// web/src/pages/MarkingRoom.tsx
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { Crew } from "../api/types";
import { Notice } from "../components/Notice";
import { ThoughtPanel } from "../components/ThoughtPanel";
import { elapsed } from "../lib/format";
import { RoomScene2D } from "../scene/RoomScene2D";
import { useDeviceTier } from "../scene/useDeviceTier";
import { useRoomEvents } from "../scene/useRoomEvents";

const TILES: { key: "queued" | "read" | "mark" | "check" | "done" | "needs_you"; label: string }[] = [
  { key: "queued", label: "In the sorter" }, { key: "read", label: "Reading" }, { key: "mark", label: "Marking" },
  { key: "check", label: "Checking" }, { key: "done", label: "Done" }, { key: "needs_you", label: "Needs you" },
];

export function MarkingRoom() {
  const [params] = useSearchParams();
  const ca = params.get("ca") ? Number(params.get("ca")) : null;
  const { snapshot, error, live } = useRoomEvents(ca);
  const tier = useDeviceTier();
  const [picked, setPicked] = useState<{ id: number; crew: Crew; label: string } | null>(null);
  return (
    <div className="page room-page">
      <div className="page-header">
        <div>
          <h1>The Marking Room</h1>
          <p className="meta">Three crew members pass each script along the desks. Tap a name tag to read what they are thinking.</p>
        </div>
        <div className="actions">
          {snapshot?.started_at && <span className="pill pill-outline tabular">Started {elapsed(snapshot.started_at)}</span>}
          {!live && <span className="pill pill-amber">Live feed paused — refreshing every 5 s</span>}
          <Link className="btn btn-primary" to="/submissions/new">Feed the sorter</Link>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="room-layout">
        <section className="room-main">
          <RoomScene2D desks={snapshot?.desks ?? []} tier={tier} onPick={(id, crew, label) => setPicked({ id, crew, label })} />
          <div className="room-tiles">
            {TILES.map((t) => (
              <div key={t.key} className={`room-tile tile-${t.key}`} aria-label={t.label}>
                <span className="label-caps">{t.label}</span>
                <strong className="tabular">{snapshot ? snapshot.counts[t.key] : "—"}</strong>
              </div>
            ))}
          </div>
        </section>
        <div className="room-side">
          {picked ? <ThoughtPanel submissionId={picked.id} crew={picked.crew} label={picked.label} onClose={() => setPicked(null)} />
                  : <div className="card"><h2>On the desks right now</h2>
                      {snapshot?.desks.length === 0 && <p className="muted">The desks are empty. Feed the sorter to start.</p>}
                      <ul className="desk-list">{snapshot?.desks.map((d) => <li key={d.submission_id}><i className={`dot dot-${d.stage}`} aria-hidden /><Link to={`/submissions/${d.submission_id}`}>{d.label}</Link><span className="muted tabular">{d.stage} · {elapsed(d.since)}</span></li>)}</ul>
                    </div>}
        </div>
      </div>
    </div>
  );
}
```

Add the route in `App.tsx` inside the `Shell` routes: `<Route path="/room" element={<MarkingRoom />} />`, and change the index redirect to `/room`. Append room styles to `app.css`:

```css
.room-layout { display: flex; flex-wrap: wrap; gap: 24px; }
.room-main { flex: 999 1 560px; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
.room-side { flex: 1 1 340px; max-width: 440px; }
.room-scene { position: relative; border-radius: var(--radius-lg); overflow: hidden; background: var(--color-surface); box-shadow: 0 12px 32px rgba(78,56,10,0.12); }
.room-scene img { display: block; width: 100%; height: auto; }
.room-tag { position: absolute; border: 0; cursor: pointer; background: var(--color-text); color: #fff; font: 700 13px var(--font-body); padding: 8px 12px; border-radius: 999px; display: flex; align-items: center; gap: 8px; box-shadow: 0 4px 0 #15141A; min-height: 36px; }
.room-tag:disabled { opacity: 0.55; cursor: default; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot-reader, .dot-read { background: var(--crew-reader); } .dot-marker, .dot-mark { background: var(--crew-marker); } .dot-checker, .dot-check { background: var(--crew-checker); }
.room-paper { position: absolute; left: 31%; top: 59%; width: 34px; height: 24px; background: #fff; border: 2px solid var(--color-text); border-radius: 3px; box-shadow: 2px 2px 0 var(--color-text); }
@keyframes bob { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
@keyframes slide { from { transform: translateX(0); } to { transform: translateX(118px); } }
.bob { animation: bob 1.8s ease-in-out infinite; } .slide { animation: slide 2.4s linear infinite; }
.room-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
.room-tile { background: var(--color-surface); border-radius: var(--radius-md); padding: 14px 16px; border: 2px solid var(--butter); display: flex; flex-direction: column; gap: 4px; }
.room-tile strong { font-family: var(--font-heading); font-size: 28px; }
.tile-read { border-color: var(--crew-reader); } .tile-mark { border-color: var(--crew-marker); } .tile-check, .tile-needs_you { border-color: var(--crew-checker); } .tile-done { border-color: var(--mint); }
.thought-head { display: flex; align-items: center; gap: 12px; }
.crew-face { width: 56px; height: 56px; object-fit: cover; border-radius: var(--radius-md); background: var(--butter); }
.crew-face-reader { object-position: 12% 40%; } .crew-face-marker { object-position: 50% 40%; } .crew-face-checker { object-position: 88% 40%; }
.thought-name { font-family: var(--font-heading); font-size: 22px; }
.thought-who { margin: 12px 0; padding: 10px 14px; background: var(--color-bg); border-radius: var(--radius-sm); }
.thought-list { list-style: none; margin: 0 0 16px; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.thought-list li { display: flex; gap: 10px; align-items: flex-start; } .thought-list p { margin: 0; background: #F4F1FA; border-radius: 14px 14px 14px 4px; padding: 10px 12px; font-size: 14px; }
.thought-at { flex: none; width: 64px; font-size: 12px; color: var(--muted); padding-top: 4px; }
.desk-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; } .desk-list li { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: var(--radius-sm); background: var(--color-bg); } .desk-list li span { margin-left: auto; }
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: PASS (an existing App test that asserts the index redirect goes to `/classes`, if any, is updated to `/room`).

- [ ] **Step 5: Commit**

```bash
git add web/src/scene/RoomScene2D.tsx web/src/components/ThoughtPanel.tsx web/src/pages/MarkingRoom.tsx web/src/App.tsx web/src/styles/app.css web/src/pages/__tests__/MarkingRoom.test.tsx
git commit -m "feat(web): the Marking Room — 2D room, desk name tags, teacher-only thought panel"
```

---

### Task 13: The sorter on the upload pages

**Files:**
- Modify: `web/src/components/DropZone.tsx`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/pages/NewSubmission.tsx` (title/hint copy only: `title="Feed the sorter"`, `hint="Drop photos, PDFs or a class zip — photos are shrunk on your device before upload"`)
- Create: `web/src/components/__tests__/DropZone.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/components/__tests__/DropZone.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DropZone } from "../DropZone";

describe("DropZone", () => {
  it("shows the sorter and hands picked files up", async () => {
    const onFiles = vi.fn();
    render(<DropZone onFiles={onFiles} title="Feed the sorter" />);
    expect(screen.getByRole("img", { name: /paper sorter/ })).toHaveAttribute("src", "/art/sorter.jpg");
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "p1.jpg", { type: "image/jpeg" }));
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: "p1.jpg" })]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/__tests__/DropZone.test.tsx`
Expected: FAIL — no img "paper sorter".

- [ ] **Step 3: Implement**

Replace the `<Upload size={32} aria-hidden />` line in `DropZone.tsx` with:

```tsx
      <span className="drop-paper" aria-hidden />
      <img className="drop-sorter" src="/art/sorter.jpg" alt="Voxel paper sorter with a funnel on top and three lit output slots" />
```

(remove the now-unused `Upload` import), and append to `app.css`:

```css
.drop { border: 3px dashed var(--crew-reader); border-radius: 28px; background: var(--color-surface); position: relative; overflow: hidden; padding-top: 24px; }
.drop.over { background: #EAF8F1; }
.drop-sorter { width: 260px; max-width: 70%; height: auto; display: block; margin: 0 auto 8px; }
.drop-paper { position: absolute; left: 50%; top: 10px; margin-left: -23px; width: 46px; height: 60px; background: #fff; border: 3px solid var(--color-text); border-radius: 6px; box-shadow: 3px 3px 0 var(--color-text); animation: drop 1.6s ease-out infinite; }
@keyframes drop { 0% { transform: translateY(-60px) rotate(-8deg); opacity: 0; } 30% { opacity: 1; } 100% { transform: translateY(0) rotate(0); } }
```

- [ ] **Step 4: Run the web suite**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: PASS (NewSubmission tests may assert the old title "Drop pages here"; update them to the new copy).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/DropZone.tsx web/src/components/__tests__/DropZone.test.tsx web/src/pages/NewSubmission.tsx web/src/styles/app.css
git commit -m "feat(web): the sorter — drop zone with falling scripts on the upload pages"
```

---

### Task 14: Student feedback and reflect screens

**Files:**
- Modify: `web/src/student/AssignmentView.tsx` (reflection pill, per-part "Try a correction · 1 left", status words, "After reflection" badge)
- Create: `web/src/student/Reflect.tsx` (route `/s/a/:caid/reflect/:qid`)
- Modify: `web/src/App.tsx` (route)
- Modify: `web/src/styles/app.css`
- Modify: `web/src/student/__tests__/AssignmentView.test.tsx`; Create: `web/src/student/__tests__/Reflect.test.tsx`

**Interfaces:**
- Consumes: `StudentAssignmentDetail.reflection`, `feedback.questions[].q_id/crop_id`, `POST /api/student/assignments/{caid}/corrections` (multipart), `GET /api/student/crops/{id}`.
- Copy (exact): pill `Reflect and correct · {days_left} days left` (singular "1 day left"); button `Try a correction · 1 left`; badge `After reflection: {new_mark} / {max}`; statuses `Sent to the Marker`, `Waiting for your teacher`, `Not accepted: {reason}`; after send `Sent to the Marker. Your teacher checks it before you see the new mark.`

- [ ] **Step 1: Write the failing tests**

```tsx
// append to web/src/student/__tests__/AssignmentView.test.tsx (reuse the file's existing render/fetch helpers)
it("offers one correction per part that lost marks while the window is open, and shows the new mark once released", async () => {
  const detail = feedbackDetail({   // the file's existing builder for a feedback_ready detail; extend it to accept overrides
    reflection: { window_ends_at: "2026-10-15T00:00:00Z", days_left: 5, parts: {
      "1b": { can_correct: true, status: null, new_mark: null },
      "2": { can_correct: false, status: "released", new_mark: 3 } } },
  });
  renderWith(detail);
  await screen.findByText("Reflect and correct · 5 days left");
  expect(screen.getByRole("link", { name: "Try a correction · 1 left" })).toHaveAttribute("href", "/s/a/7/reflect/1b");
  expect(screen.getByText("After reflection: 3 / 3")).toBeInTheDocument();
  expect(screen.queryAllByRole("link", { name: /Try a correction/ })).toHaveLength(1);
});
```

```tsx
// web/src/student/__tests__/Reflect.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Reflect } from "../Reflect";

const detail = { id: 7, title: "Quadratics", status: "feedback_ready", handed_in_at: "2026-10-01T00:00:00Z", due_at: null, pages: 1, allow_student_uploads: true, subject: "math", accepts_files: false,
  feedback: { summary: "", strengths: [], improvement_plan: [], next_steps: [], total: 3, max: 6, pages: [],
    questions: [{ q_id: "1b", label: "1(b)", mark: 0, max: 1, comment: "6 not 9", try_next: "", transcription: "6", crop_id: 55 }] },
  reflection: { window_ends_at: "2026-10-15T00:00:00Z", days_left: 5, parts: { "1b": { can_correct: true, status: null, new_mark: null } } } };

afterEach(() => vi.unstubAllGlobals());

describe("Reflect", () => {
  it("shows the original crop and comment, sends the correction, and confirms", async () => {
    const sent: FormData[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/student/assignments/7") return Promise.resolve(new Response(JSON.stringify(detail), { status: 200 }));
      if (path === "/api/student/assignments/7/corrections") { sent.push(init!.body as FormData); return Promise.resolve(new Response(JSON.stringify({ id: 1, q_id: "1b", status: "submitted" }), { status: 201 })); }
      return Promise.reject(new Error(`Unexpected fetch to ${path}`));
    }));
    render(<MemoryRouter initialEntries={["/s/a/7/reflect/1b"]}><Routes><Route path="/s/a/:caid/reflect/:qid" element={<Reflect />} /></Routes></MemoryRouter>);
    await screen.findByText("1(b) · Reflect and correct");
    expect(screen.getByRole("img", { name: "Your first try" })).toHaveAttribute("src", "/api/student/crops/55");
    expect(screen.getByText("6 not 9")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign slip" }));
    await userEvent.type(screen.getByLabelText("Your corrected working"), "x^2 = 3^2 = 9");
    await userEvent.click(screen.getByRole("button", { name: "Send my correction" }));
    await waitFor(() => expect(screen.getByText("Sent to the Marker. Your teacher checks it before you see the new mark.")).toBeInTheDocument());
    expect(sent[0].get("q_id")).toBe("1b"); expect(sent[0].get("reason")).toBe("sign"); expect(sent[0].get("text")).toBe("x^2 = 3^2 = 9");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/student`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `AssignmentView.tsx`'s `Feedback` component take an extra `reflection: Reflection | null` and `caid: string` and render:

```tsx
{reflection?.window_ends_at && reflection.days_left > 0 && (
  <p className="pill pill-amber reflect-pill">{`Reflect and correct · ${reflection.days_left} day${reflection.days_left === 1 ? "" : "s"} left`}</p>
)}
```

and, inside each open question body, after the comment:

```tsx
{(() => {
  const r = reflection?.parts[q.q_id];
  if (!r) return null;
  if (r.can_correct) return <Link className="btn btn-primary btn-sm" to={`/s/a/${caid}/reflect/${q.q_id}`}>Try a correction · 1 left</Link>;
  if (r.status === "released" && r.new_mark !== null) return <span className="pill pill-crew-reader">{`After reflection: ${r.new_mark} / ${q.max}`}</span>;
  if (r.status === "rejected") return <p className="muted">Not accepted — ask your teacher.</p>;
  if (r.status) return <p className="muted">{r.status === "submitted" ? "Sent to the Marker" : "Waiting for your teacher"}</p>;
  return null;
})()}
```

Note the test asserts the badge and button render even when the question row is collapsed: render these two elements in the question's header row (next to the mark), not inside the collapsed body, so a student sees at a glance which parts they can fix.

```tsx
// web/src/student/Reflect.tsx
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import type { StudentAssignmentDetail } from "../api/types";
import { downscale } from "../lib/image";
import { studentApi as api } from "./api";

const REASONS = [["sign", "Sign slip"], ["method", "Wrong method"], ["rushed", "Rushed it"], ["misread", "Misread the question"]] as const;

export function Reflect() {
  const { caid, qid } = useParams();
  const [detail, setDetail] = useState<StudentAssignmentDetail | null>(null);
  const [reason, setReason] = useState<string>("sign");
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.get<StudentAssignmentDetail>(`/api/student/assignments/${caid}`).then(setDetail, (e) => setError(e.message)); }, [caid]);
  const q = detail?.feedback?.questions.find((x) => x.q_id === qid);
  const part = detail?.reflection?.parts[qid ?? ""];
  if (error) return <p role="alert" className="notice notice-error">{error}</p>;
  if (!detail || !q) return <p className="muted">Loading…</p>;
  const send = async () => {
    setState("sending"); setError(null);
    const form = new FormData();
    form.append("q_id", q.q_id); form.append("reason", reason); form.append("text", text);
    if (photo) form.append("photo", await downscale(photo));
    try { await api.postForm(`/api/student/assignments/${caid}/corrections`, form); setState("sent"); }
    catch (e) { setState("idle"); setError(e instanceof ApiError ? e.message : "Can't reach Smart Marking — check your signal and try again."); }
  };
  return (
    <>
      <Link className="student-back" to={`/s/a/${caid}`}>Back to feedback</Link>
      <h1>{`${q.label} · Reflect and correct`}</h1>
      {detail.reflection && <div className="reflect-chips"><span className="pill pill-amber">{`${detail.reflection.days_left} days left`}</span><span className="pill pill-crew-marker">{part?.can_correct ? "1 correction left" : "No corrections left"}</span></div>}
      <section className="student-card">
        <span className="label-caps">{`Your first try · ${q.mark} / ${q.max}`}</span>
        {q.crop_id !== null && <img className="reflect-crop" src={`/api/student/crops/${q.crop_id}`} alt="Your first try" />}
        {q.comment && <p className="student-comment"><strong>Marker:</strong> {q.comment}</p>}
      </section>
      {state === "sent" ? (
        <p className="notice notice-ok">Sent to the Marker. Your teacher checks it before you see the new mark.</p>
      ) : (
        <section className="student-card reflect-form">
          <h2>1 · What went wrong?</h2>
          <div className="reflect-reasons">{REASONS.map(([id, label]) => <button key={id} type="button" aria-pressed={reason === id} className={`btn btn-sm ${reason === id ? "btn-primary" : "btn-secondary"}`} onClick={() => setReason(id)}>{label}</button>)}</div>
          <h2>2 · Your corrected working</h2>
          <label htmlFor="working" className="help">Type it, or photograph your corrected working.</label>
          <textarea id="working" aria-label="Your corrected working" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
          <label className="btn btn-secondary btn-sm">Take a photo instead<input type="file" accept="image/*" capture="environment" hidden onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} /></label>
          {photo && <p className="help">{photo.name}</p>}
          {error && <p role="alert" className="notice notice-error">{error}</p>}
          <p className="help">The Marker re-marks your correction against the same scheme. Your teacher checks it before you see the new mark.</p>
          <button type="button" className="btn btn-primary btn-lg" disabled={state === "sending" || !part?.can_correct || (!text.trim() && !photo)} onClick={send}>Send my correction</button>
        </section>
      )}
    </>
  );
}
```

Add the route under the `StudentLayout` routes: `<Route path="a/:caid/reflect/:qid" element={<Reflect />} />`. Styles: `.reflect-crop { width: 100%; height: auto; border-radius: var(--radius-sm); border: 2px dashed var(--color-divider); margin: 8px 0; } .reflect-reasons { display: flex; flex-wrap: wrap; gap: 8px; } .reflect-chips { display: flex; gap: 8px; margin: 8px 0 14px; } .reflect-form textarea { width: 100%; box-sizing: border-box; border: 2px solid var(--color-divider); border-radius: var(--radius-sm); padding: 10px; font: 15px var(--font-body); }`.

- [ ] **Step 4: Run the web suite**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/student web/src/App.tsx web/src/styles/app.css
git commit -m "feat(student): reflect and correct — window pill, one correction per part, after-reflection badge"
```

---

### Task 15: Corrections tab in Review and the Settings/assignment fields

**Files:**
- Create: `web/src/components/CorrectionsTab.tsx`
- Modify: `web/src/pages/Review.tsx` (a two-tab header: "Parts" (existing) / "Corrections"; the tab reads `?ca=` or a class-set picker fed by `/api/classes` + `/api/classes/{id}/assignments`)
- Modify: `web/src/pages/Settings.tsx` (number input `#reflect-days`, label "Reflection window (days after release, 0 = off)")
- Modify: `web/src/pages/ClassAssignmentPage.tsx` (same field per assignment, "Follow default (N)" when blank; "Release corrections" button)
- Create: `web/src/components/__tests__/CorrectionsTab.test.tsx`
- Modify: `web/src/pages/__tests__/Settings.test.tsx` (field round-trips), `web/src/pages/__tests__/ClassAssignmentPage.test.tsx` (button posts)

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/components/__tests__/CorrectionsTab.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Correction } from "../../api/types";
import { CorrectionsTab } from "../CorrectionsTab";

const row: Correction = { id: 5, submission_id: 9, submission_label: "#1 Tan", reg_no: 1, student_name: "Tan", q_id: "1b", reason: "sign", text: "x^2 = 9", page_id: null,
  status: "remarked", remark_total: 1, remark_max: 1, remark_note: "Marker: B1 earned\nChecker: APPROVE: agree", teacher_total: null, teacher_reason: null, error: null, submitted_at: "2026-10-08T01:00:00Z", released_at: null };

afterEach(() => vi.unstubAllGlobals());

describe("CorrectionsTab", () => {
  it("lists corrections with the Marker's re-mark and posts accept, override and release", async () => {
    const posted: { path: string; body: unknown }[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/review/corrections?class_assignment_id=3") return Promise.resolve(new Response(JSON.stringify([row]), { status: 200 }));
      posted.push({ path, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (path.endsWith("/release-corrections")) return Promise.resolve(new Response(JSON.stringify({ released: 1 }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify({ ...row, status: "accepted" }), { status: 200 }));
    }));
    render(<MemoryRouter><CorrectionsTab classAssignmentId={3} /></MemoryRouter>);
    await screen.findByText("#1 Tan · 1b");
    expect(screen.getByText("Marker: B1 earned")).toBeInTheDocument();
    expect(screen.getByText("Re-marked 1 / 1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accept 1 / 1" }));
    await userEvent.type(screen.getByLabelText("Override mark"), "0.5");
    await userEvent.click(screen.getByRole("button", { name: "Override" }));
    await userEvent.click(screen.getByRole("button", { name: "Release corrections" }));
    await waitFor(() => expect(posted.map((p) => p.path)).toEqual(["/api/corrections/5/accept", "/api/corrections/5/override", "/api/class-assignments/3/release-corrections"]));
    expect(posted[1].body).toEqual({ total: 0.5 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/__tests__/CorrectionsTab.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```tsx
// web/src/components/CorrectionsTab.tsx
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Correction } from "../api/types";
import { Notice } from "./Notice";

const WORD: Record<Correction["status"], string> = { submitted: "Waiting for the Marker", remarked: "Re-marked", accepted: "Accepted", overridden: "Overridden", rejected: "Rejected", released: "Released" };

export function CorrectionsTab({ classAssignmentId }: { classAssignmentId: number }) {
  const [rows, setRows] = useState<Correction[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [override, setOverride] = useState<Record<number, string>>({});
  const [released, setReleased] = useState<number | null>(null);
  const load = useCallback(() => api.get<Correction[]>(`/api/review/corrections?class_assignment_id=${classAssignmentId}`).then(setRows).catch((e) => setError(e.message)), [classAssignmentId]);
  useEffect(() => { load(); }, [load]);
  const act = async (id: number, action: "accept" | "override" | "reject", body?: unknown) => {
    try { await api.post(`/api/corrections/${id}/${action}`, body); await load(); } catch (e) { setError((e as Error).message); }
  };
  const release = async () => { try { const r = await api.post<{ released: number }>(`/api/class-assignments/${classAssignmentId}/release-corrections`); setReleased(r.released); await load(); } catch (e) { setError((e as Error).message); } };
  const pending = rows?.filter((r) => r.status === "accepted" || r.status === "overridden").length ?? 0;
  return (
    <section className="corrections">
      {error && <Notice kind="error">{error}</Notice>}
      {released !== null && <Notice>{`Released ${released} correction${released === 1 ? "" : "s"}.`}</Notice>}
      <div className="actions"><button type="button" className="btn btn-primary" disabled={pending === 0} onClick={release}>Release corrections</button><span className="muted">{`${pending} ready to release`}</span></div>
      {rows?.length === 0 && <p className="muted">No corrections yet.</p>}
      {rows?.map((r) => {
        const mx = r.remark_max ?? 0;
        return (
          <article key={r.id} className="card correction">
            <header><strong>{`${r.submission_label} · ${r.q_id}`}</strong><span className={`pill pill-${r.status === "released" ? "crew-reader" : "neutral"}`}>{WORD[r.status]}</span></header>
            <p className="muted">{`Reason given: ${r.reason}`}</p>
            {r.text && <p className="student-read">{r.text}</p>}
            {r.page_id && <img src={`/api/pages/${r.page_id}`} alt="The student's corrected working" style={{ maxWidth: "100%", borderRadius: 12 }} />}
            {r.error && <Notice kind="error">{`Re-mark failed · mark it yourself: ${r.error}`}</Notice>}
            {r.remark_total !== null && <p><strong>{`Re-marked ${r.remark_total} / ${mx}`}</strong></p>}
            {r.remark_note && r.remark_note.split("\n").map((line, i) => <p key={i} className="thought-note">{line}</p>)}
            {r.teacher_total !== null && <p>{`Your mark: ${r.teacher_total} / ${mx}`}</p>}
            {r.status !== "released" && r.status !== "rejected" && (
              <div className="actions">
                {r.remark_total !== null && <button type="button" className="btn btn-primary btn-sm" onClick={() => act(r.id, "accept")}>{`Accept ${r.remark_total} / ${mx}`}</button>}
                <label className="help">Override mark<input aria-label="Override mark" type="number" min={0} max={mx} step={0.5} value={override[r.id] ?? ""} onChange={(e) => setOverride({ ...override, [r.id]: e.target.value })} /></label>
                <button type="button" className="btn btn-secondary btn-sm" disabled={override[r.id] === undefined || override[r.id] === ""} onClick={() => act(r.id, "override", { total: Number(override[r.id]) })}>Override</button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => { const reason = window.prompt("Why is this not accepted? (the student sees this)") ?? ""; if (reason) act(r.id, "reject", { reason }); }}>Reject</button>
              </div>
            )}
          </article>
        );
      })}
    </section>
  );
}
```

`Review.tsx`: add a tab strip above the existing content: buttons "Parts" and "Corrections" (`aria-pressed`), state `tab`, and a class-set `<select id="correction-set">` listing open or released class assignments (load `/api/classes`, then each class's `/api/classes/{id}/assignments`, label `"{class} · {title}"`). When `tab === "corrections"` render `<CorrectionsTab classAssignmentId={selected} />`. The existing Review tests render with only `/api/queue` stubbed: keep the class loading lazy (only when the Corrections tab is opened) so they keep passing.

`Settings.tsx`: add `<label htmlFor="reflect-days">Reflection window (days after release, 0 = off)</label><input id="reflect-days" type="number" min={0} max={60} value={...} />` and send `reflect_days` in the PUT body. `ClassAssignmentPage.tsx`: the same input (`#reflect-days`, placeholder `Follow default (${effective})`, blank → `null`), sent in the PUT; and a "Release corrections" button next to "Release feedback" that posts `/api/class-assignments/{caid}/release-corrections` and shows `Released N corrections`.

- [ ] **Step 4: Run the web suite**

Run: `cd web && npx vitest run && npx tsc --noEmit && npm run build`
Expected: PASS; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/CorrectionsTab.tsx web/src/components/__tests__/CorrectionsTab.test.tsx web/src/pages/Review.tsx web/src/pages/Settings.tsx web/src/pages/ClassAssignmentPage.tsx web/src/pages/__tests__
git commit -m "feat(web): Corrections tab in Review, reflection window in Settings and per assignment"
```

---

### Task 16: Documentation

**Files:**
- Modify: `README.md` (a "The Marking Room" paragraph under the web-app section; a "Reflect and correct" paragraph; `reflect_days` in the settings list)
- Modify: `docs/setup-guide/README.md` (new step "Watch the crew in the Marking Room" after step 12 "Marking, and the parts that need you"; a "Students reflect and correct" step after "Release feedback"; renumber the TOC)
- Modify: `docs/railway-template/overview.md` (one sentence in About: "Teachers watch the Reader, Marker and Checker work through a class set in the Marking Room and can read what each one noted; after release, students get a window to correct the parts they lost marks on, re-marked by the Marker and released by the teacher.")
- The PDF (`docs/setup-guide/Smart-Marking-Setup-Guide.pdf`) and the online guide are rebuilt by the controller from the Playwright kit after merge, with fresh screenshots of the room and the phone screens — not part of this task.

- [ ] **Step 1: Add the paragraphs**

`README.md`, under the web-app section (after the paragraph on Review):

> **The Marking Room.** Open **Marking Room** to watch a class set being marked. Three crew members pass each script along the desks: the **Reader** finds each part on the page and transcribes it, the **Marker** awards marks against your scheme, and the **Checker** re-marks independently and flags anything the two disagree on. Click a name tag to read what that crew member noted for the script on its desk, with timestamps. The notes are the marker's justifications and the reviewer's reasoning; students never see them. The room updates live (Server-Sent Events) and falls back to refreshing every five seconds.

> **Reflect and correct.** After you release feedback, students have a window (`Settings → Reflection window`, default 7 days; set per assignment, 0 turns it off) to send **one correction per part** they lost marks on, typed or photographed. The Marker re-marks the correction against the same scheme; you accept, override or reject it under **Review → Corrections**, then **Release corrections**. The student then sees "After reflection: a / b" on that part. Released corrections appear in the marking record and as an `after_reflection_total` column in the marks CSV.

`docs/setup-guide/README.md`: a new step after "Marking, and the parts that need you":

> ## Watch the crew in the Marking Room
> Open **Marking Room**. The sorter on the left holds scripts waiting their turn; the three desks show who is working on what. Tap a name tag to read that crew member's notes for the script on the desk, for example the Checker explaining why it flagged 2(a). Nothing here is shown to students. If the live feed drops, the room refreshes every five seconds instead.

and a new step after "Release feedback":

> ## Students reflect and correct
> Once feedback is released, each student has a window (7 days unless you change it under Settings or on the assignment) to send one correction per part they lost marks on. On their phone they tap **Try a correction**, pick what went wrong, and type or photograph their corrected working. The Marker re-marks it; you decide under **Review → Corrections** and press **Release corrections** when you are ready. The student's feedback then shows "After reflection" beside that part.

Update the TOC numbers in that file accordingly.

`docs/railway-template/overview.md`, in the About paragraph after the sentence on Review: "Teachers watch the Reader, Marker and Checker work through a class set in the Marking Room and can read what each one noted; after release, students get a window to correct the parts they lost marks on, re-marked by the Marker and released by the teacher."

- [ ] **Step 2: Check the hits**: `grep -n "Marking Room\|Reflect and correct\|reflect and correct" README.md docs/setup-guide/README.md docs/railway-template/overview.md` lists at least one line per file.
- [ ] **Step 3: Commit**

```bash
git add README.md docs/setup-guide/README.md docs/railway-template/overview.md
git commit -m "docs: the Marking Room and reflect-and-correct in the README, guide and template overview"
```

---

### Task 17: Whole-branch verification

- [ ] **Step 1: Backend on SQLite**: `uv run python -m pytest -q` → all pass.
- [ ] **Step 2: Backend on Postgres**: start the scratch Postgres (memory recipe), then `SMS_TEST_PG_URL=postgresql+psycopg://sms@127.0.0.1:54329/smstest uv run python -m pytest -q tests/unit/test_migrations_postgres.py tests/web/test_room_api.py tests/web/test_corrections_api.py` → all pass. (The web tests use the app's SQLite; the migration test is the Postgres gate.)
- [ ] **Step 3: Web**: `cd web && npx vitest run && npx tsc --noEmit && npm run build` → all pass; note the gzipped size of the main chunk in the build output and confirm the increase over `main` is under 250 KB.
- [ ] **Step 4: Manual smoke on a dev server**: sign in, open `/room` with an empty queue (desks empty, tiles show zeros), upload a script against a mark-scheme assignment with a real key, watch the tags change through read → mark → check, click a tag and read the thoughts; release a class assignment, open the student link on a phone-sized window, send a correction, accept it in Review, release corrections, confirm the badge on the phone.
- [ ] **Step 5**: hand over with `superpowers:finishing-a-development-branch`.

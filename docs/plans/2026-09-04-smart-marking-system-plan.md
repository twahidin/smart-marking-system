# Smart Marking System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A CLI marking pipeline (extract → mark → review → feedback) for math scripts from images, with teacher escalation, case memory, and nightly reflection that makes agents smarter and faster over time.

**Architecture:** Standalone Python package `sms` depending on upstream `atomic-agents` (v2). Each pipeline role is an `AtomicAgent[InputSchema, OutputSchema]`. Subject-specific Marker/Reviewer pairs are selected by a router. Learning loop: teacher corrections → nightly Reflection agent → rubric notes/exemplar cases injected at runtime via atomic-agents Context Providers. Speed loop: SHA-256 content-hash extraction cache + hook-based metrics.

**Tech Stack:** Python 3.12+ (uv-managed), atomic-agents 2.10.x, instructor 1.14.5, pydantic v2, SQLite (stdlib), pytest.

**Design doc:** `docs/plans/2026-09-04-smart-marking-system-design.md`

---

### Task 0: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `.gitignore`
- Create (empty `__init__.py`): `src/sms/`, `src/sms/schemas/`, `src/sms/agents/`, `src/sms/pipeline/`, `src/sms/memory/`, `src/sms/subjects/`, `src/sms/eval/`, `src/sms/learning/`, `tests/`, `tests/unit/`, `tests/integration/`

**Step 1: Create `pyproject.toml`**

```toml
[project]
name = "sms"
version = "0.1.0"
description = "Smart Marking System: agent-based marking, review and feedback on student scripts"
requires-python = ">=3.12"
dependencies = [
    "atomic-agents>=2.10.0,<3.0.0",
    "openai>=1.99.0",
]

[project.scripts]
sms = "sms.cli:main"

[dependency-groups]
dev = ["pytest>=8.0.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sms"]
```

**Step 2: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
*.sqlite3
*.egg-info/
dist/
.pytest_cache/
data/
.env
```

**Step 3: Create the empty `__init__.py` files** for each directory listed above.

**Step 4: Verify install resolves**

Run: `uv sync`
Expected: `uv.lock` created; atomic-agents installed.

**Step 5: Commit**

```bash
git add -A && git commit -m "chore: scaffold sms package with uv"
```

---

### Task 1: Core schemas

**Files:**
- Create: `src/sms/schemas/extraction.py`, `src/sms/schemas/marking.py`, `src/sms/schemas/feedback.py`, `src/sms/schemas/reflection.py`
- Test: `tests/unit/test_schemas.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_schemas.py
import pytest

from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.marking import MarkedQuestion, ReviewVerdict
from sms.schemas.feedback import FeedbackReport
from sms.schemas.reflection import ReflectionUpdate


def test_extracted_question_confidence_bounds():
    with pytest.raises(ValueError):
        ExtractedQuestion(q_id="q1", transcribed_answer="x=3", confidence=1.5)


def test_marked_question_fields():
    mq = MarkedQuestion(q_id="q1", criterion_scores=[1, 2], total=3, confidence=0.8, rationale="ok")
    assert mq.total == 3


def test_review_verdict_enum():
    assert ReviewVerdict.APPROVE.value == "APPROVE"
    assert ReviewVerdict.ADJUST.value == "ADJUST"
    assert ReviewVerdict.ESCALATE.value == "ESCALATE"


def test_schema_docstrings_present():
    for schema in (ExtractedScript, FeedbackReport, ReflectionUpdate):
        assert schema.__doc__ and schema.__doc__.strip()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sms.schemas'`

**Step 3: Write the schemas**

`src/sms/schemas/extraction.py`:

```python
from typing import List

import instructor
from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema


class ExtractionInput(BaseIOSchema):
    """Input for the Extractor agent: script images and assignment context."""

    assignment_context: str = Field(..., description="Subject, level, question count of the assignment")
    images: List[instructor.Image] = Field(..., description="Script pages as images")


class ExtractedQuestion(BaseModel):
    q_id: str = Field(..., description="Question identifier, e.g. 'q1'")
    transcribed_answer: str = Field(..., description="Student's transcribed answer")
    workings: str = Field(default="", description="Transcribed working steps, if any")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Transcription confidence 0-1")
    needs_human_transcription: bool = Field(default=False, description="True if illegible")


class ExtractedScript(BaseIOSchema):
    """Extractor output: per-question transcription of a student script."""

    questions: List[ExtractedQuestion] = Field(..., description="Transcribed questions")
```

`src/sms/schemas/marking.py`:

```python
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema

from sms.schemas.extraction import ExtractedScript


class RubricCriterion(BaseModel):
    id: str = Field(..., description="Criterion identifier, e.g. 'c1'")
    description: str = Field(..., description="What the criterion assesses")
    max_score: int = Field(..., ge=0, description="Maximum marks for this criterion")


class Rubric(BaseModel):
    criterion_defs: List[RubricCriterion] = Field(..., description="Criteria for one assignment")


class MarkingInput(BaseIOSchema):
    """Input to the Marker agent: extraction plus rubric."""

    extracted: ExtractedScript = Field(..., description="Extractor output")
    rubric: Rubric = Field(..., description="Marking criteria for the assignment")
    assignment_context: str = Field(..., description="Subject/level context")


class MarkedQuestion(BaseModel):
    q_id: str = Field(..., description="Question identifier")
    criterion_scores: List[int] = Field(..., description="Score per rubric criterion, same length as rubric")
    total: int = Field(..., description="Sum of criterion scores")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Marking confidence 0-1")
    rationale: str = Field(..., description="Why these marks were awarded")
    evidence: str = Field(default="", description="Quoted student text supporting the mark")


class MarkedScript(BaseIOSchema):
    """Marker output: marks per question with rationale and confidence."""

    marks: List[MarkedQuestion] = Field(..., description="Marks per question")


class ReviewInput(BaseIOSchema):
    """Input to the Reviewer agent: extraction + marks + rubric (marker rationale stripped)."""

    extracted: ExtractedScript = Field(..., description="Extractor output")
    marks: MarkedScript = Field(..., description="Marker output with rationale hidden")
    rubric: Rubric = Field(..., description="Marking criteria")
    assignment_context: str = Field(..., description="Subject/level context")


class ReviewVerdict(str, Enum):
    APPROVE = "APPROVE"
    ADJUST = "ADJUST"
    ESCALATE = "ESCALATE"


class ReviewVerdictItem(BaseModel):
    q_id: str = Field(..., description="Question identifier")
    verdict: ReviewVerdict = Field(..., description="APPROVE, ADJUST, or ESCALATE")
    adjusted_criterion_scores: Optional[List[int]] = Field(default=None, description="New scores if ADJUST")
    adjusted_total: Optional[int] = Field(default=None, description="New total if ADJUST")
    reviewer_note: str = Field(default="", description="Reviewer's reasoning")


class ReviewedScript(BaseIOSchema):
    """Reviewer output: per-question verdicts and final marks."""

    verdicts: List[ReviewVerdictItem] = Field(..., description="Per-question verdicts")
    final_marks: List[MarkedQuestion] = Field(..., description="Merged final marks")
    disagreement_flags: List[str] = Field(default_factory=list, description="q_ids with disagreements")
```

`src/sms/schemas/feedback.py`:

```python
from typing import List, Optional

from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema

from sms.schemas.marking import MarkedScript, ReviewedScript


class FeedbackInput(BaseIOSchema):
    """Input to the Feedback agent: reviewed script plus final marks."""

    reviewed: ReviewedScript = Field(..., description="Reviewer output")
    final_marks: MarkedScript = Field(..., description="Merged final marks")
    final_result_set: bool = Field(..., description="True if marks are final (no escalation pending)")
    student_context: Optional[str] = Field(default=None, description="Student name/context if known")


class PerQuestionComment(BaseModel):
    q_id: str = Field(..., description="Question identifier")
    comment: str = Field(..., description="Feedback for this question")
    suggested_action: str = Field(..., description="What the student should practise next")


class FeedbackReport(BaseIOSchema):
    """Student-facing feedback report."""

    summary: str = Field(..., description="Two or three sentence overview")
    strengths: List[str] = Field(..., description="Concrete strengths demonstrated")
    per_question_comments: List[PerQuestionComment] = Field(..., description="Comment per question")
    improvement_plan: List[str] = Field(..., description="3-5 actionable practice areas")
    next_steps: List[str] = Field(..., description="Concrete next actions for the student")
```

`src/sms/schemas/reflection.py`:

```python
from typing import List

from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema


class RubricNote(BaseModel):
    subject: str = Field(..., description="Subject this note applies to")
    note: str = Field(..., description="General rule distilled from corrections")
    source_run_ids: List[str] = Field(default_factory=list, description="Runs that motivated this note")


class ExemplarCase(BaseModel):
    subject: str = Field(..., description="Subject")
    topic: str = Field(..., description="Topic, e.g. 'quadratic equations'")
    q_id: str = Field(..., description="Question identifier")
    answer_text: str = Field(..., description="The student answer that scored well")
    awarded: int = Field(..., ge=0, description="Marks awarded")
    max_score: int = Field(..., ge=0, description="Maximum marks for the question")
    why_it_matters: str = Field(..., description="What makes this answer worth copying")


class CorrectionRow(BaseModel):
    run_id: str = Field(..., description="Marking run id")
    q_id: str = Field(..., description="Question identifier")
    subject: str = Field(..., description="Subject")
    rubric_json: str = Field(..., description="Rubric at time of marking, as JSON")
    extracted_answer: str = Field(..., description="Transcribed student answer")
    agent_mark: int = Field(..., description="What the agent awarded")
    teacher_mark: int = Field(..., description="What the teacher awarded")
    reason: str = Field(default="", description="Teacher's reason for the correction")


class ReflectionInput(BaseIOSchema):
    """Input for the Reflection agent: recent teacher corrections."""

    corrections: List[CorrectionRow] = Field(..., description="Recent corrections where agent != teacher")


class ReflectionUpdate(BaseIOSchema):
    """Nightly reflection output: distilled rubric notes and exemplar cases."""

    rubric_notes: List[RubricNote] = Field(..., description="Clarifications to add to rubric context")
    exemplar_cases: List[ExemplarCase] = Field(..., description="Good marked-answer examples per topic")
    prompt_tweaks: List[str] = Field(default_factory=list, description="Suggested prompt adjustments")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_schemas.py -v`
Expected: 4 PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: core pipeline schemas"
```

---

### Task 2: Memory layer (SQLite + content-hash cache)

**Files:**
- Create: `src/sms/memory/db.py`, `src/sms/memory/extraction_cache.py`
- Test: `tests/unit/test_memory.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_memory.py
from sms.memory.db import Database
from sms.memory.extraction_cache import ExtractionCache


def test_database_creates_tables(tmp_path):
    db = Database(path=str(tmp_path / "sms.db"))
    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"marking_runs", "teacher_corrections", "rubric_notes", "exemplar_cases",
            "extraction_cache", "agent_metrics", "teacher_queue"} <= tables


def test_extraction_cache_roundtrip(tmp_path):
    db = Database(path=str(tmp_path / "sms.db"))
    cache = ExtractionCache(db)
    extracted = {"questions": [{"q_id": "q1", "transcribed_answer": "x=3",
                                "workings": "", "confidence": 0.9,
                                "needs_human_transcription": False}]}
    cache.put(hash_="abc123", subject="math", extracted=extracted)
    hit = cache.get(hash_="abc123", subject="math")
    assert hit["questions"][0]["transcribed_answer"] == "x=3"
    assert cache.get(hash_="abc123", subject="language") is None
    assert cache.get(hash_="nope", subject="math") is None


def test_extraction_cache_hash(tmp_path):
    db = Database(path=str(tmp_path / "sms.db"))
    cache = ExtractionCache(db)
    h1 = cache.hash_image(b"img-bytes")
    h2 = cache.hash_image(b"img-bytes")
    h3 = cache.hash_image(b"other")
    assert h1 == h2 and h1 != h3 and len(h1) == 64
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_memory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sms.memory'`

**Step 3: Write `src/sms/memory/db.py`**

```python
import sqlite3
from typing import Any, Dict, List, Tuple


class Database:
    """Thin sqlite3 wrapper with schema bootstrapping for sms tables."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS marking_runs (
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
    CREATE TABLE IF NOT EXISTS teacher_corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        q_id TEXT NOT NULL,
        agent_mark INTEGER,
        teacher_mark INTEGER,
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS rubric_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        note TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        source_run_ids_json TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS exemplar_cases (
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
    CREATE TABLE IF NOT EXISTS extraction_cache (
        hash TEXT NOT NULL,
        subject TEXT NOT NULL,
        schema_version INTEGER NOT NULL DEFAULT 1,
        extracted_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (hash, subject, schema_version)
    );
    CREATE TABLE IF NOT EXISTS agent_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        stage TEXT NOT NULL,
        agent_role TEXT NOT NULL,
        latency_ms INTEGER NOT NULL,
        tokens_in INTEGER NOT NULL,
        tokens_out INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS teacher_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        q_id TEXT NOT NULL,
        reason TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """

    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()

    def execute(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def query(self, sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
```

**Step 4: Write `src/sms/memory/extraction_cache.py`**

```python
import hashlib
import json
from typing import Any, Dict, Optional

from sms.memory.db import Database


class ExtractionCache:
    """Content-hash cache: SHA-256(image bytes) -> cached ExtractedScript JSON.

    Keyed by hash + subject because extraction prompts and question
    segmentation differ per subject.
    """

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def hash_image(image_bytes: bytes) -> str:
        return hashlib.sha256(image_bytes).hexdigest()

    def get(self, hash_: str, subject: str) -> Optional[Dict[str, Any]]:
        row = self.db.query(
            "SELECT extracted_json FROM extraction_cache WHERE hash = ? AND subject = ? AND schema_version = 1",
            (hash_, subject),
        )
        if not row:
            return None
        return json.loads(row[0]["extracted_json"])

    def put(self, hash_: str, subject: str, extracted: Dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO extraction_cache (hash, subject, schema_version, extracted_json) "
            "VALUES (?, ?, 1, ?)",
            (hash_, subject, json.dumps(extracted)),
        )
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_memory.py -v`
Expected: 3 PASS

**Step 6: Commit**

```bash
git add -A && git commit -m "feat: memory layer with extraction cache"
```

---

### Task 3: Context providers (learning injection)

**Files:**
- Create: `src/sms/memory/providers.py`
- Test: `tests/unit/test_providers.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_providers.py
from sms.memory.db import Database
from sms.memory.providers import ExemplarCasesProvider, RubricNotesProvider


def test_rubric_notes_provider_injects_active_notes_only(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    db.execute(
        "INSERT INTO rubric_notes (subject, note, status) VALUES (?, ?, ?)",
        ("math", "State units in final answers.", "active"),
    )
    db.execute(
        "INSERT INTO rubric_notes (subject, note, status) VALUES (?, ?, ?)",
        ("math", "Draft note not shown.", "draft"),
    )
    provider = RubricNotesProvider(db, subject="math")
    info = provider.get_info()
    assert "State units" in info
    assert "Draft note" not in info


def test_rubric_notes_provider_empty(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    provider = RubricNotesProvider(db, subject="math")
    assert provider.get_info() == ""


def test_exemplar_cases_provider_formats_cases(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    db.execute(
        "INSERT INTO exemplar_cases (subject, topic, q_id, answer_text, awarded, max_score, why_it_matters, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("math", "quadratic equations", "q1", "x = 3 or x = -2, with steps", 5, 5, "Full method marks", "active"),
    )
    provider = ExemplarCasesProvider(db, subject="math")
    info = provider.get_info()
    assert "quadratic" in info
    assert "5/5" in info
    assert "Full method marks" in info
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_providers.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write `src/sms/memory/providers.py`**

```python
from atomic_agents.context import BaseDynamicContextProvider

from sms.memory.db import Database


class RubricNotesProvider(BaseDynamicContextProvider):
    """Injects active learned rubric notes for a subject into the system prompt."""

    def __init__(self, db: Database, subject: str, limit: int = 5):
        super().__init__(title="Rubric Notes (learned)")
        self.db = db
        self.subject = subject
        self.limit = limit

    def get_info(self) -> str:
        rows = self.db.query(
            "SELECT note FROM rubric_notes WHERE subject = ? AND status = 'active' ORDER BY id DESC LIMIT ?",
            (self.subject, self.limit),
        )
        if not rows:
            return ""
        return "\n".join(f"- {r['note']}" for r in rows)


class ExemplarCasesProvider(BaseDynamicContextProvider):
    """Injects recent active exemplar cases for a subject as few-shot context."""

    def __init__(self, db: Database, subject: str, limit: int = 5):
        super().__init__(title="Exemplar Cases (learned)")
        self.db = db
        self.subject = subject
        self.limit = limit

    def get_info(self) -> str:
        rows = self.db.query(
            "SELECT topic, q_id, answer_text, awarded, max_score, why_it_matters "
            "FROM exemplar_cases WHERE subject = ? AND status = 'active' ORDER BY id DESC LIMIT ?",
            (self.subject, self.limit),
        )
        if not rows:
            return ""
        return "\n".join(
            f"- [{r['topic']}] {r['answer_text']}: {r['awarded']}/{r['max_score']} ({r['why_it_matters']})"
            for r in rows
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_providers.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: rubric notes and exemplar cases context providers"
```

---

### Task 4: Subject prompt modules + router

**Files:**
- Create: `src/sms/subjects/math/prompt.py` (+ `src/sms/subjects/math/__init__.py`)
- Create: `src/sms/subjects/language/prompt.py` (+ `__init__.py`) — prompt data only, no factories
- Create: `src/sms/subjects/science/prompt.py` (+ `__init__.py`) — prompt data only
- Create: `src/sms/pipeline/router.py`
- Test: `tests/unit/test_router.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_router.py
import pytest

from sms.pipeline.router import SubjectRouter


def test_router_resolves_known_subjects():
    router = SubjectRouter()
    assert router.resolve("math") == "math"
    assert router.resolve(" Math ") == "math"


def test_router_rejects_unknown_subject():
    router = SubjectRouter()
    with pytest.raises(KeyError):
        router.resolve("fiction")


def test_router_returns_math_prompt_config():
    router = SubjectRouter()
    cfg = router.marker_prompt_config("math")
    assert cfg["background"]
    assert cfg["steps"]
    assert cfg["output_instructions"]
    assert cfg["reviewer_background"]


def test_router_language_and_science_have_prompt_data():
    router = SubjectRouter()
    for subject in ("language", "science"):
        cfg = router.marker_prompt_config(subject)
        assert cfg["background"] and cfg["steps"] and cfg["output_instructions"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write `src/sms/subjects/math/prompt.py`**

```python
MARKER_BACKGROUND = [
    "You are an experienced math examiner for the given level.",
    "You award method marks for correct approach and accuracy marks for correct final answers.",
    "You apply follow-through marking where the rubric states it.",
    "You credit valid alternate methods.",
    "You are strict about units, rounding, and final-answer form when the rubric says so.",
]

MARKER_STEPS = [
    "Read the transcribed answer and workings for each question.",
    "Check each rubric criterion against the student's demonstrated work.",
    "Award 0..max per criterion based on demonstrated level.",
    "Assign a marking confidence score per question.",
    "Cite quoted evidence from the transcription for every awarded mark.",
]

MARKER_OUTPUT_INSTRUCTIONS = [
    "One MarkedQuestion per extracted question, same q_id.",
    "criterion_scores length must equal rubric criterion count.",
    "total equals sum of criterion scores.",
    "Cite evidence for every mark.",
]

REVIEWER_BACKGROUND = [
    "You are an independent senior examiner conducting a second review.",
    "You never assume the first mark is correct or incorrect.",
    "You re-derive answers independently from the transcription before comparing.",
    "You apply the same rubric strictly and uniformly.",
]

REVIEWER_STEPS = [
    "Re-derive each question's answer independently from the transcription.",
    "Compare your derivation against the marks shown.",
    "Issue APPROVE if marks match your independent assessment.",
    "Issue ADJUST with corrected scores if you are confident the marks are wrong.",
    "Issue ESCALATE if the rubric is ambiguous or the work is hard to judge.",
]

REVIEWER_OUTPUT_INSTRUCTIONS = [
    "One verdict per marked question, same q_id.",
    "ADJUST must include adjusted_criterion_scores and adjusted_total.",
    "ESCALATE for ambiguity; do not guess.",
]
```

**Step 4: Write `src/sms/subjects/language/prompt.py`**

```python
MARKER_BACKGROUND = [
    "You are an experienced language teacher marking essays and written responses.",
    "You assess content, organisation, and language mechanics as separate rubric dimensions.",
    "You reward ideas and structure over length.",
]

MARKER_STEPS = [
    "Read the transcribed response in full.",
    "Assess each rubric criterion: content relevance, organisation, language mechanics.",
    "Award 0..max per criterion based on demonstrated level.",
    "Assign a marking confidence score per question.",
    "Cite quoted evidence from the transcription for every awarded mark.",
]

MARKER_OUTPUT_INSTRUCTIONS = [
    "One MarkedQuestion per extracted question, same q_id.",
    "criterion_scores length must equal rubric criterion count.",
    "total equals sum of criterion scores.",
    "Cite evidence for every mark.",
]

REVIEWER_BACKGROUND = [
    "You are an independent senior language teacher conducting a second review.",
    "You never assume the first mark is correct or incorrect.",
    "You re-read the response against the rubric before comparing marks.",
]

REVIEWER_STEPS = [
    "Re-read the transcribed response against each rubric criterion.",
    "Compare your assessment against the marks shown.",
    "Issue APPROVE, ADJUST with corrected scores, or ESCALATE for ambiguity.",
]

REVIEWER_OUTPUT_INSTRUCTIONS = [
    "One verdict per marked question, same q_id.",
    "ADJUST must include adjusted_criterion_scores and adjusted_total.",
    "ESCALATE for ambiguity; do not guess.",
]
```

**Step 5: Write `src/sms/subjects/science/prompt.py`**

```python
MARKER_BACKGROUND = [
    "You are an experienced science examiner for the given level.",
    "You assess concept coverage, correct terminology, and application.",
    "You credit correct scientific reasoning even with minor spelling errors.",
]

MARKER_STEPS = [
    "Read the transcribed answer and workings for each question.",
    "Check each rubric criterion: concept coverage, terminology, application.",
    "Award 0..max per criterion based on demonstrated level.",
    "Assign a marking confidence score per question.",
    "Cite quoted evidence from the transcription for every awarded mark.",
]

MARKER_OUTPUT_INSTRUCTIONS = [
    "One MarkedQuestion per extracted question, same q_id.",
    "criterion_scores length must equal rubric criterion count.",
    "total equals sum of criterion scores.",
    "Cite evidence for every mark.",
]

REVIEWER_BACKGROUND = [
    "You are an independent senior science examiner conducting a second review.",
    "You never assume the first mark is correct or incorrect.",
    "You re-derive expected answers independently before comparing.",
]

REVIEWER_STEPS = [
    "Re-derive each expected answer independently from the rubric.",
    "Compare your derivation against the marks shown.",
    "Issue APPROVE, ADJUST with corrected scores, or ESCALATE for ambiguity.",
]

REVIEWER_OUTPUT_INSTRUCTIONS = [
    "One verdict per marked question, same q_id.",
    "ADJUST must include adjusted_criterion_scores and adjusted_total.",
    "ESCALATE for ambiguity; do not guess.",
]
```

**Step 6: Write `src/sms/pipeline/router.py`**

```python
import importlib


class SubjectRouter:
    """Resolves subject names to their prompt configuration modules."""

    KNOWN_SUBJECTS = ("math", "language", "science")

    def resolve(self, subject: str) -> str:
        s = subject.strip().lower()
        if s not in self.KNOWN_SUBJECTS:
            raise KeyError(f"Unknown subject: {subject!r}. Known: {list(self.KNOWN_SUBJECTS)}")
        return s

    def marker_prompt_config(self, subject: str) -> dict:
        module = importlib.import_module(f"sms.subjects.{self.resolve(subject)}.prompt")
        return {
            "background": module.MARKER_BACKGROUND,
            "steps": module.MARKER_STEPS,
            "output_instructions": module.MARKER_OUTPUT_INSTRUCTIONS,
            "reviewer_background": module.REVIEWER_BACKGROUND,
            "reviewer_steps": module.REVIEWER_STEPS,
            "reviewer_output_instructions": module.REVIEWER_OUTPUT_INSTRUCTIONS,
        }
```

**Step 7: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_router.py -v`
Expected: 4 PASS

**Step 8: Commit**

```bash
git add -A && git commit -m "feat: subject prompt modules and SubjectRouter"
```

---

### Task 5: Agent factories

**Files:**
- Create: `src/sms/agents/extractor.py`, `src/sms/agents/marker.py`, `src/sms/agents/reviewer.py`, `src/sms/agents/feedback.py`, `src/sms/agents/reflection.py`
- Test: `tests/integration/test_agent_factories.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_agent_factories.py
import openai
import pytest

import instructor

from sms.agents.extractor import build_extractor
from sms.agents.feedback import build_feedback
from sms.agents.marker import build_marker
from sms.agents.reflection import build_reflection
from sms.agents.reviewer import build_reviewer
from sms.memory.db import Database
from sms.schemas.extraction import ExtractionInput, ExtractedScript
from sms.schemas.feedback import FeedbackInput, FeedbackReport
from sms.schemas.marking import MarkingInput, MarkedScript, ReviewInput, ReviewedScript
from sms.schemas.reflection import ReflectionInput, ReflectionUpdate


@pytest.fixture
def client():
    return instructor.from_openai(openai.OpenAI(api_key="test-key"))


def test_extractor_factory(client):
    agent = build_extractor(client=client, model="gpt-5-mini")
    assert agent.input_schema is ExtractionInput
    assert agent.output_schema is ExtractedScript


def test_marker_factory_registers_providers(client, tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    agent = build_marker(client=client, model="gpt-5-mini", subject="math", db=db)
    assert agent.input_schema is MarkingInput
    assert agent.output_schema is MarkedScript
    assert "rubric_notes" in agent.system_prompt_generator.context_providers
    assert "exemplar_cases" in agent.system_prompt_generator.context_providers


def test_reviewer_factory_registers_providers(client, tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    agent = build_reviewer(client=client, model="gpt-5-mini", subject="math", db=db)
    assert agent.input_schema is ReviewInput
    assert agent.output_schema is ReviewedScript
    assert "rubric_notes" in agent.system_prompt_generator.context_providers


def test_feedback_factory(client):
    agent = build_feedback(client=client, model="gpt-5-mini")
    assert agent.input_schema is FeedbackInput
    assert agent.output_schema is FeedbackReport


def test_reflection_factory(client):
    agent = build_reflection(client=client, model="gpt-5-mini")
    assert agent.input_schema is ReflectionInput
    assert agent.output_schema is ReflectionUpdate


def test_marker_rejects_unknown_subject(client):
    with pytest.raises(KeyError):
        build_marker(client=client, model="gpt-5-mini", subject="fiction", db=None)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_agent_factories.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write `src/sms/agents/extractor.py`**

```python
from typing import Any

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.schemas.extraction import ExtractionInput, ExtractedScript


def build_extractor(client: Any, model: str = "gpt-5-mini") -> AtomicAgent[ExtractionInput, ExtractedScript]:
    return AtomicAgent[ExtractionInput, ExtractedScript](
        config=AgentConfig(
            client=client,
            model=model,
            system_prompt_generator=SystemPromptGenerator(
                background=[
                    "You are a precise handwriting transcription specialist for student exam scripts.",
                    "You segment scripts by question number and transcribe all work, including rough work.",
                    "You flag illegible content rather than guessing.",
                ],
                steps=[
                    "Scan each image page for question numbers and answers.",
                    "Transcribe each question's answer and workings verbatim, preserving math notation.",
                    "Lower confidence for messy handwriting but still transcribe your best guess.",
                    "Flag questions you cannot read with needs_human_transcription=True.",
                ],
                output_instructions=[
                    "Return one ExtractedQuestion per question found in the script.",
                    "Preserve mathematical notation as faithfully as possible.",
                ],
            ),
        )
    )
```

**Step 4: Write `src/sms/agents/marker.py`**

```python
from typing import Any, Dict, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import BaseDynamicContextProvider, SystemPromptGenerator

from sms.memory.db import Database
from sms.memory.providers import ExemplarCasesProvider, RubricNotesProvider
from sms.pipeline.router import SubjectRouter
from sms.schemas.marking import MarkingInput, MarkedScript

_ROUTER = SubjectRouter()


def _build_providers(db: Optional[Database], subject: str) -> Dict[str, BaseDynamicContextProvider]:
    if db is None:
        return {}
    return {
        "rubric_notes": RubricNotesProvider(db, subject=subject),
        "exemplar_cases": ExemplarCasesProvider(db, subject=subject),
    }


def build_marker(
    client: Any,
    model: str = "gpt-5-mini",
    subject: str = "math",
    db: Optional[Database] = None,
) -> AtomicAgent[MarkingInput, MarkedScript]:
    cfg = _ROUTER.marker_prompt_config(subject)
    return AtomicAgent[MarkingInput, MarkedScript](
        config=AgentConfig(
            client=client,
            model=model,
            system_prompt_generator=SystemPromptGenerator(
                background=cfg["background"],
                steps=cfg["steps"],
                output_instructions=cfg["output_instructions"],
                context_providers=_build_providers(db, _ROUTER.resolve(subject)),
            ),
        )
    )
```

**Step 5: Write `src/sms/agents/reviewer.py`**

```python
from typing import Any, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.memory.db import Database
from sms.memory.providers import ExemplarCasesProvider, RubricNotesProvider
from sms.pipeline.router import SubjectRouter
from sms.schemas.marking import ReviewInput, ReviewedScript

_ROUTER = SubjectRouter()


def build_reviewer(
    client: Any,
    model: str = "gpt-5-mini",
    subject: str = "math",
    db: Optional[Database] = None,
) -> AtomicAgent[ReviewInput, ReviewedScript]:
    cfg = _ROUTER.marker_prompt_config(subject)
    providers = {}
    if db is not None:
        providers = {
            "rubric_notes": RubricNotesProvider(db, subject=subject),
            "exemplar_cases": ExemplarCasesProvider(db, subject=subject),
        }
    return AtomicAgent[ReviewInput, ReviewedScript](
        config=AgentConfig(
            client=client,
            model=model,
            system_prompt_generator=SystemPromptGenerator(
                background=cfg["reviewer_background"],
                steps=cfg["reviewer_steps"],
                output_instructions=cfg["reviewer_output_instructions"],
                context_providers=providers,
            ),
        )
    )
```

**Step 6: Write `src/sms/agents/feedback.py`**

```python
from typing import Any

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.schemas.feedback import FeedbackInput, FeedbackReport


def build_feedback(client: Any, model: str = "gpt-5-mini") -> AtomicAgent[FeedbackInput, FeedbackReport]:
    return AtomicAgent[FeedbackInput, FeedbackReport](
        config=AgentConfig(
            client=client,
            model=model,
            system_prompt_generator=SystemPromptGenerator(
                background=[
                    "You are a supportive teacher writing feedback for the student.",
                    "You never reveal internal pipeline details such as confidence scores or disagreement flags.",
                    "You balance praise and constructive criticism.",
                ],
                steps=[
                    "Review the final marks and per-question outcomes.",
                    "Identify two to four concrete strengths.",
                    "Write specific, actionable improvement comments per question.",
                    "Draft an improvement plan of three to five focused practice areas.",
                ],
                output_instructions=[
                    "Write for a student audience: encouraging, specific, jargon-free.",
                    "per_question_comments must cover every marked question.",
                    "improvement_plan entries must be actionable practice items.",
                ],
            ),
        )
    )
```

**Step 7: Write `src/sms/agents/reflection.py`**

```python
from typing import Any

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.schemas.reflection import ReflectionInput, ReflectionUpdate


def build_reflection(client: Any, model: str = "gpt-5-mini") -> AtomicAgent[ReflectionInput, ReflectionUpdate]:
    return AtomicAgent[ReflectionInput, ReflectionUpdate](
        config=AgentConfig(
            client=client,
            model=model,
            system_prompt_generator=SystemPromptGenerator(
                background=[
                    "You are a marking-standards analyst reviewing teacher corrections.",
                    "You find systematic patterns in where the marking agents disagreed with teachers.",
                    "You propose rubric clarifications and exemplar cases, never mark-level decisions.",
                ],
                steps=[
                    "Read each correction: what the agent marked, what the teacher marked, and why they differ.",
                    "Cluster corrections by pattern (e.g. units, rounding, follow-through, notation).",
                    "For each cluster with two or more supporting cases, propose a rubric note.",
                    "For each high-quality answer, propose an exemplar case with why_it_matters.",
                ],
                output_instructions=[
                    "Only propose notes backed by two or more correction cases.",
                    "Each rubric note must be a general rule, not a case-specific fix.",
                    "Each exemplar must include why_it_matters.",
                ],
            ),
        )
    )
```

**Step 8: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_agent_factories.py -v`
Expected: 6 PASS

**Step 9: Commit**

```bash
git add -A && git commit -m "feat: agent factories for all five pipeline roles"
```

---

### Task 6: Marking pipeline orchestrator

**Files:**
- Create: `src/sms/pipeline/marking_pipeline.py`
- Test: `tests/integration/test_pipeline.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_pipeline.py
import pytest

from sms.memory.db import Database
from sms.pipeline.marking_pipeline import MarkingResult, MarkingPipeline
from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.schemas.feedback import FeedbackReport, PerQuestionComment
from sms.schemas.marking import (
    MarkedQuestion,
    MarkedScript,
    ReviewVerdict,
    ReviewVerdictItem,
    ReviewedScript,
)


class StubAgent:
    """Duck-typed AtomicAgent stub: records calls, returns canned output."""

    def __init__(self, canned, input_schema, output_schema):
        self._canned = canned
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.calls = []

    def run(self, user_input):
        self.calls.append(user_input)
        return self._canned


EXTRACTED_STUB = ExtractedScript(questions=[
    ExtractedQuestion(q_id="q1", transcribed_answer="x=3", workings="3x=9", confidence=0.95),
])

MARKED_STUB = MarkedScript(marks=[
    MarkedQuestion(q_id="q1", criterion_scores=[2, 1], total=3, confidence=0.7,
                  rationale="method right", evidence="3x=9"),
])

REVIEWED_STUB = ReviewedScript(
    verdicts=[ReviewVerdictItem(q_id="q1", verdict=ReviewVerdict.APPROVE, reviewer_note="agree")],
    final_marks=[],
    disagreement_flags=[],
)

FEEDBACK_STUB = FeedbackReport(
    summary="Great work overall.",
    strengths=["Clear method"],
    per_question_comments=[PerQuestionComment(q_id="q1", comment="Good method", suggested_action="Practise rounding")],
    improvement_plan=["Rounding practice"],
    next_steps=["Retry worksheet"],
)


@pytest.fixture
def rubric():
    from sms.schemas.marking import Rubric, RubricCriterion
    return Rubric(criterion_defs=[
        RubricCriterion(id="c1", description="method", max_score=2),
        RubricCriterion(id="c2", description="accuracy", max_score=2),
    ])


def test_pipeline_runs_and_persists(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    extractor = StubAgent(EXTRACTED_STUB, None, None)
    marker = StubAgent(MARKED_STUB, None, None)
    reviewer = StubAgent(REVIEWED_STUB, None, None)
    feedback = StubAgent(FEEDBACK_STUB, None, None)
    pipeline = MarkingPipeline(db=db, extractor=extractor, marker=marker,
                               reviewer=reviewer, feedback=feedback, subject="math")
    result = pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)

    assert isinstance(result, MarkingResult)
    assert result.feedback.summary.startswith("Great")
    assert result.escalations == []
    assert result.final_marks.marks[0].q_id == "q1"
    rows = db.query("SELECT * FROM marking_runs WHERE final_status = 'complete'")
    assert rows and rows[0]["feedback_json"]


def test_pipeline_escalates_on_escalate_verdict(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    reviewed = ReviewedScript(
        verdicts=[ReviewVerdictItem(q_id="q1", verdict=ReviewVerdict.ESCALATE, reviewer_note="ambiguous rubric")],
        final_marks=[],
        disagreement_flags=["q1"],
    )
    pipeline = MarkingPipeline(
        db=db,
        extractor=StubAgent(EXTRACTED_STUB, None, None),
        marker=StubAgent(MARKED_STUB, None, None),
        reviewer=StubAgent(reviewed, None, None),
        feedback=StubAgent(FEEDBACK_STUB, None, None),
        subject="math",
    )
    result = pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    assert result.escalations == ["q1"]
    queued = db.query("SELECT * FROM teacher_queue WHERE status = 'pending'")
    assert queued and queued[0]["q_id"] == "q1"


def test_pipeline_reviewer_input_strips_marker_rationale(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    reviewer = StubAgent(REVIEWED_STUB, None, None)
    pipeline = MarkingPipeline(
        db=db,
        extractor=StubAgent(EXTRACTED_STUB, None, None),
        marker=StubAgent(MARKED_STUB, None, None),
        reviewer=reviewer,
        feedback=StubAgent(FEEDBACK_STUB, None, None),
        subject="math",
    )
    pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    review_input = reviewer.calls[0]
    assert review_input.marks.marks[0].rationale == ""
    assert review_input.marks.marks[0].criterion_scores == [2, 1]


def test_pipeline_uses_extraction_cache_on_second_run(tmp_path, rubric):
    db = Database(path=str(tmp_path / "s.db"))
    extractor = StubAgent(EXTRACTED_STUB, None, None)
    pipeline = MarkingPipeline(
        db=db,
        extractor=extractor,
        marker=StubAgent(MARKED_STUB, None, None),
        reviewer=StubAgent(REVIEWED_STUB, None, None),
        feedback=StubAgent(FEEDBACK_STUB, None, None),
        subject="math",
    )
    pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    pipeline.run(images=[b"img-bytes"], assignment_context="Math test", rubric=rubric)
    assert len(extractor.calls) == 1  # second run hit the cache
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write `src/sms/pipeline/marking_pipeline.py`**

```python
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional

from sms.memory.db import Database
from sms.memory.extraction_cache import ExtractionCache
from sms.pipeline.router import SubjectRouter
from sms.schemas.extraction import ExtractedScript
from sms.schemas.feedback import FeedbackReport
from sms.schemas.marking import (
    MarkedQuestion,
    MarkedScript,
    ReviewVerdict,
    ReviewedScript,
    Rubric,
)


@dataclass
class MarkingResult:
    run_id: str
    extracted: ExtractedScript
    final_marks: MarkedScript
    escalations: List[str] = field(default_factory=list)
    feedback: Optional[FeedbackReport] = None


class MarkingPipeline:
    """Orchestrates extract -> mark -> review -> merge -> feedback -> persist."""

    def __init__(self, db: Database, extractor: Any, marker: Any, reviewer: Any, feedback: Any, subject: str):
        self.db = db
        self.extractor = extractor
        self.marker = marker
        self.reviewer = reviewer
        self.feedback = feedback
        self.subject = SubjectRouter().resolve(subject)
        self.cache = ExtractionCache(db)

    def run(self, images: List[bytes], assignment_context: str, rubric: Rubric) -> MarkingResult:
        run_id = uuid.uuid4().hex[:12]
        image_hashes = [self.cache.hash_image(b) for b in images]
        composite_hash = self.cache.hash_image("|".join(image_hashes).encode())

        extracted = self._extract(composite_hash, images, assignment_context)
        marked = self.marker.run(self._marking_input(extracted, rubric, assignment_context))
        reviewed = self.reviewer.run(self._review_input(extracted, marked, rubric, assignment_context))
        final_marks, escalations = self._merge(marked, reviewed)
        feedback_report = self.feedback.run(
            type(self.feedback.input_schema)(
                reviewed=reviewed,
                final_marks=final_marks,
                final_result_set=not escalations,
            )
        )
        self._persist(run_id, rubric, extracted, marked, reviewed, feedback_report, escalations)
        return MarkingResult(run_id=run_id, extracted=extracted, final_marks=final_marks,
                             escalations=escalations, feedback=feedback_report)

    def _extract(self, composite_hash: str, images: List[bytes], assignment_context: str) -> ExtractedScript:
        import instructor

        cached = self.cache.get(composite_hash, self.subject)
        if cached is not None:
            return ExtractedScript.model_validate(cached)
        extracted = self.extractor.run(
            type(self.extractor.input_schema)(
                assignment_context=assignment_context,
                images=[instructor.Image.from_bytes(b) for b in images],
            )
        )
        self.cache.put(composite_hash, self.subject, extracted.model_dump())
        return extracted

    def _marking_input(self, extracted: ExtractedScript, rubric: Rubric, ctx: str) -> Any:
        return type(self.marker.input_schema)(extracted=extracted, rubric=rubric, assignment_context=ctx)

    def _review_input(self, extracted: ExtractedScript, marked: MarkedScript, rubric: Rubric, ctx: str) -> Any:
        stripped = MarkedScript(
            marks=[
                MarkedQuestion(
                    q_id=m.q_id,
                    criterion_scores=m.criterion_scores,
                    total=m.total,
                    confidence=m.confidence,
                    rationale="",  # anti-anchoring: hide marker rationale from reviewer
                    evidence="",
                )
                for m in marked.marks
            ]
        )
        return type(self.reviewer.input_schema)(extracted=extracted, marks=stripped, rubric=rubric, assignment_context=ctx)

    def _merge(self, marked: MarkedScript, reviewed: ReviewedScript):
        final: List[MarkedQuestion] = []
        escalations: List[str] = []
        by_q = {v.q_id: v for v in reviewed.verdicts}
        for m in marked.marks:
            v = by_q.get(m.q_id)
            if v is None or v.verdict == ReviewVerdict.APPROVE:
                final.append(m)
            elif v.verdict == ReviewVerdict.ADJUST and v.adjusted_criterion_scores is not None:
                final.append(
                    MarkedQuestion(
                        q_id=m.q_id,
                        criterion_scores=v.adjusted_criterion_scores,
                        total=v.adjusted_total or sum(v.adjusted_criterion_scores),
                        confidence=m.confidence,
                        rationale=m.rationale,
                        evidence=m.evidence,
                    )
                )
            else:  # ESCALATE
                escalations.append(m.q_id)
                final.append(m)
        return MarkedScript(marks=final), escalations

    def _persist(self, run_id, rubric, extracted, marked, reviewed, feedback, escalations) -> None:
        self.db.execute(
            "INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, marks_json, "
            "reviewed_json, feedback_json, final_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                "complete",
                self.subject,
                rubric.model_dump_json(),
                extracted.model_dump_json(),
                marked.model_dump_json(),
                reviewed.model_dump_json(),
                feedback.model_dump_json(),
                "escalated" if escalations else "complete",
            ),
        )
        for q_id in escalations:
            self.db.execute(
                "INSERT INTO teacher_queue (run_id, q_id, reason, status) VALUES (?, ?, ?, 'pending')",
                (run_id, q_id, "reviewer escalated"),
            )
```

Note: `instructor.Image.from_bytes` may not exist in instructor 1.14.5 — check `dir(instructor.Image)` during implementation and use the correct constructor (e.g. `instructor.Image(bytes_or_path=...)` or `from_path`). Write a tiny probe script first.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_pipeline.py -v`
Expected: 4 PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: marking pipeline orchestrator with cache, anti-anchoring, escalation"
```

---

### Task 7: Metrics recorder

**Files:**
- Create: `src/sms/memory/metrics.py`
- Test: `tests/unit/test_metrics.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_metrics.py
from sms.memory.db import Database
from sms.memory.metrics import MetricsSummary, record_run_metric


def test_record_and_summarize(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    record_run_metric(db, run_id="r1", stage="marking", agent_role="marker",
                      latency_ms=1500, tokens_in=800, tokens_out=400)
    record_run_metric(db, run_id="r2", stage="marking", agent_role="marker",
                      latency_ms=2500, tokens_in=900, tokens_out=500)
    s = MetricsSummary(db).summarize(agent_role="marker")
    assert s["count"] == 2
    assert s["mean_latency_ms"] == 2000.0
    assert s["total_tokens_in"] == 1700
    assert s["total_tokens_out"] == 900


def test_summarize_empty(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    s = MetricsSummary(db).summarize(agent_role="marker")
    assert s["count"] == 0
    assert s["mean_latency_ms"] == 0.0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write `src/sms/memory/metrics.py`**

```python
from typing import Optional

from sms.memory.db import Database


def record_run_metric(
    db: Database,
    run_id: Optional[str],
    stage: str,
    agent_role: str,
    latency_ms: int,
    tokens_in: int,
    tokens_out: int,
) -> None:
    db.execute(
        "INSERT INTO agent_metrics (run_id, stage, agent_role, latency_ms, tokens_in, tokens_out) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, stage, agent_role, latency_ms, tokens_in, tokens_out),
    )


class MetricsSummary:
    def __init__(self, db: Database):
        self.db = db

    def summarize(self, agent_role: str) -> dict:
        rows = self.db.query(
            "SELECT COUNT(*) AS count, AVG(latency_ms) AS mean_latency_ms, "
            "SUM(tokens_in) AS total_tokens_in, SUM(tokens_out) AS total_tokens_out "
            "FROM agent_metrics WHERE agent_role = ?",
            (agent_role,),
        )
        r = rows[0] if rows else {}
        return {
            "count": r.get("count") or 0,
            "mean_latency_ms": float(r.get("mean_latency_ms") or 0.0),
            "total_tokens_in": r.get("total_tokens_in") or 0,
            "total_tokens_out": r.get("total_tokens_out") or 0,
        }
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_metrics.py -v`
Expected: 2 PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: agent metrics recorder and summary"
```

---

### Task 8: Reflection job + activation

**Files:**
- Create: `src/sms/learning/__init__.py` (already created in Task 0), `src/sms/learning/reflection_job.py`
- Test: `tests/integration/test_reflection_job.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_reflection_job.py
from sms.learning.reflection_job import run_reflection, activate_note
from sms.memory.db import Database
from sms.schemas.reflection import ExemplarCase, ReflectionUpdate, RubricNote


class StubReflectionAgent:
    def __init__(self, canned):
        self._canned = canned

    def run(self, user_input):
        self.last_input = user_input
        return self._canned


UPDATE = ReflectionUpdate(
    rubric_notes=[RubricNote(subject="math", note="Always require units in final answers.", source_run_ids=["r1", "r2"])],
    exemplar_cases=[ExemplarCase(subject="math", topic="algebra", q_id="q3",
                                 answer_text="x = 3 (units: cm)", awarded=5, max_score=5,
                                 why_it_matters="States units explicitly")],
)


def _add_correction(db, run_id):
    db.execute(
        "INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason) VALUES (?, ?, ?, ?, ?)",
        (run_id, "q1", 2, 3, "student stated units; agent missed"),
    )


def test_reflection_writes_draft_rows(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    _add_correction(db, "r1")
    _add_correction(db, "r2")
    agent = StubReflectionAgent(UPDATE)
    result = run_reflection(db=db, agent=agent, subject="math", lookback_days=7)
    assert result == 1  # one note proposed
    rows = db.query("SELECT * FROM rubric_notes WHERE status = 'draft'")
    assert rows and "units" in rows[0]["note"]
    exemplars = db.query("SELECT * FROM exemplar_cases WHERE status = 'draft'")
    assert exemplars and exemplars[0]["awarded"] == 5


def test_activation_flips_status(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'note', 'draft')")
    note_id = db.query("SELECT id FROM rubric_notes")[0]["id"]
    activate_note(db, note_id)
    row = db.query("SELECT status FROM rubric_notes WHERE id = ?", (note_id,))[0]
    assert row["status"] == "active"


def test_reflection_noop_without_corrections(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    agent = StubReflectionAgent(UPDATE)
    result = run_reflection(db=db, agent=agent, subject="math", lookback_days=7)
    assert result == 0
    assert not hasattr(agent, "last_input")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_reflection_job.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write `src/sms/learning/reflection_job.py`**

```python
import json
from typing import Any, Optional

from sms.memory.db import Database
from sms.schemas.reflection import CorrectionRow, ReflectionInput


def run_reflection(db: Database, agent: Any, subject: str, lookback_days: int = 7) -> int:
    """Run the nightly reflection job over recent teacher corrections.

    Returns the number of proposed rubric notes (written as draft).
    """
    rows = db.query(
        "SELECT tc.run_id, tc.q_id, tc.agent_mark, tc.teacher_mark, tc.reason, mr.subject, "
        "mr.rubric_json, mr.extracted_json "
        "FROM teacher_corrections tc JOIN marking_runs mr ON tc.run_id = mr.run_id "
        "WHERE mr.subject = ? AND tc.created_at >= datetime('now', ?) AND tc.agent_mark != tc.teacher_mark",
        (subject, f"-{lookback_days} days"),
    )
    if not rows:
        return 0

    corrections = []
    for r in rows:
        extracted = json.loads(r["extracted_json"]) if r["extracted_json"] else {"questions": []}
        answers = {q["q_id"]: q.get("transcribed_answer", "") for q in extracted.get("questions", [])}
        corrections.append(
            CorrectionRow(
                run_id=r["run_id"],
                q_id=r["q_id"],
                subject=r["subject"],
                rubric_json=r["rubric_json"] or "{}",
                extracted_answer=answers.get(r["q_id"], ""),
                agent_mark=r["agent_mark"],
                teacher_mark=r["teacher_mark"],
                reason=r["reason"] or "",
            )
        )

    update = agent.run(ReflectionInput(corrections=corrections))

    for note in update.rubric_notes:
        db.execute(
            "INSERT INTO rubric_notes (subject, note, status, source_run_ids_json) VALUES (?, ?, 'draft', ?)",
            (note.subject, note.note, json.dumps(note.source_run_ids)),
        )
    for case in update.exemplar_cases:
        db.execute(
            "INSERT INTO exemplar_cases (subject, topic, q_id, answer_text, awarded, max_score, why_it_matters, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')",
            (case.subject, case.topic, case.q_id, case.answer_text, case.awarded, case.max_score, case.why_it_matters),
        )
    return len(update.rubric_notes)


def activate_note(db: Database, note_id: int) -> None:
    db.execute("UPDATE rubric_notes SET status = 'active' WHERE id = ?", (note_id,))


def activate_exemplar(db: Database, exemplar_id: int) -> None:
    db.execute("UPDATE exemplar_cases SET status = 'active' WHERE id = ?", (exemplar_id,))
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_reflection_job.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: reflection job with draft-to-active activation"
```

---

### Task 9: CLI

**Files:**
- Create: `src/sms/cli.py`
- Test: `tests/integration/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_cli.py
import json
import sqlite3

from sms.cli import build_parser, main


def test_cli_mark_invokes_pipeline(tmp_path, monkeypatch):
    class FakePipeline:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, images, assignment_context, rubric):
            class R:
                run_id = "abc123"
                escalations = []
                final_marks = type("M", (), {"marks": []})()
                feedback = type("F", (), {"summary": "ok", "model_dump_json": lambda self: "{}"})()
            return R()

    import sms.cli as cli_mod
    monkeypatch.setattr(cli_mod, "MarkingPipeline", FakePipeline)

    rubric_file = tmp_path / "rubric.json"
    rubric_file.write_text(json.dumps({
        "criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]
    }))
    img = tmp_path / "script.png"
    img.write_bytes(b"png")

    exit_code = main([
        "mark", str(img),
        "--subject", "math",
        "--rubric", str(rubric_file),
        "--db", str(tmp_path / "sms.db"),
    ])
    assert exit_code == 0


def test_cli_queue_lists_pending(tmp_path):
    db_path = str(tmp_path / "sms.db")
    from sms.memory.db import Database
    db = Database(path=db_path)
    db.execute("INSERT INTO teacher_queue (run_id, q_id, reason) VALUES ('r1', 'q1', 'escalated')")

    exit_code = main(["queue", "list", "--db", db_path])
    assert exit_code == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError` or ImportError

**Step 3: Write `src/sms/cli.py`**

```python
import argparse
import json
import sys
from pathlib import Path

import instructor
import openai

from sms.agents.extractor import build_extractor
from sms.agents.feedback import build_feedback
from sms.agents.marker import build_marker
from sms.agents.reflection import build_reflection
from sms.agents.reviewer import build_reviewer
from sms.learning.reflection_job import run_reflection
from sms.memory.db import Database
from sms.memory.metrics import MetricsSummary
from sms.pipeline.marking_pipeline import MarkingPipeline
from sms.schemas.marking import Rubric


def _client():
    return instructor.from_openai(openai.OpenAI())


def _mark(args) -> int:
    db = Database(path=args.db)
    rubric = Rubric.model_validate_json(Path(args.rubric).read_text())
    images = [Path(p).read_bytes() for p in args.images]
    pipeline = MarkingPipeline(
        db=db,
        extractor=build_extractor(client=_client(), model=args.model),
        marker=build_marker(client=_client(), model=args.model, subject=args.subject, db=db),
        reviewer=build_reviewer(client=_client(), model=args.model, subject=args.subject, db=db),
        feedback=build_feedback(client=_client(), model=args.model),
        subject=args.subject,
    )
    result = pipeline.run(images=images, assignment_context=args.context, rubric=rubric)
    print(json.dumps({
        "run_id": result.run_id,
        "escalations": result.escalations,
        "marks": [m.model_dump() for m in result.final_marks.marks],
        "feedback": result.feedback.model_dump() if result.feedback else None,
    }, indent=2))
    return 0


def _reflect(args) -> int:
    db = Database(path=args.db)
    agent = build_reflection(client=_client(), model=args.model)
    proposed = run_reflection(db=db, agent=agent, subject=args.subject, lookback_days=args.lookback_days)
    print(f"Proposed {proposed} rubric note(s) as draft. Review with: sms notes list --db {args.db}")
    return 0


def _evaluate(args) -> int:
    db = Database(path=args.db)
    rows = db.query("SELECT agent_mark, teacher_mark FROM teacher_corrections")
    if not rows:
        print("No corrections recorded yet.")
        return 0
    agree = sum(1 for r in rows if r["agent_mark"] == r["teacher_mark"])
    total = len(rows)
    print(f"Agreement: {agree}/{total} ({100 * agree / total:.1f}%)")
    return 0


def _stats(args) -> int:
    db = Database(path=args.db)
    for role in ("extractor", "marker", "reviewer", "feedback", "reflection"):
        s = MetricsSummary(db).summarize(agent_role=role)
        if s["count"]:
            print(f"{role}: {s['count']} runs, mean {s['mean_latency_ms']:.0f}ms, "
                  f"{s['total_tokens_in']} in / {s['total_tokens_out']} out tokens")
    return 0


def _queue_list(args) -> int:
    db = Database(path=args.db)
    rows = db.query("SELECT * FROM teacher_queue WHERE status = 'pending'")
    if not rows:
        print("Queue empty.")
        return 0
    for r in rows:
        print(f"[{r['id']}] run={r['run_id']} q={r['q_id']} reason={r['reason']}")
    return 0


def _queue_resolve(args) -> int:
    db = Database(path=args.db)
    db.execute("UPDATE teacher_queue SET status = 'resolved' WHERE id = ?", (args.queue_id,))
    db.execute(
        "INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason) "
        "SELECT run_id, q_id, NULL, ?, ? FROM teacher_queue WHERE id = ?",
        (args.teacher_mark, args.reason or "", args.queue_id),
    )
    print(f"Resolved #{args.queue_id}.")
    return 0


def _notes_list(args) -> int:
    db = Database(path=args.db)
    for r in db.query("SELECT id, subject, note, status FROM rubric_notes"):
        print(f"[{r['id']}] ({r['status']}) {r['subject']}: {r['note']}")
    return 0


def _notes_approve(args) -> int:
    db = Database(path=args.db)
    db.execute("UPDATE rubric_notes SET status = 'active' WHERE id = ?", (args.note_id,))
    print(f"Activated note #{args.note_id}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sms", description="Smart Marking System")
    parser.add_argument("--model", default="gpt-5-mini")

    sub = parser.add_subparsers(dest="command", required=True)

    p_mark = sub.add_parser("mark", help="Mark a script from images")
    p_mark.add_argument("images", nargs="+")
    p_mark.add_argument("--subject", default="math")
    p_mark.add_argument("--rubric", required=True)
    p_mark.add_argument("--context", default="Student exam script")
    p_mark.add_argument("--db", default="sms.db")
    p_mark.set_defaults(func=_mark)

    p_reflect = sub.add_parser("reflect", help="Run nightly reflection")
    p_reflect.add_argument("--subject", default="math")
    p_reflect.add_argument("--lookback", type=int, default=7)
    p_reflect.add_argument("--db", default="sms.db")
    p_reflect.set_defaults(func=_reflect)

    sub_eval = sub.add_parser("evaluate", help="Show agent-teacher agreement")
    sub_eval.add_argument("--db", default="sms.db")
    sub_eval.set_defaults(func=_evaluate)

    sub_stats = sub.add_parser("stats", help="Show agent metrics")
    sub_stats.add_argument("--db", default="sms.db")
    sub_stats.set_defaults(func=_stats)

    p_queue = sub.add_parser("queue", help="Teacher queue")
    q_sub = p_queue.add_subparsers(dest="queue_command", required=True)
    q_list = q_sub.add_parser("list")
    q_list.add_argument("--db", default="sms.db")
    q_list.set_defaults(func=_queue_list)
    q_resolve = q_sub.add_parser("resolve")
    q_resolve.add_argument("queue_id", type=int)
    q_resolve.add_argument("--teacher-mark", type=int, required=True)
    q_resolve.add_argument("--reason", default="")
    q_resolve.add_argument("--db", default="sms.db")
    q_resolve.set_defaults(func=_queue_resolve)

    p_notes = sub.add_parser("notes", help="Rubric notes")
    n_sub = p_notes.add_subparsers(dest="notes_command", required=True)
    n_list = n_sub.add_parser("list")
    n_list.add_argument("--db", default="sms.db")
    n_list.set_defaults(func=_notes_list)
    n_approve = n_sub.add_parser("approve")
    n_approve.add_argument("note_id", type=int)
    n_approve.add_argument("--db", default="sms.db")
    n_approve.set_defaults(func=_notes_approve)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

Note: the `--model`/`--db` args live at different subparser levels; verify parse behavior in tests and fix placement (e.g., move `--model` into each subcommand) if argparse errors.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_cli.py -v`
Expected: 2 PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: CLI with mark, reflect, evaluate, stats, queue, notes commands"
```

---

### Task 10: README + full test run

**Files:**
- Create: `README.md`

**Step 1: Write README** — quickstart (`uv sync`, `export OPENAI_API_KEY=...`, `sms mark script.png --subject math --rubric rubric.json`), architecture summary (link to design doc), CLI reference, learning-loop explanation (corrections → reflect → notes → approve → providers), metrics explanation.

**Step 2: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS across unit/ and integration/.

**Step 3: Commit**

```bash
git add -A && git commit -m "docs: README with quickstart and CLI reference"
```

---

## Execution Handoff

Plan saved to `docs/plans/2026-09-04-smart-marking-system-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** — Open a new session with executing-plans, batch execution with checkpoints

Which approach?

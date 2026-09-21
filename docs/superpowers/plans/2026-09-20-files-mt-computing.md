# File Submissions, MT and Computing (slice 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Submissions can be Python / Scratch / Excel files, photos, or both; two new subjects (MT with a language, Computing) each with a default model; an error is never penalised twice.

**Architecture:** Files are rendered to text by pure-Python renderers (`sms/files/`) and mapped onto the assignment's question parts by a text **segmenter** agent that emits the same `ExtractedScript` the vision extractor does, so the v2 marker → reviewer → merge → feedback → records path is unchanged. A mixed submission feeds the vision transcription into the segmenter as one more source. Per-subject model defaults sit between the assignment pin and the global Settings in `SettingsStore.for_template`. Double-penalty detection is a reviewer output consumed by `_merge`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core + Alembic (SQLite dev / Postgres prod), atomic-agents + instructor, openpyxl (already a dependency), `zipfile`/`ast` from the stdlib, React 18 + TypeScript + vitest.

**Spec:** `docs/superpowers/specs/2026-09-20-files-mt-computing-design.md`

## Global Constraints

- Renderers never execute, evaluate or recalculate anything: no `exec`/`eval`, `ast.parse` only, `openpyxl` read-only with `data_only` for cached values, no macro handling; `.xlsm` rejected.
- Accepted file types: `.py`, `.sb3`, `.xlsx`, `.zip` (container). Limits: 12 files / 2 MB per file / 60 pages / 200 KB rendered text per submission / 20 MB decompressed per zip. Error codes: `bad_file`, `too_large`, `too_many_files`, `zip_nothing_usable`, `zip_bomb` — each names the file.
- `submissions.input_kind` ∈ `pages | files | mixed`, derived from the upload, never chosen by the client.
- Subjects: `math | language | science | mt | computing`; `assignment_templates.language` ∈ `zh | ms | ta`, required when subject is `mt` (400 `bad_language`), null otherwise. Labels: **MT**, **Computing**.
- Student-facing feedback for MT is written in the assignment's language; teacher-facing text (justifications, reviewer notes, Insights) stays in English.
- Model resolution: assignment pin → subject default → global Settings. A subject default whose provider has no saved key is ignored (logged), never an error.
- No double penalisation: the deduction stays in the first listed part; later parts get the allocation restored with `why="already penalised in <first>"`; unresolvable → escalate with reason `double_penalty`.
- Photos are downsized browser-side on every upload path (long edge ≤ 2000 px, JPEG 0.85) before upload; the server's `_normalise` remains the backstop.
- Commits end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Tests never touch the network. Frontend tests query by role / accessible name.

---

## File structure

**Create**
- `src/sms/migrations/versions/0011_files_subjects_models.py` — `submission_files`, `submissions.input_kind`, `assignment_templates.language`, `subject_models`.
- `src/sms/subjects/mt/__init__.py`, `src/sms/subjects/mt/prompt.py`, `src/sms/subjects/computing/__init__.py`, `src/sms/subjects/computing/prompt.py` — v1-style prompt modules (the router imports them) plus `SUBJECT_NOTE` strings used by the v2 path.
- `src/sms/files/__init__.py`, `python.py`, `scratch.py`, `excel.py`, `render.py` (budget + dispatch), `intake.py` (classify uploads, expand zips, limits), `bulk.py` (register-number matcher).
- `src/sms/schemas/segment.py` — `TextSource`, `TextSegmentInput`.
- `src/sms/agents/text_segmenter.py` — `build_text_segmenter`.
- `src/sms/web/services/subject_models.py` — CRUD for `subject_models`.
- `tests/fixtures/files/` — `ok.py`, `bad_syntax.py`, `two_sprites.sb3`, `broken.sb3`, `formulas.xlsx` (built by a fixture script, checked in as bytes).
- `web/src/components/FilesBlock.tsx`, `web/src/components/BulkUpload.tsx`, `web/src/pages/settings/SubjectModels.tsx`.

**Modify**
- `src/sms/pipeline/router.py` (subjects), `src/sms/subjects/scheme_prompts.py` (double-penalty rule + subject notes), `src/sms/schemas/marking_v2.py` (`DoublePenalty`, `ReviewedScriptV2.double_penalties`), `src/sms/pipeline/marking_pipeline_v2.py` (`run(..., files=)`, `_segment`, `_merge` double penalties), `src/sms/schemas/feedback.py` + `src/sms/agents/feedback.py` (`feedback_language`), `src/sms/agents/extractor.py` (language note passes through `assignment_context` — no change needed there), `src/sms/worker/mark_job.py` (load files, build segmenter, pass language), `src/sms/storage.py` (`put_file`), `src/sms/web/services/submissions.py` (`create_submission` files + `input_kind`, `get_submission` files), `src/sms/web/services/class_assignments.py` (`remove_hand_in` files; bulk), `src/sms/web/services/pages_cleanup.py` (files deleted with pages), `src/sms/web/services/assignments.py` (`language`, subject validation, `effective_model` with subject default), `src/sms/providers/settings.py` (`for_template` three levels), `src/sms/web/routers/settings.py`, `src/sms/web/routers/class_assignments.py`, `src/sms/web/routers/student.py`, `src/sms/web/routers/submissions.py` (accept file types), `web/src/api/types.ts`, `web/src/lib/format.ts`, `web/src/lib/files.ts`, `web/src/components/DropZone.tsx`, `web/src/student/HandIn.tsx`, `web/src/pages/ClassAssignmentPage.tsx`, `web/src/pages/NewSubmission.tsx`, `web/src/pages/SubmissionDetail.tsx`, `web/src/pages/AssignmentEditor.tsx`, `web/src/pages/Settings.tsx`, `README.md`, `docs/setup-guide/README.md` (one paragraph).

---

### Task 1: Migration 0011, subjects `mt` and `computing`, `language` on templates

**Files:**
- Create: `src/sms/migrations/versions/0011_files_subjects_models.py`, `src/sms/subjects/mt/__init__.py`, `src/sms/subjects/mt/prompt.py`, `src/sms/subjects/computing/__init__.py`, `src/sms/subjects/computing/prompt.py`
- Modify: `src/sms/pipeline/router.py:9` (`KNOWN_SUBJECTS`), `src/sms/web/services/assignments.py` (`_validate`, template dict), `src/sms/web/services/submissions.py:35` (error text)
- Test: `tests/unit/test_router.py`, `tests/web/test_assignments_api.py`, `tests/unit/test_settings_store.py` (migration head)

**Interfaces:**
- Produces: `SubjectRouter.KNOWN_SUBJECTS == ("math", "language", "science", "mt", "computing")`; `sms.subjects.mt.prompt.LANGUAGE_NAMES = {"zh": "Chinese", "ms": "Malay", "ta": "Tamil"}`; `sms.subjects.mt.prompt.SUBJECT_NOTE: str`, `sms.subjects.computing.prompt.SUBJECT_NOTE: str`; template dict key `language: str | None`; tables `submission_files`, `subject_models`; columns `submissions.input_kind`, `assignment_templates.language`.

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_router.py (append)
def test_router_knows_mt_and_computing():
    r = SubjectRouter()
    assert r.resolve("mt") == "mt" and r.resolve("computing") == "computing"
    for s in ("mt", "computing"):
        cfg = r.marker_prompt_config(s)
        assert cfg["background"] and cfg["reviewer_steps"]

# tests/web/test_assignments_api.py (append)
def test_mt_requires_language(auth):
    body = _tpl(subject="mt")  # existing helper that builds a valid POST body
    r = auth.post("/api/assignments", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_language"
    body["language"] = "zh"
    r = auth.post("/api/assignments", json=body)
    assert r.status_code == 201 and r.json()["language"] == "zh"

def test_language_ignored_for_other_subjects(auth):
    body = _tpl(subject="math"); body["language"] = "zh"
    r = auth.post("/api/assignments", json=body)
    assert r.status_code == 201 and r.json()["language"] is None

def test_computing_is_a_subject(auth):
    r = auth.post("/api/assignments", json=_tpl(subject="computing"))
    assert r.status_code == 201 and r.json()["subject"] == "computing"
```

- [ ] **Step 2: Run** `uv run python -m pytest tests/unit/test_router.py tests/web/test_assignments_api.py -q -k "mt or computing or language"` → FAIL (`Unknown subject`).

- [ ] **Step 3: Migration**

```python
"""file submissions, MT and Computing, per-subject models

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("submissions") as b:
        b.add_column(sa.Column("input_kind", sa.Text, nullable=False, server_default="pages"))
    with op.batch_alter_table("assignment_templates") as b:
        b.add_column(sa.Column("language", sa.Text))  # zh | ms | ta, MT only
    op.create_table(
        "submission_files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),          # py | sb3 | xlsx
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("sha256", sa.Text, nullable=False),
        sa.Column("stored_path", sa.Text, nullable=False),
        sa.Column("text_rendered", sa.Text),
        sa.Column("deleted_at", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_submission_files_submission", "submission_files", ["submission_id"])
    op.create_table(
        "subject_models",
        sa.Column("subject", sa.Text, primary_key=True),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("extractor_model", sa.Text),
        sa.Column("updated_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("subject_models")
    op.drop_index("ix_submission_files_submission", table_name="submission_files")
    op.drop_table("submission_files")
    with op.batch_alter_table("assignment_templates") as b:
        b.drop_column("language")
    with op.batch_alter_table("submissions") as b:
        b.drop_column("input_kind")
```

- [ ] **Step 4: Router and prompt modules**

`src/sms/pipeline/router.py`: `KNOWN_SUBJECTS = ("math", "language", "science", "mt", "computing")`.

`src/sms/subjects/mt/prompt.py` (the six `MARKER_*` / `REVIEWER_*` lists mirror `subjects/language/prompt.py`; copy that file and change the background), plus:

```python
LANGUAGE_NAMES = {"zh": "Chinese", "ms": "Malay", "ta": "Tamil"}

MARKER_BACKGROUND = [
    "You are an experienced Mother Tongue examiner (Chinese, Malay or Tamil) marking handwritten scripts.",
    "You read the script in its own language and mark against the scheme or rubric bands exactly as written, using the scheme's vocabulary.",
    "You judge language accuracy, vocabulary range, content and organisation as the descriptors describe them, never length.",
]
# … MARKER_STEPS, MARKER_OUTPUT_INSTRUCTIONS, REVIEWER_* copied from language/prompt.py …

SUBJECT_NOTE = ("Mother Tongue script in {language}. Read it in that language; do not translate when quoting evidence. "
                "Teacher-facing justifications are written in English.")
```

`src/sms/subjects/computing/prompt.py`:

```python
MARKER_BACKGROUND = [
    "You are an experienced Computing teacher marking programs, Scratch projects and spreadsheets by reading them.",
    "You judge correctness against the task as stated, logic and control flow, use of the required constructs, data handling and clarity.",
    "You never run code and never assert runtime behaviour you cannot see in the source; when a scheme row can only be "
    "verified by running the program, say so, mark what is verifiable and lower your confidence.",
    "In spreadsheets the formulas are the work and the cached values are the evidence; in Scratch the block structure is the work.",
]
# … the other five lists copied from math/prompt.py with 'question' → 'task' wording …

SUBJECT_NOTE = ("Computing submission: sources are program files, Scratch projects and spreadsheets rendered as text, "
                "plus any handwritten pages. Cite the source and line/cell for every observation. Never claim to have run anything.")
```

- [ ] **Step 5: Assignment validation and dict** — in `src/sms/web/services/assignments.py`: `_validate` gains `language: Optional[str]`; error text at line ~78 becomes "Subject must be math, language, science, mt or computing"; when `subject == "mt"` and `language not in ("zh", "ms", "ta")` → `ApiError(400, "bad_language", "Choose the Mother Tongue language (zh, ms or ta)")`; for other subjects store `NULL`. INSERT/UPDATE include `language`; the template dict gains `"language": row["language"]`. `submissions.py:35` error text updated the same way. Also update `SELECT` in `mark_job._v2_template` to include `language` (used by Task 7) and put `"language": t["language"]` into the returned dict.

- [ ] **Step 6: Run** the tests above → PASS; full suite `uv run python -m pytest -q` green (fix the migration-head test to expect `0011`).

- [ ] **Step 7: Commit** `feat(subjects): migration 0011; MT (with language) and Computing subjects`.

---

### Task 2: File renderers — Python, Scratch, Excel, budget

**Files:**
- Create: `src/sms/files/__init__.py`, `src/sms/files/python.py`, `src/sms/files/scratch.py`, `src/sms/files/excel.py`, `src/sms/files/render.py`, `tests/fixtures/files/make_fixtures.py`, `tests/fixtures/files/{ok.py,bad_syntax.py,two_sprites.sb3,broken.sb3,formulas.xlsx}`
- Test: `tests/unit/test_files_render.py`

**Interfaces:**
- Produces: `Rendered` dataclass `{name: str, kind: str, text: str, summary: str, truncated: bool}`; `render_one(name: str, data: bytes) -> Rendered` (raises `RenderError(name, msg)`); `render_all(files: List[Tuple[str, bytes]], budget: int = 200_000) -> List[Rendered]`; `KIND_BY_EXT = {".py": "py", ".sb3": "sb3", ".xlsx": "xlsx"}`.

- [ ] **Step 1: Fixture builder** `tests/fixtures/files/make_fixtures.py` (run once, commit the outputs):

```python
import io, json, zipfile, pathlib
import openpyxl
HERE = pathlib.Path(__file__).parent
(HERE / "ok.py").write_text("def total(xs):\n    s = 0\n    for x in xs:\n        s += x\n    return s\n\nprint(total([1, 2, 3]))\n")
(HERE / "bad_syntax.py").write_text("def broken(:\n    return 1\n")
project = {"targets": [
  {"isStage": True, "name": "Stage", "variables": {"v1": ["score", 0]}, "lists": {}, "broadcasts": {"b1": "go"}, "blocks": {}, "costumes": [{}], "sounds": []},
  {"isStage": False, "name": "Cat", "variables": {}, "lists": {}, "broadcasts": {}, "costumes": [{}, {}], "sounds": [{}],
   "blocks": {
     "a": {"opcode": "event_whenflagclicked", "next": "b", "parent": None, "inputs": {}, "fields": {}, "topLevel": True},
     "b": {"opcode": "control_repeat", "next": "d", "parent": "a", "inputs": {"TIMES": [1, [6, "10"]], "SUBSTACK": [2, "c"]}, "fields": {}, "topLevel": False},
     "c": {"opcode": "motion_movesteps", "next": None, "parent": "b", "inputs": {"STEPS": [1, [4, "10"]]}, "fields": {}, "topLevel": False},
     "d": {"opcode": "event_broadcast", "next": None, "parent": "b", "inputs": {"BROADCAST_INPUT": [1, [11, "go", "b1"]]}, "fields": {}, "topLevel": False},
   }}]}
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z: z.writestr("project.json", json.dumps(project))
(HERE / "two_sprites.sb3").write_bytes(buf.getvalue())
(HERE / "broken.sb3").write_bytes(b"not a zip at all")
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Marks"
ws["A1"] = "Item"; ws["B1"] = 10; ws["B2"] = 20; ws["B3"] = 30; ws["B4"] = "=SUM(B1:B3)"
wb.defined_names["Total"] = openpyxl.workbook.defined_name.DefinedName("Total", attr_text="Marks!$B$4")
wb.save(HERE / "formulas.xlsx")
```

(openpyxl cannot write cached values, so `formulas.xlsx` has a formula with no cached value — the test asserts the `→ (not calculated)` rendering; a second fixture is not needed.)

- [ ] **Step 2: Failing tests**

```python
# tests/unit/test_files_render.py
import pathlib, pytest
from sms.files.render import render_one, render_all, RenderError

FX = pathlib.Path(__file__).parent.parent / "fixtures" / "files"

def _b(n): return (FX / n).read_bytes()

def test_python_renders_with_line_numbers_and_syntax_ok():
    r = render_one("ok.py", _b("ok.py"))
    assert r.kind == "py" and r.text.startswith("syntax: ok\n") and "   4 |         s += x" in r.text
    assert r.summary == "7 lines, syntax ok"

def test_python_syntax_error_is_noted_not_raised():
    r = render_one("bad_syntax.py", _b("bad_syntax.py"))
    assert r.text.startswith("syntax: error at line 1") and "   1 | def broken(:" in r.text

def test_scratch_blocks_become_indented_pseudo_code():
    r = render_one("two_sprites.sb3", _b("two_sprites.sb3"))
    assert "sprite Cat" in r.text and "when green flag clicked" in r.text
    assert "  repeat (10)" in r.text and "    move (10) steps" in r.text and "  broadcast [go]" in r.text
    assert "variables: score" in r.text and "costumes: 2" in r.text
    assert r.summary == "2 targets, 1 script"

def test_broken_sb3_raises_render_error():
    with pytest.raises(RenderError) as e:
        render_one("broken.sb3", _b("broken.sb3"))
    assert "broken.sb3" in str(e.value)

def test_excel_shows_formulas_values_and_names():
    r = render_one("formulas.xlsx", _b("formulas.xlsx"))
    assert "sheet Marks" in r.text and "B2 = 20" in r.text
    assert "B4 = =SUM(B1:B3) → (not calculated)" in r.text
    assert "named ranges: Total = Marks!$B$4" in r.text
    assert r.summary == "1 sheet, 5 cells, 1 formula"

def test_xlsm_rejected():
    with pytest.raises(RenderError):
        render_one("macros.xlsm", b"")

def test_budget_truncates_largest_first():
    big = ("x = 1\n" * 60_000).encode()          # ~360 KB
    out = render_all([("small.py", b"y = 2\n"), ("big.py", big)], budget=50_000)
    small, large = out[0], out[1]
    assert not small.truncated and large.truncated
    assert "… truncated:" in large.text and len(large.text) <= 50_000
```

- [ ] **Step 3: Run** → FAIL (`No module named sms.files`).

- [ ] **Step 4: Implement**

`src/sms/files/__init__.py` — empty. `src/sms/files/render.py`:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from sms.files import python as _py, scratch as _sb3, excel as _xlsx

KIND_BY_EXT = {".py": "py", ".sb3": "sb3", ".xlsx": "xlsx"}
TEXT_BUDGET = 200_000


class RenderError(ValueError):
    def __init__(self, name: str, msg: str):
        super().__init__(f"{name}: {msg}"); self.name = name; self.msg = msg


@dataclass
class Rendered:
    name: str
    kind: str
    text: str
    summary: str
    truncated: bool = False


def render_one(name: str, data: bytes) -> Rendered:
    ext = Path(name).suffix.lower()
    kind = KIND_BY_EXT.get(ext)
    if kind is None:
        raise RenderError(name, "unsupported file type (use .py, .sb3 or .xlsx)")
    fn = {"py": _py.render, "sb3": _sb3.render, "xlsx": _xlsx.render}[kind]
    try:
        text, summary = fn(data)
    except RenderError:
        raise
    except Exception as e:  # noqa: BLE001 - any parser failure is a bad file, never a crash
        raise RenderError(name, f"could not read ({e.__class__.__name__})") from e
    return Rendered(name=name, kind=kind, text=text, summary=summary)


def render_all(files: List[Tuple[str, bytes]], budget: int = TEXT_BUDGET) -> List[Rendered]:
    out = [render_one(n, b) for n, b in files]
    total = sum(len(r.text) for r in out)
    # Largest first: one huge file should not starve the small ones the marker also needs.
    for r in sorted(out, key=lambda r: -len(r.text)):
        if total <= budget:
            break
        over = total - budget
        keep = max(0, len(r.text) - over - 64)
        lines = r.text[:keep].rsplit("\n", 1)[0]
        dropped = r.text.count("\n") - lines.count("\n")
        r.text = lines + f"\n… truncated: {dropped} more lines\n"
        r.truncated = True
        total = sum(len(x.text) for x in out)
    return out
```

`src/sms/files/python.py`:

```python
import ast


def render(data: bytes):
    try:
        src = data.decode("utf-8")
    except UnicodeDecodeError:
        src = data.decode("latin-1")
    lines = src.splitlines()
    try:
        ast.parse(src)  # parse only; never compiled or executed
        head, ok = "syntax: ok", "syntax ok"
    except SyntaxError as e:
        head, ok = f"syntax: error at line {e.lineno}: {e.msg}", f"syntax error at line {e.lineno}"
    body = "\n".join(f"{i:4d} | {l}" for i, l in enumerate(lines, 1))
    return head + "\n" + body + "\n", f"{len(lines)} lines, {ok}"
```

`src/sms/files/scratch.py` (opcode table covers the common blocks; unknown opcodes print as `[opcode]`):

```python
import io, json, zipfile
from typing import Dict, List

from sms.files.render import RenderError

MAX_DECOMPRESSED = 20 * 1024 * 1024

# opcode -> template; {NAME} = input or field value
OPCODES: Dict[str, str] = {
    "event_whenflagclicked": "when green flag clicked", "event_whenkeypressed": "when [{KEY_OPTION}] key pressed",
    "event_whenthisspriteclicked": "when this sprite clicked", "event_whenbroadcastreceived": "when I receive [{BROADCAST_OPTION}]",
    "event_broadcast": "broadcast [{BROADCAST_INPUT}]", "event_broadcastandwait": "broadcast [{BROADCAST_INPUT}] and wait",
    "control_repeat": "repeat ({TIMES})", "control_forever": "forever", "control_if": "if <{CONDITION}> then",
    "control_if_else": "if <{CONDITION}> then … else", "control_wait": "wait ({DURATION}) seconds",
    "control_repeat_until": "repeat until <{CONDITION}>", "control_stop": "stop [{STOP_OPTION}]",
    "motion_movesteps": "move ({STEPS}) steps", "motion_turnright": "turn right ({DEGREES}) degrees",
    "motion_turnleft": "turn left ({DEGREES}) degrees", "motion_gotoxy": "go to x: ({X}) y: ({Y})",
    "motion_changexby": "change x by ({DX})", "motion_changeyby": "change y by ({DY})", "motion_ifonedgebounce": "if on edge, bounce",
    "looks_say": "say ({MESSAGE})", "looks_sayforsecs": "say ({MESSAGE}) for ({SECS}) seconds", "looks_switchcostumeto": "switch costume to ({COSTUME})",
    "looks_show": "show", "looks_hide": "hide", "sound_play": "start sound ({SOUND_MENU})",
    "sensing_touchingobject": "touching [{TOUCHINGOBJECTMENU}]?", "sensing_keypressed": "key [{KEY_OPTION}] pressed?", "sensing_askandwait": "ask ({QUESTION}) and wait",
    "operator_add": "({NUM1}) + ({NUM2})", "operator_subtract": "({NUM1}) - ({NUM2})", "operator_multiply": "({NUM1}) * ({NUM2})",
    "operator_divide": "({NUM1}) / ({NUM2})", "operator_lt": "({OPERAND1}) < ({OPERAND2})", "operator_gt": "({OPERAND1}) > ({OPERAND2})",
    "operator_equals": "({OPERAND1}) = ({OPERAND2})", "operator_and": "<{OPERAND1}> and <{OPERAND2}>", "operator_or": "<{OPERAND1}> or <{OPERAND2}>",
    "operator_not": "not <{OPERAND}>", "operator_random": "pick random ({FROM}) to ({TO})", "operator_join": "join ({STRING1}) ({STRING2})",
    "data_setvariableto": "set [{VARIABLE}] to ({VALUE})", "data_changevariableby": "change [{VARIABLE}] by ({VALUE})",
    "data_addtolist": "add ({ITEM}) to [{LIST}]", "data_showvariable": "show variable [{VARIABLE}]",
    "procedures_definition": "define {custom_block}", "procedures_call": "call {custom_block}",
}
SUBSTACKS = ("SUBSTACK", "SUBSTACK2")


def _value(blocks, v) -> str:
    """An input is [shadow, value]; value is a block id (string) or a literal array [type, text, ...]."""
    if isinstance(v, list) and len(v) >= 2:
        inner = v[1]
        if isinstance(inner, list) and len(inner) >= 2:
            return str(inner[1])
        if isinstance(inner, str) and inner in blocks:
            return _render_block(blocks, inner, 0, inline=True).strip()
    return "?"


def _render_block(blocks, bid, depth, inline=False) -> str:
    b = blocks[bid]
    vals = {k: _value(blocks, v) for k, v in (b.get("inputs") or {}).items() if k not in SUBSTACKS}
    vals.update({k: (v[0] if isinstance(v, list) and v else str(v)) for k, v in (b.get("fields") or {}).items()})
    if b.get("opcode") in ("procedures_definition", "procedures_call"):
        vals["custom_block"] = (b.get("mutation") or {}).get("proccode", "?")
    tmpl = OPCODES.get(b.get("opcode"), f"[{b.get('opcode')}]")
    try:
        line = tmpl.format(**{k: vals.get(k, "?") for k in _names(tmpl)})
    except (KeyError, IndexError):
        line = tmpl
    if inline:
        return line
    out = ["  " * depth + line]
    for key in SUBSTACKS:
        sub = (b.get("inputs") or {}).get(key)
        if sub and isinstance(sub, list) and len(sub) >= 2 and isinstance(sub[1], str) and sub[1] in blocks:
            if key == "SUBSTACK2":
                out.append("  " * depth + "else")
            out.extend(_render_chain(blocks, sub[1], depth + 1))
    return "\n".join(out)


def _names(tmpl: str) -> List[str]:
    import string
    return [f for _, f, _, _ in string.Formatter().parse(tmpl) if f]


def _render_chain(blocks, bid, depth) -> List[str]:
    out, seen = [], set()
    while bid and bid in blocks and bid not in seen:
        seen.add(bid)
        out.append(_render_block(blocks, bid, depth))
        bid = blocks[bid].get("next")
    return out


def render(data: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_DECOMPRESSED:
                raise RenderError("project", "zip expands past 20 MB")
            project = json.loads(z.read("project.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as e:
        raise RenderError("project", "not a Scratch 3 project (.sb3)") from e
    lines, scripts = [], 0
    for t in project.get("targets", []):
        name = t.get("name", "?")
        lines.append(("stage " if t.get("isStage") else "sprite ") + name)
        for label, key in (("variables", "variables"), ("lists", "lists"), ("broadcasts", "broadcasts")):
            names = [v[0] if isinstance(v, list) else str(v) for v in (t.get(key) or {}).values()]
            if names:
                lines.append(f"  {label}: " + ", ".join(names))
        lines.append(f"  costumes: {len(t.get('costumes') or [])}, sounds: {len(t.get('sounds') or [])}")
        blocks = t.get("blocks") or {}
        tops = [bid for bid, b in blocks.items() if isinstance(b, dict) and b.get("topLevel") and b.get("opcode")]
        for bid in tops:
            scripts += 1
            lines.append("")
            lines.extend("  " + l for l in _render_chain(blocks, bid, 0))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", f"{len(project.get('targets', []))} targets, {scripts} script{'s' if scripts != 1 else ''}"
```

`src/sms/files/excel.py`:

```python
import io
import openpyxl

from sms.files.render import RenderError


def render(data: bytes):
    if not data[:2] == b"PK":
        raise RenderError("workbook", "not an .xlsx workbook")
    try:
        wb_f = openpyxl.load_workbook(io.BytesIO(data), read_only=False, data_only=False, keep_vba=False)
        wb_v = openpyxl.load_workbook(io.BytesIO(data), read_only=False, data_only=True)
    except Exception as e:  # noqa: BLE001
        raise RenderError("workbook", "could not open the workbook") from e
    lines, cells, formulas = [], 0, 0
    for ws in wb_f.worksheets:
        wv = wb_v[ws.title]
        lines.append(f"sheet {ws.title} ({ws.max_row} rows × {ws.max_column} cols)")
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    continue
                cells += 1
                v = c.value
                if isinstance(v, str) and v.startswith("="):
                    formulas += 1
                    cached = wv[c.coordinate].value
                    lines.append(f"  {c.coordinate} = {v} → {cached if cached is not None else '(not calculated)'}")
                else:
                    lines.append(f"  {c.coordinate} = {v}")
        if ws.merged_cells.ranges:
            lines.append("  merged: " + ", ".join(str(r) for r in ws.merged_cells.ranges))
        charts = getattr(ws, "_charts", [])
        if charts:
            lines.append(f"  charts: {len(charts)} (" + ", ".join(type(ch).__name__ for ch in charts) + ")")
        dv = getattr(ws.data_validations, "dataValidation", []) if getattr(ws, "data_validations", None) else []
        cf = len(ws.conditional_formatting) if getattr(ws, "conditional_formatting", None) else 0
        if dv or cf:
            lines.append(f"  data validations: {len(dv)}, conditional formats: {cf}")
        lines.append("")
    names = [(n, d.attr_text) for n, d in wb_f.defined_names.items()] if hasattr(wb_f.defined_names, "items") else []
    if names:
        lines.append("named ranges: " + ", ".join(f"{n} = {t}" for n, t in names))
    n_sheets = len(wb_f.worksheets)
    return "\n".join(lines).rstrip() + "\n", f"{n_sheets} sheet{'s' if n_sheets != 1 else ''}, {cells} cells, {formulas} formula{'s' if formulas != 1 else ''}"
```

Also in `render_one`: `.xlsm` (and any other extension) falls to `RenderError("unsupported file type …")` — that satisfies `test_xlsm_rejected`.

- [ ] **Step 5: Run** `uv run python -m pytest tests/unit/test_files_render.py -q` → PASS (adjust the `named ranges` line to whatever openpyxl 3.1 exposes — `wb.defined_names` is a dict-like in 3.1; assert on `"Total = Marks!$B$4"`).

- [ ] **Step 6: Commit** `feat(files): render Python, Scratch and Excel files to text (read-only)`.

---
### Task 3: Upload intake — files stored on the submission, `input_kind`, detail and cleanup

**Files:**
- Create: `src/sms/files/intake.py`
- Modify: `src/sms/storage.py` (`PageStorage.put_file`), `src/sms/web/services/submissions.py` (`create_submission`, `get_submission`), `src/sms/web/services/class_assignments.py:153-175` (`remove_hand_in`), `src/sms/web/services/pages_cleanup.py:67-77`, `src/sms/web/services/student.py` (`_HAND_IN_MESSAGES`), `src/sms/web/routers/student.py:72-90` (count cap message)
- Test: `tests/unit/test_files_intake.py`, `tests/web/test_submissions_api.py`, `tests/web/test_class_assignments_api.py`, `tests/unit/test_pages_cleanup.py`

**Interfaces:**
- Consumes: `KIND_BY_EXT` (Task 2), `IMAGE_EXTS`/`PDF_EXTS` from `sms.storage`.
- Produces: `Intake{pages: List[Tuple[str, bytes]], files: List[Tuple[str, bytes]], ignored: List[str]}`; `classify_uploads(files, *, max_files=12, max_file_bytes=2*1024*1024) -> Intake` raising `IntakeError(code, name, message)`; `input_kind(intake) -> str`; `PageStorage.put_file(data: bytes, ext: str) -> Tuple[str, str]` (sha256, relative path `files/<aa>/<sha><ext>`); `create_submission` accepts files and writes `submissions.input_kind` + `submission_files` rows; `get_submission()` returns `input_kind` and `files: [{id, name, kind, size, text_rendered, deleted, matched}]`; `delete_submission_pages` also deletes files.

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_files_intake.py
import io, zipfile, pytest
from sms.files.intake import classify_uploads, input_kind, IntakeError

def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in entries: z.writestr(n, b)
    return buf.getvalue()

def test_pages_only():
    it = classify_uploads([("p1.jpg", b"x"), ("p2.pdf", b"y")])
    assert [n for n, _ in it.pages] == ["p1.jpg", "p2.pdf"] and it.files == [] and input_kind(it) == "pages"

def test_files_and_pages_are_mixed():
    it = classify_uploads([("a.py", b"print(1)"), ("scan.png", b"z")])
    assert input_kind(it) == "mixed" and [n for n, _ in it.files] == ["a.py"]

def test_zip_is_expanded_and_junk_listed():
    z = _zip([("prog.py", b"x=1"), ("notes.txt", b"hi"), ("__MACOSX/._prog.py", b"junk"), ("sheet.xlsx", b"PK..")])
    it = classify_uploads([("work.zip", z)])
    assert sorted(n for n, _ in it.files) == ["prog.py", "sheet.xlsx"] and it.ignored == ["notes.txt"] and input_kind(it) == "files"

def test_zip_with_nothing_usable_rejected():
    with pytest.raises(IntakeError) as e:
        classify_uploads([("work.zip", _zip([("a.txt", b"")]))])
    assert e.value.code == "zip_nothing_usable" and "work.zip" in e.value.message

def test_bad_type_too_large_too_many():
    with pytest.raises(IntakeError) as e: classify_uploads([("a.exe", b"")])
    assert e.value.code == "bad_file" and "a.exe" in e.value.message
    with pytest.raises(IntakeError) as e: classify_uploads([("big.py", b"x" * (2 * 1024 * 1024 + 1))])
    assert e.value.code == "too_large"
    with pytest.raises(IntakeError) as e: classify_uploads([(f"f{i}.py", b"x") for i in range(13)])
    assert e.value.code == "too_many_files"

def test_zip_bomb_cap():
    big = _zip([("a.py", b"0" * (21 * 1024 * 1024))])
    with pytest.raises(IntakeError) as e: classify_uploads([("bomb.zip", big)])
    assert e.value.code == "zip_bomb"
```

```python
# tests/web/test_submissions_api.py (append; `_tpl_v2(auth)` = existing helper creating a mark-scheme template)
def test_upload_python_file_creates_files_submission(auth):
    tid = _tpl_v2(auth)
    r = auth.post("/api/submissions", data={"label": "S1", "subject": "math", "context": "", "rubric": "{}", "assignment_id": str(tid)},
                  files=[("files", ("prog.py", b"print(1)\n", "text/x-python"))])
    assert r.status_code == 202
    d = auth.get(f"/api/submissions/{r.json()['id']}").json()
    assert d["input_kind"] == "files" and d["pages"] == [] and [f["name"] for f in d["files"]] == ["prog.py"]
    assert d["files"][0]["kind"] == "py" and d["files"][0]["size"] == 9 and d["files"][0]["text_rendered"] is None

def test_mixed_upload(auth, png_bytes):
    tid = _tpl_v2(auth)
    r = auth.post("/api/submissions", data={"label": "S2", "subject": "math", "context": "", "rubric": "{}", "assignment_id": str(tid)},
                  files=[("files", ("p.png", png_bytes, "image/png")), ("files", ("s.xlsx", b"PK\x03\x04", "application/octet-stream"))])
    assert r.status_code == 202
    d = auth.get(f"/api/submissions/{r.json()['id']}").json()
    assert d["input_kind"] == "mixed" and len(d["pages"]) == 1 and len(d["files"]) == 1

def test_files_need_a_scheme_assignment(auth):
    r = auth.post("/api/submissions", data={"label": "S3", "subject": "math", "context": "", "rubric": "{}"},
                  files=[("files", ("prog.py", b"x=1", "text/x-python"))])
    assert r.status_code == 400 and r.json()["error"]["code"] == "files_need_scheme"

def test_bad_file_named(auth):
    tid = _tpl_v2(auth)
    r = auth.post("/api/submissions", data={"label": "S4", "subject": "math", "context": "", "rubric": "{}", "assignment_id": str(tid)},
                  files=[("files", ("virus.exe", b"x", "application/octet-stream"))])
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_file" and "virus.exe" in r.json()["error"]["message"]
```

```python
# tests/unit/test_pages_cleanup.py (append) — seed a submission with one page and one file via create_submission,
# run delete_submission_pages, assert the file row has deleted_at set, its stored path is gone from disk, and
# get_submission reports files[0]["deleted"] is True while text_rendered survives when set.
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: `src/sms/files/intake.py`**

```python
import io, zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from sms.files.render import KIND_BY_EXT
from sms.storage import IMAGE_EXTS, PDF_EXTS

MAX_FILES = 12
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ZIP_DECOMPRESSED = 20 * 1024 * 1024
PAGE_EXTS = set(IMAGE_EXTS) | set(PDF_EXTS)
FILE_EXTS = set(KIND_BY_EXT)


class IntakeError(ValueError):
    def __init__(self, code: str, name: str, message: str):
        super().__init__(message); self.code = code; self.name = name; self.message = message


@dataclass
class Intake:
    pages: List[Tuple[str, bytes]] = field(default_factory=list)
    files: List[Tuple[str, bytes]] = field(default_factory=list)
    ignored: List[str] = field(default_factory=list)


def _junk(name: str) -> bool:
    parts = Path(name).parts
    return name.endswith("/") or any(p.startswith("__MACOSX") or p.startswith(".") for p in parts)


def _expand_zip(name: str, data: bytes, into: Intake) -> None:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise IntakeError("bad_file", name, f"{name} is not a zip file")
    with z:
        if sum(i.file_size for i in z.infolist()) > MAX_ZIP_DECOMPRESSED:
            raise IntakeError("zip_bomb", name, f"{name} expands past 20 MB")
        usable = 0
        for info in z.infolist():
            if info.is_dir() or _junk(info.filename):
                continue
            inner = Path(info.filename).name
            ext = Path(inner).suffix.lower()
            if ext in PAGE_EXTS:
                into.pages.append((inner, z.read(info))); usable += 1
            elif ext in FILE_EXTS:
                _add_file(inner, z.read(info), into); usable += 1
            else:
                into.ignored.append(inner)
        if usable == 0:
            raise IntakeError("zip_nothing_usable", name, f"{name} contains no pages or program files")


def _add_file(name: str, data: bytes, into: Intake) -> None:
    if len(data) > MAX_FILE_BYTES:
        raise IntakeError("too_large", name, f"{name} is over 2 MB")
    if len(into.files) >= MAX_FILES:
        raise IntakeError("too_many_files", name, f"too many files; the limit is {MAX_FILES} per submission")
    into.files.append((name, data))


def classify_uploads(files: List[Tuple[str, bytes]], *, max_files: int = MAX_FILES,
                     max_file_bytes: int = MAX_FILE_BYTES) -> Intake:
    """Split an upload into pages (images/PDFs) and program files, expanding zips. Order is kept."""
    it = Intake()
    for name, data in files:
        ext = Path(name).suffix.lower()
        if ext == ".zip":
            _expand_zip(name, data, it)
        elif ext in PAGE_EXTS:
            it.pages.append((name, data))
        elif ext in FILE_EXTS:
            _add_file(name, data, it)
        else:
            raise IntakeError("bad_file", name, f"{name}: unsupported file type (use PDF, JPG, PNG, HEIC, .py, .sb3, .xlsx or a .zip of those)")
    return it


def input_kind(it: Intake) -> str:
    if it.files and it.pages:
        return "mixed"
    return "files" if it.files else "pages"
```

(`max_files` / `max_file_bytes` are read through module constants in `_add_file` — thread them as parameters if the implementer prefers; the tests use the defaults.)

- [ ] **Step 4: Storage and `create_submission`**

`PageStorage.put_file(self, data, ext)` — same content-addressed layout as `put_jpeg` but under `files/`: `digest = sha256(data)`, `rel = f"files/{digest[:2]}/{digest}{ext}"`, write if absent, return `(digest, rel)`. `unlink` works on any relative path already.

`create_submission`: replace the `if not files` / `process_uploads` block with

```python
    try:
        intake = classify_uploads(files)
    except IntakeError as e:
        raise ApiError(400, e.code, e.message)
    if not intake.pages and not intake.files:
        raise ApiError(400, "no_files", "Add at least one page or file")
    try:
        pages = process_uploads(intake.pages, storage, **({"max_pages": max_pages} if max_pages is not None else {})) if intake.pages else []
    except UploadError as e:
        raise ApiError(400, "bad_upload", str(e))
    kind_of_input = input_kind(intake)
```

after the template checks add: `if intake.files and (template is None or template["scheme_kind"] not in V2_KINDS): raise ApiError(400, "files_need_scheme", "Files can be marked against an assignment with a mark scheme or rubric — set one first")`. The INSERT gains `input_kind` (`:ik`), and after the page rows:

```python
            for name, data in intake.files:
                digest, rel = storage.put_file(data, Path(name).suffix.lower())
                tx.insert("INSERT INTO submission_files (submission_id, name, kind, size, sha256, stored_path) "
                          "VALUES (:s, :n, :k, :z, :h, :p) RETURNING id",
                          {"s": sid, "n": name, "k": KIND_BY_EXT[Path(name).suffix.lower()], "z": len(data), "h": digest, "p": rel})
```

Return dict gains `"input_kind": kind_of_input, "files": [...names...]`, and `"ignored": intake.ignored`.

`get_submission`: query `submission_files` for the id (`ORDER BY id`), and add `"input_kind": s.get("input_kind") or "pages"` and

```python
    extracted_text = " ".join(q.get("transcribed_answer", "") for q in (run_extracted(run) or {}).get("questions", [])) if run else ""
    files = [{"id": f["id"], "name": f["name"], "kind": f["kind"], "size": f["size"], "text_rendered": f["text_rendered"],
              "deleted": f["deleted_at"] is not None, "matched": f"[{f['name']}" in extracted_text} for f in file_rows]
```

(`run_extracted(run)` is the existing helper that reads the run's extracted JSON; if it has another name, use that.)

- [ ] **Step 5: Cleanup and removal** — `pages_cleanup.delete_submission_pages`: inside the transaction also `paths += [r["stored_path"] for r in tx.query("SELECT stored_path FROM submission_files WHERE submission_id = :s AND deleted_at IS NULL")]` then `tx.execute("UPDATE submission_files SET deleted_at = CURRENT_TIMESTAMP WHERE submission_id = :s AND deleted_at IS NULL")`; `unlink_pages(storage, paths)` handles both. `remove_hand_in`: collect `submission_files.stored_path` too, `DELETE FROM submission_files WHERE submission_id = :s`, unlink after commit. `student.py::_HAND_IN_MESSAGES` gains `bad_file`, `too_large`, `too_many_files`, `zip_nothing_usable`, `zip_bomb`, `files_need_scheme` with student wording ("That file type can't be handed in — use .py, .sb3, .xlsx or photos"). The student route's count-cap message becomes "Up to 20 pages or files".

- [ ] **Step 6: Run** the new tests and the full suite → PASS. **Step 7: Commit** `feat(submissions): accept .py/.sb3/.xlsx and zips; input_kind; files on the detail and in cleanup`.

---

### Task 4: Text segmenter and the mixed/files pipeline path

**Files:**
- Create: `src/sms/schemas/segment.py`, `src/sms/agents/text_segmenter.py`
- Modify: `src/sms/pipeline/marking_pipeline_v2.py` (`__init__`, `run`, new `_segment`, `_sources_from_extracted`), `src/sms/worker/mark_job.py` (`_default_pipeline_factory`, `run_mark_job`), `src/sms/reasons.py` (`INPUT_TRUNCATED`)
- Test: `tests/unit/test_schemas_v2.py` (segment schema), `tests/unit/test_pipeline_v2_files.py` (new), `tests/unit/test_worker.py` or `tests/web/test_submissions_api.py` (mark job loads files)

**Interfaces:**
- Consumes: `Rendered`, `render_all` (Task 2); `submission_files` rows (Task 3).
- Produces: `TextSource{name, text}`, `TextSegmentInput{assignment_context, questions, sources}`; `build_text_segmenter(client, model, model_api_parameters=None) -> AtomicAgent[TextSegmentInput, ExtractedScript]`; `MarkingPipelineV2(..., segmenter=None)`; `run(images, template, submission_id=None, files: Optional[List[Rendered]] = None)`; reason `INPUT_TRUNCATED = "input truncated"` in `sms.reasons` with `reason_text`.

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_pipeline_v2_files.py
from sms.files.render import Rendered
from sms.pipeline.marking_pipeline_v2 import MarkingPipelineV2
from sms.schemas.extraction import ExtractedScript, ExtractedQuestion
from sms.schemas.marking_v2 import MarkedScriptV2, PartMark, AllocationMark, ReviewedScriptV2
from tests.unit.test_pipeline_v2 import _template, _feedback_stub, _db   # existing helpers from the v2 pipeline tests

class Fake:
    def __init__(self, out): self.out, self.calls = out, []
    def run(self, inp): self.calls.append(inp); return self.out

EX = ExtractedScript(questions=[ExtractedQuestion(q_id="1", transcribed_answer="[prog.py L1-3] print(1)", workings="", confidence=0.9)])
MARKED = MarkedScriptV2(kind="mark_scheme", parts=[PartMark(q_id="1", awarded=[AllocationMark(label="B1", marks=1, got=True)], total=1)])

def _pipeline(db, vision, segmenter):
    return MarkingPipelineV2(db=db, extractor=vision, segmenter=segmenter, marker=Fake(MARKED),
                             reviewer=Fake(ReviewedScriptV2(verdicts=[])), feedback=_feedback_stub(), kind="mark_scheme")

def test_files_only_skips_vision_and_segments(db):
    vision, seg = Fake(EX), Fake(EX)
    p = _pipeline(db, vision, seg)
    p.run(images=[], template=_template(), files=[Rendered("prog.py", "py", "syntax: ok\n   1 | print(1)\n", "1 line", False)])
    assert vision.calls == [] and len(seg.calls) == 1
    assert [s.name for s in seg.calls[0].sources] == ["prog.py"]

def test_mixed_feeds_transcription_into_segmenter(db, png_bytes):
    vision, seg = Fake(EX), Fake(EX)
    p = _pipeline(db, vision, seg)
    p.run(images=[png_bytes], template=_template(), files=[Rendered("s.xlsx", "xlsx", "sheet Marks\n  B1 = 1\n", "1 sheet", False)])
    assert len(vision.calls) == 1 and len(seg.calls) == 1
    assert [s.name for s in seg.calls[0].sources] == ["handwritten pages", "s.xlsx"]
    assert "[1] [prog.py L1-3] print(1)" in seg.calls[0].sources[0].text

def test_pages_only_never_calls_segmenter(db, png_bytes):
    vision, seg = Fake(EX), Fake(EX)
    _pipeline(db, vision, seg).run(images=[png_bytes], template=_template())
    assert seg.calls == []

def test_truncated_file_escalates_every_part(db):
    p = _pipeline(db, Fake(EX), Fake(EX))
    res = p.run(images=[], template=_template(), files=[Rendered("big.py", "py", "…", "x", True)])
    assert res.escalations == {"1": "input truncated"}

def test_segment_is_cached_by_source_hashes(db):
    seg = Fake(EX); p = _pipeline(db, Fake(EX), seg)
    f = [Rendered("prog.py", "py", "x", "1 line", False)]
    p.run(images=[], template=_template(), files=f); p.run(images=[], template=_template(), files=f)
    assert len(seg.calls) == 1
```

- [ ] **Step 2: Run** → FAIL (`unexpected keyword 'segmenter'`).

- [ ] **Step 3: Schema and agent**

```python
# src/sms/schemas/segment.py
from typing import List
from pydantic import BaseModel, Field
from atomic_agents import BaseIOSchema
from sms.schemas.scheme import Question


class TextSource(BaseModel):
    name: str = Field(..., description="File name, or 'handwritten pages' for the transcription of photographed pages")
    text: str = Field(..., description="The rendered content: numbered source lines, Scratch pseudo-code, or cells")


class TextSegmentInput(BaseIOSchema):
    """Input for the text segmenter: rendered files (and any page transcription) plus the paper's parts."""
    assignment_context: str = Field(..., description="Subject, level, task summary")
    questions: List[Question] = Field(default_factory=list, description="The paper's parts: return exactly one ExtractedQuestion per part")
    sources: List[TextSource] = Field(..., description="Every source the student handed in")
```

```python
# src/sms/agents/text_segmenter.py
from typing import Any, Optional
from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator
from sms.schemas.extraction import ExtractedScript
from sms.schemas.segment import TextSegmentInput


def build_text_segmenter(client: Any, model: str = "gpt-5-mini", model_api_parameters: Optional[dict] = None
                         ) -> AtomicAgent[TextSegmentInput, ExtractedScript]:
    return AtomicAgent[TextSegmentInput, ExtractedScript](config=AgentConfig(
        client=client, model=model, model_api_parameters=model_api_parameters,
        system_prompt_generator=SystemPromptGenerator(
            background=[
                "You map a student's submitted files (program source, Scratch pseudo-code, spreadsheet cells) and any "
                "transcribed handwritten pages onto the parts of an assignment.",
                "You copy evidence verbatim and never run, complete or correct the student's work.",
            ],
            steps=[
                "Read every source. For each listed part, find the lines, blocks or cells that address it.",
                "Put the relevant excerpt(s) in transcribed_answer, each prefixed with its source and location, e.g. "
                "'[prog.py L12-30]', '[results.xlsx Marks!B4]', '[Cat script 2]', '[handwritten pages]'. Put supporting "
                "context (helper functions, other cells the excerpt depends on) in workings.",
                "If no source addresses a part, return an empty transcribed_answer and needs_human_transcription=true.",
                "Confidence reflects how clearly the excerpt addresses the part, not code quality.",
            ],
            output_instructions=[
                "Exactly one ExtractedQuestion per listed part, q_id equal to the part's q_id, in the given order.",
                "Never paraphrase code, formulas or block text; quote them.",
            ])))
```

- [ ] **Step 4: Pipeline** — in `marking_pipeline_v2.py`:

```python
    def __init__(self, db, extractor, marker, reviewer, feedback, kind, confidence_threshold=0.0, segmenter=None):
        ...; self.segmenter = segmenter

    def run(self, images, template, submission_id=None, files=None) -> MarkingResultV2:
        ...
        files = list(files or [])
        if images and not files:
            extracted = self._extract(images, subject, questions, notes)
        else:
            sources = []
            if images:
                vision = self._extract(images, subject, questions, notes)
                sources.append(TextSource(name="handwritten pages", text=_sources_from_extracted(vision)))
            sources += [TextSource(name=f.name, text=f.text) for f in files]
            extracted = self._segment(sources, subject, questions, notes)
        ... marker / reviewer / merge as before ...
        if any(f.truncated for f in files):
            for m in (final.parts or final.rubric):
                escalations.setdefault(_key(m), INPUT_TRUNCATED)
        ...

    def _segment(self, sources, subject, questions, notes) -> ExtractedScript:
        if self.segmenter is None:
            raise RuntimeError("This assignment's model set-up cannot read files yet — the segmenter is missing")
        digest = self.cache.hash_image(("|".join(f"{s.name}:{self.cache.hash_image(s.text.encode())}" for s in sources)
                                        + "#seg#" + ",".join(q.q_id for q in questions)).encode())
        cached = self.cache.get(digest, subject)
        if cached is not None:
            return ExtractedScript.model_validate(cached)
        context = f"{subject} submission, {len(questions)} part(s)" + (f". Notes: {notes}" if notes else "")
        extracted = self.segmenter.run(TextSegmentInput(assignment_context=context, questions=questions, sources=sources))
        self.cache.put(digest, subject, extracted.model_dump())
        return extracted


def _sources_from_extracted(ex: ExtractedScript) -> str:
    return "\n\n".join(f"[{q.q_id}] {q.transcribed_answer}" + (f"\n{q.workings}" if q.workings else "") for q in ex.questions)
```

`sms/reasons.py`: add `INPUT_TRUNCATED = "input truncated"` and its `reason_text` entry ("The files were too large to read completely — check this part against the original"). Any list of "the five reasons" in tests/records grows to six.

- [ ] **Step 5: Worker** — `_default_pipeline_factory`: for v2 kinds add `"segmenter": build_text_segmenter(client=client, model=settings.model, model_api_parameters=params)` to `agents` (it is rate-limited and metric-wired with the rest). `run_mark_job`: after loading pages,

```python
    file_rows = db.query("SELECT id, name, stored_path, deleted_at FROM submission_files WHERE submission_id = :id ORDER BY id", {"id": submission_id})
    if any(f["deleted_at"] is not None for f in file_rows):
        raise RuntimeError("This submission's files were deleted after marking, so it cannot be marked again")
    rendered = render_all([(f["name"], storage.read(f["stored_path"])) for f in file_rows]) if file_rows else []
    for f, r in zip(file_rows, rendered):
        db.execute("UPDATE submission_files SET text_rendered = :t WHERE id = :i", {"t": r.text, "i": f["id"]})
```

`RenderError` → `RuntimeError(str(e))` (non-retryable, shown as the job error). Pass `files=rendered` to `pipeline.run(...)` on the v2 branch; on the v1 branch with `rendered` non-empty raise `RuntimeError("Files need an assignment with a mark scheme or rubric")` (unreachable after Task 3's guard, kept as a safety net). The images list may be empty now: `pages` query result can be `[]`.

- [ ] **Step 6: Run** the new tests + full suite → PASS. **Step 7: Commit** `feat(pipeline): text segmenter; files-only and mixed submissions join the v2 path`.

---

### Task 5: No double penalisation

**Files:**
- Modify: `src/sms/schemas/marking_v2.py` (`DoublePenalty`, `ReviewedScriptV2.double_penalties`), `src/sms/subjects/scheme_prompts.py` (rule text in both kinds), `src/sms/pipeline/marking_pipeline_v2.py` (`_apply_double_penalties` called from `_merge`), `src/sms/reasons.py` (`DOUBLE_PENALTY`)
- Test: `tests/unit/test_schemas_v2.py`, `tests/unit/test_pipeline_v2.py`

**Interfaces:**
- Produces: `DoublePenalty{error: str, q_ids: List[str]}`; `ReviewedScriptV2.double_penalties: List[DoublePenalty] = []`; reason `DOUBLE_PENALTY = "double penalty"`.

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_pipeline_v2.py (append)
def _part(q, allocs):
    return PartMark(q_id=q, awarded=[AllocationMark(label=l, marks=m, got=g) for l, m, g in allocs], total=sum(m for _, m, g in allocs if g))

def test_double_penalty_restores_the_later_part(db):
    marked = MarkedScriptV2(kind="mark_scheme", parts=[_part("1a", [("M1", 1, True), ("A1", 1, False)]), _part("1b", [("B1", 1, False)])])
    reviewed = ReviewedScriptV2(verdicts=[], double_penalties=[DoublePenalty(error="sign error in 1a", q_ids=["1a", "1b"])])
    p = _pipeline_with(db, marked, reviewed)                       # helper: fake marker/reviewer returning these
    res = p.run(images=[b"x"], template=_template(parts=["1a", "1b"]))
    b = next(x for x in res.final.parts if x.q_id == "1b")
    assert b.total == 1 and b.awarded[0].got and b.awarded[0].why == "already penalised in 1a"
    assert "1b" not in res.escalations

def test_double_penalty_ambiguous_escalates(db):
    marked = MarkedScriptV2(kind="mark_scheme", parts=[_part("1a", [("A1", 1, False)]), _part("1b", [("M1", 1, False), ("A1", 1, False)])])
    reviewed = ReviewedScriptV2(verdicts=[], double_penalties=[DoublePenalty(error="same slip", q_ids=["1a", "1b"])])
    res = _pipeline_with(db, marked, reviewed).run(images=[b"x"], template=_template(parts=["1a", "1b"]))
    assert res.escalations["1b"] == "double penalty"

def test_double_penalty_rubric_keeps_band_and_notes(db):
    # rubric kind: the later criterion keeps its band; justification gains the note
    ...
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**

`marking_v2.py`:

```python
class DoublePenalty(BaseModel):
    error: str = Field(description="The single slip that was deducted more than once, in the marker's words")
    q_ids: List[str] = Field(min_length=2, description="Parts / criteria where it was deducted, first occurrence first")

class ReviewedScriptV2(BaseIOSchema):
    verdicts: ...
    double_penalties: List[DoublePenalty] = Field(default_factory=list,
        description="Errors the marker deducted in more than one part or criterion; empty when none")
```

`scheme_prompts.py` — append to `MARK_SCHEME["steps"]`: "An error costs marks once: deduct it where it first occurs, mark later parts on the work as it stands (error carried forward) and never deduct the same slip twice." To `RUBRIC["steps"]`: "A weakness counts once: do not lower two criteria for the same slip; place it under the criterion it belongs to." To both `reviewer_steps`: "Check for double penalisation: if one slip cost marks in two or more parts / criteria, list it in double_penalties with the parts in order of first occurrence; the merge keeps the first deduction." To both `reviewer_output_instructions`: "double_penalties is empty unless the same error was deducted twice."

`marking_pipeline_v2.py` — at the end of `_merge`, before returning, call `self._apply_double_penalties(final, reviewed, escalations)`:

```python
    def _apply_double_penalties(self, final: List[Mark], reviewed: ReviewedScriptV2, escalations: Dict[str, str]) -> None:
        by_key = {_key(m): m for m in final}
        for dp in reviewed.double_penalties:
            keys = [norm_qid(q) if self.kind == "mark_scheme" else q for q in dp.q_ids]
            first, later = keys[0], keys[1:]
            for key in later:
                m = by_key.get(key)
                if m is None or key in escalations:
                    continue
                if isinstance(m, PartMark):
                    lost = [a for a in m.awarded if not a.got]
                    if len(lost) == 1:
                        lost[0].got = True
                        lost[0].why = f"already penalised in {first}"
                        m.total = sum(a.marks for a in m.awarded if a.got)
                        m.justification = (m.justification + f" {lost[0].label} restored: '{dp.error}' already penalised in {first}.").strip()
                    elif lost:
                        escalations[key] = DOUBLE_PENALTY  # which allocation to restore is the teacher's call
                else:
                    m.justification = (m.justification + f" Reviewer: '{dp.error}' already penalised under {first}; band kept.").strip()
```

`_key` for rubric marks is the criterion name, so `keys` uses the raw id there. `sms/reasons.py`: `DOUBLE_PENALTY = "double penalty"`, text "The reviewer found the same error deducted twice — decide which part keeps the deduction".

- [ ] **Step 4: Run** → PASS; full suite green. **Step 5: Commit** `feat(marking): an error is penalised once — reviewer flags, merge restores`.

---
### Task 6: Model per subject — store, resolution, API

**Files:**
- Create: `src/sms/web/services/subject_models.py`
- Modify: `src/sms/providers/settings.py:200-219` (`for_template`), `src/sms/web/services/assignments.py` (`effective_model` with `source`), `src/sms/web/routers/settings.py`
- Test: `tests/unit/test_settings_store.py`, `tests/web/test_settings_api.py`, `tests/web/test_assignments_api.py`

**Interfaces:**
- Produces: `list_subject_models(db) -> Dict[str, Optional[dict]]` (every known subject, `None` = Auto); `set_subject_model(db, subject, provider, model, extractor_model=None) -> dict`; `clear_subject_model(db, subject)`; `SettingsStore.subject_default(subject) -> Optional[dict]`; `for_template` resolution pin → subject → global; template `effective_model: {provider, model, extractor_model, source: "assignment" | "subject" | "settings"}`; routes `GET /api/settings/subject-models`, `PUT /api/settings/subject-models/{subject}`, `DELETE /api/settings/subject-models/{subject}`.

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_settings_store.py (append)
def test_for_template_uses_subject_default_when_no_pin(store_with_keys):   # fixture: global openrouter + saved key for 'google'
    store, db = store_with_keys
    db.execute("INSERT INTO subject_models (subject, provider, model) VALUES ('mt', 'google', 'gemini-3.8-pro')")
    s = store.for_template({"subject": "mt", "provider": None, "model": None})
    assert (s.provider, s.model) == ("google", "gemini-3.8-pro") and s.api_key == store.key_for("google")

def test_pin_beats_subject_default(store_with_keys):
    store, db = store_with_keys
    db.execute("INSERT INTO subject_models (subject, provider, model) VALUES ('computing', 'google', 'g')")
    s = store.for_template({"subject": "computing", "provider": "openrouter", "model": "openai/gpt-5.5"})
    assert (s.provider, s.model) == ("openrouter", "openai/gpt-5.5")

def test_keyless_subject_default_is_ignored(store_with_keys, caplog):
    store, db = store_with_keys
    db.execute("INSERT INTO subject_models (subject, provider, model) VALUES ('mt', 'anthropic', 'claude-x')")
    s = store.for_template({"subject": "mt", "provider": None})
    assert s.provider == "openrouter" and "no saved key" in caplog.text

# tests/web/test_settings_api.py (append)
def test_subject_models_crud(auth_with_google_key):
    c = auth_with_google_key
    assert c.get("/api/settings/subject-models").json() == {"math": None, "language": None, "science": None, "mt": None, "computing": None}
    r = c.put("/api/settings/subject-models/mt", json={"provider": "google", "model": "gemini-3.8-pro"})
    assert r.status_code == 200 and r.json()["model"] == "gemini-3.8-pro"
    assert c.put("/api/settings/subject-models/mt", json={"provider": "anthropic", "model": "x"}).json()["error"]["code"] == "no_key_for_provider"
    assert c.put("/api/settings/subject-models/art", json={"provider": "google", "model": "x"}).status_code == 400
    assert c.delete("/api/settings/subject-models/mt").status_code == 204
    assert c.get("/api/settings/subject-models").json()["mt"] is None

# tests/web/test_assignments_api.py (append)
def test_effective_model_reports_source(auth_with_google_key):
    c = auth_with_google_key
    c.put("/api/settings/subject-models/computing", json={"provider": "google", "model": "gemini-3.8-flash"})
    t = c.post("/api/assignments", json=_tpl(subject="computing")).json()
    assert t["effective_model"] == {"provider": "google", "model": "gemini-3.8-flash", "extractor_model": None, "source": "subject"}
    t2 = c.post("/api/assignments", json=_tpl(subject="math")).json()
    assert t2["effective_model"]["source"] == "settings"
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**

`services/subject_models.py`:

```python
from typing import Dict, Optional
from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.providers.registry import get_provider
from sms.providers.settings import SettingsStore
from sms.web.errors import ApiError


def list_subject_models(db: Database) -> Dict[str, Optional[dict]]:
    rows = {r["subject"]: r for r in db.query("SELECT subject, provider, model, extractor_model FROM subject_models")}
    return {s: ({"provider": rows[s]["provider"], "model": rows[s]["model"], "extractor_model": rows[s]["extractor_model"]}
                if s in rows else None) for s in SubjectRouter.KNOWN_SUBJECTS}


def set_subject_model(db: Database, subject: str, provider: str, model: str, extractor_model: Optional[str] = None) -> dict:
    try:
        subject = SubjectRouter().resolve(subject)
    except KeyError:
        raise ApiError(400, "bad_subject", "Unknown subject")
    try:
        get_provider(provider)
    except KeyError:
        raise ApiError(400, "bad_provider", "Unknown provider")
    if not SettingsStore.has_key_for(db, provider):
        raise ApiError(400, "no_key_for_provider", f"Save a key for {get_provider(provider).label} under Settings first")
    model = (model or "").strip()
    if not model:
        raise ApiError(400, "bad_model", "Choose a model")
    extractor_model = (extractor_model or "").strip() or None
    with db.transaction() as tx:
        tx.execute("DELETE FROM subject_models WHERE subject = :s", {"s": subject})
        tx.execute("INSERT INTO subject_models (subject, provider, model, extractor_model) VALUES (:s, :p, :m, :e)",
                   {"s": subject, "p": provider, "m": model, "e": extractor_model})
    return {"provider": provider, "model": model, "extractor_model": extractor_model}


def clear_subject_model(db: Database, subject: str) -> None:
    db.execute("DELETE FROM subject_models WHERE subject = :s", {"s": subject})
```

`SettingsStore`:

```python
    def subject_default(self, subject: Optional[str]) -> Optional[dict]:
        if not subject:
            return None
        rows = self.db.query("SELECT provider, model, extractor_model FROM subject_models WHERE subject = :s", {"s": subject})
        return dict(rows[0]) if rows else None

    def for_template(self, tpl: Optional[dict]) -> Settings:
        """Resolution: the assignment's own pin, else its subject's default, else the global settings."""
        s = self.load()
        if not tpl:
            return s
        if tpl.get("provider"):
            return self._overlay(s, tpl["provider"], tpl.get("model"), tpl.get("extractor_model"))
        sub = self.subject_default(tpl.get("subject"))
        if sub is None:
            return s
        if not self.key_for(sub["provider"]):
            log.info("subject default for %s ignored: no saved key for %s", tpl.get("subject"), sub["provider"])
            return s
        return self._overlay(s, sub["provider"], sub["model"], sub["extractor_model"])

    def _overlay(self, s: Settings, provider: str, model: Optional[str], extractor_model: Optional[str]) -> Settings:
        spec = get_provider(provider)
        s.model = model or spec.default_model
        s.extractor_model = extractor_model or None
        s.api_key = self.key_for(provider)
        s.base_url = None if provider != s.provider else s.base_url
        if provider != s.provider:
            s.rpm_limit = spec.default_rpm
        s.provider = provider
        return s
```

`assignments.py` — `effective_model` now: `store = SettingsStore(db)`; if `tpl["provider"]` → source `assignment`; elif `store.subject_default(tpl["subject"])` with a saved key → source `subject`; else `settings`; the provider/model/extractor_model come from `store.for_template(tpl)`. Routes in `routers/settings.py`:

```python
@router.get("/subject-models")
def subject_models(db=Depends(get_db)): return list_subject_models(db)

@router.put("/subject-models/{subject}")
def put_subject_model(subject: str, body: SubjectModelBody, db=Depends(get_db)):
    return set_subject_model(db, subject, body.provider, body.model, body.extractor_model)

@router.delete("/subject-models/{subject}", status_code=204)
def delete_subject_model(subject: str, db=Depends(get_db)):
    clear_subject_model(db, subject); return Response(status_code=204)
```

with `class SubjectModelBody(BaseModel): provider: str; model: str; extractor_model: Optional[str] = None`. Also extend the key-removal guard from slice 3 (`DELETE /api/settings/keys/{provider}`): the `in_use` count adds subjects whose default uses that provider (`count = templates + subject defaults`, message names both).

- [ ] **Step 4: Run** → PASS; full suite green. **Step 5: Commit** `feat(settings): a default model per subject; assignment pin > subject > settings`.

---

### Task 7: MT and Computing in the pipeline — language, subject notes, feedback language

**Files:**
- Modify: `src/sms/schemas/feedback.py` (`FeedbackInput.feedback_language`), `src/sms/agents/feedback.py` (prompt), `src/sms/agents/marker_v2.py` + `src/sms/agents/reviewer_v2.py` (subject note in background), `src/sms/pipeline/marking_pipeline_v2.py` (`_extract` context with language; `feedback_input_for_v2(..., language)`), `src/sms/worker/mark_job.py` (`_v2_template` returns `language` — done in Task 1)
- Test: `tests/unit/test_pipeline_v2_files.py` or `test_pipeline_v2.py`, `tests/unit/test_schemas_v2.py`

**Interfaces:**
- Consumes: `LANGUAGE_NAMES`, `SUBJECT_NOTE` (Task 1).
- Produces: `FeedbackInput.feedback_language: str = "en"`; `feedback_input_for_v2(final, reviewed, escalations, language="en")`; `build_marker_v2/build_reviewer_v2` append the subject's `SUBJECT_NOTE` when the module defines one.

- [ ] **Step 1: Failing tests**

```python
def test_mt_language_reaches_extractor_context_and_feedback(db, png_bytes):
    vision, feedback = Fake(EX), Fake(FEEDBACK_STUB)
    p = MarkingPipelineV2(db=db, extractor=vision, marker=Fake(MARKED), reviewer=Fake(ReviewedScriptV2(verdicts=[])), feedback=feedback, kind="rubric")
    p.run(images=[png_bytes], template=_template(subject="mt", language="zh", kind="rubric"))
    assert "Chinese" in vision.calls[0].assignment_context and "do not translate" in vision.calls[0].assignment_context
    assert feedback.calls[0].feedback_language == "zh"

def test_other_subjects_feedback_in_english(db, png_bytes):
    feedback = Fake(FEEDBACK_STUB)
    ...run with subject math...
    assert feedback.calls[0].feedback_language == "en"

def test_marker_v2_background_carries_subject_note():
    agent = build_marker_v2(client=FakeClient(), kind="mark_scheme", subject="computing")
    assert any("Never claim to have run anything" in b for b in agent.system_prompt_generator.background)
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**

`schemas/feedback.py`: `feedback_language: str = Field(default="en", description="Language code for every student-facing sentence: en, zh, ms or ta")`. `agents/feedback.py` output instructions gain: "Write summary, strengths, comments, improvement_plan and next_steps in the language named by feedback_language (en = English, zh = Chinese, ms = Malay, ta = Tamil); keep q_ids and mark-scheme labels unchanged." `feedback_input_for_v2(final, reviewed, escalations, language="en")` sets it; `run()` computes `language = (template.get("language") or "en") if subject == "mt" else "en"`.

`_extract`: when `subject == "mt"`, `context += " " + mt_prompt.SUBJECT_NOTE.format(language=LANGUAGE_NAMES.get(template_language, "the script's language"))` — pass `template.get("language")` into `_extract` as a new keyword. `build_marker_v2` / `build_reviewer_v2`: `note = getattr(importlib.import_module(f"sms.subjects.{subject}.prompt"), "SUBJECT_NOTE", None)`; when present, `background = cfg["background"] + [note.replace("{language}", "the assignment's language")]` (the formatted language lives in the extractor context; the marker sees the transcription).

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat(subjects): MT feedback in the script's language; Computing read-only marking notes`.

---

### Task 8: Bulk upload — zip matched by register number (backend)

**Files:**
- Create: `src/sms/files/bulk.py`
- Modify: `src/sms/web/services/class_assignments.py` (`bulk_preview`, `bulk_commit`), `src/sms/web/routers/class_assignments.py` (two routes)
- Test: `tests/unit/test_files_bulk.py`, `tests/web/test_class_assignments_api.py`

**Interfaces:**
- Consumes: `classify_uploads` (Task 3), `hand_in`, `remove_hand_in`.
- Produces: `match_entries(names: List[str], students: List[dict]) -> BulkPlan{matched: Dict[int, List[str]], ambiguous: List[str], unmatched: List[str]}` (students carry `id`, `reg_no`, `name`); `bulk_preview(db, ca, zip_bytes) -> dict`; `bulk_commit(db, storage, jobs, ca, zip_bytes, replace: bool) -> dict`; routes `POST /api/classes/{id}/assignments/{caid}/bulk/preview` and `POST …/bulk?replace=0|1` (multipart field `zip`).

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_files_bulk.py
from sms.files.bulk import match_entries
STUDENTS = [{"id": 1, "reg_no": 7, "name": "Amirah"}, {"id": 2, "reg_no": 12, "name": "Ben"}]

def test_prefix_forms():
    plan = match_entries(["07_amirah.py", "12 - ben/prog.py", "12 - ben/data.xlsx", "7.jpg", "notes.txt", "99_nobody.py"], STUDENTS)
    assert plan.matched == {1: ["07_amirah.py", "7.jpg"], 2: ["12 - ben/prog.py", "12 - ben/data.xlsx"]}
    assert plan.unmatched == ["notes.txt", "99_nobody.py"] and plan.ambiguous == []

def test_ambiguous_when_two_students_share_a_number():
    plan = match_entries(["7_x.py"], STUDENTS + [{"id": 3, "reg_no": 7, "name": "Dup"}])
    assert plan.ambiguous == ["7_x.py"] and plan.matched == {}
```

```python
# tests/web/test_class_assignments_api.py (append) — seed class 4E2 with students #7 and #12 and an opened
# mark-scheme assignment; POST a zip with "07_a.py" and "12/prog.py" to …/bulk/preview → 200 with
# {"matched": [{"student_id":..,"reg_no":7,"name":..,"files":["07_a.py"]}, ...], "unmatched": [], "ambiguous": []};
# POST …/bulk → 202 {"created": [7, 12], "skipped": [], "unmatched": []}; a second POST without replace → skipped both;
# with ?replace=1 → created again and the old submissions gone.
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**

```python
# src/sms/files/bulk.py
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

_LEAD = re.compile(r"^\s*0*(\d+)(?=[\s_\-./]|$)")


@dataclass
class BulkPlan:
    matched: Dict[int, List[str]] = field(default_factory=dict)
    ambiguous: List[str] = field(default_factory=list)
    unmatched: List[str] = field(default_factory=list)


def _reg_of(name: str):
    head = Path(name).parts[0] if len(Path(name).parts) > 1 else Path(name).stem
    m = _LEAD.match(head)
    return int(m.group(1)) if m else None


def match_entries(names: List[str], students: List[dict]) -> BulkPlan:
    by_reg: Dict[int, List[dict]] = {}
    for s in students:
        by_reg.setdefault(int(s["reg_no"]), []).append(s)
    plan = BulkPlan()
    for n in names:
        reg = _reg_of(n)
        hits = by_reg.get(reg, []) if reg is not None else []
        if len(hits) == 1:
            plan.matched.setdefault(hits[0]["id"], []).append(n)
        elif len(hits) > 1:
            plan.ambiguous.append(n)
        else:
            plan.unmatched.append(n)
    return plan
```

`bulk_preview(db, ca, zip_bytes)`: open the zip (reuse `classify_uploads([("bulk.zip", zip_bytes)])` only for validation of the bomb cap; for matching read the entry names directly with `zipfile`, skipping dirs and junk), `match_entries(names, list_students(db, ca["class_id"]))`, return `{"matched": [{student_id, reg_no, name, files, already_handed_in: bool}], "ambiguous": [...], "unmatched": [...]}`.
`bulk_commit(db, storage, jobs, ca, zip_bytes, replace)`: for each matched student in reg order: if already handed in and not replace → `skipped`; else (`remove_hand_in` first when replacing) build that student's `[(Path(n).name, bytes)]` and call `hand_in(db, storage, jobs, ca=ca, student=st, files=…, source="teacher")` inside a per-student `try/except ApiError` that records `{"reg_no", "error"}` in `failed` and continues. Return `{"created": [reg…], "skipped": [reg…], "failed": [...], "unmatched": [...], "ambiguous": [...]}`. Routes mirror `upload_for_student` (content-length check, `no_key` guard, `run_in_threadpool`), multipart field name `zip`.

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat(classes): bulk upload — a zip matched to students by register number`.

---
### Task 9: Frontend — types, assignment editor (MT language, Computing), Settings *By subject* table

**Files:**
- Create: `web/src/pages/settings/SubjectModels.tsx`
- Modify: `web/src/api/types.ts` (`Subject`, `AssignmentTemplate.language`, `AssignmentBody.language`, `EffectiveModel.source`, `SubjectModels`), `web/src/lib/format.ts` (`subjectLabel`: `mt: "MT"`, `computing: "Computing"`; `languageLabel`), `web/src/pages/AssignmentEditor.tsx`, `web/src/pages/Settings.tsx`
- Test: `web/src/pages/__tests__/AssignmentEditor.test.tsx`, `web/src/pages/__tests__/Settings.test.tsx`, `web/src/pages/settings/__tests__/SubjectModels.test.tsx`

**Interfaces:**
- Consumes: routes of Task 6; template `language`, `effective_model.source` (Tasks 1, 6).
- Produces: `type Subject = "math" | "language" | "science" | "mt" | "computing"`; `type MtLanguage = "zh" | "ms" | "ta"`; `SubjectModels = Record<Subject, {provider: string; model: string; extractor_model: string | null} | null>`; `<SubjectModels providers settings onChange />` component.

- [ ] **Step 1: Tests**: editor — choosing subject **MT** shows a `<select aria-label="Language">` with Chinese / Malay / Tamil (default Chinese) and saving sends `language: "zh"`; choosing **Computing** shows the note "Students can hand in files (.py, .sb3, .xlsx) and photos" and sends `language: null`; the Auto caption reads "Using Google Gemini · gemini-3.8-flash from the Computing default" when `effective_model.source === "subject"`. Settings — a table `role="table"` `aria-label="Model by subject"` with one row per subject (Maths, English, Science, MT, Computing); each row has a `.seg` "Auto | Choose" (`aria-label="<Subject> model"`); choosing on MT shows provider tiles (keyless disabled, title "No key saved — add one under Settings") and a model select; **Save** on the row PUTs `/api/settings/subject-models/mt` with `{provider, model, extractor_model}`; switching back to Auto DELETEs; the MT row shows the hint "Pick a model that reads Chinese, Malay or Tamil handwriting well", the Computing row "Pick a model that is strong at code".
- [ ] **Step 2:** FAIL. **Step 3:** implement. Editor: `Draft` gains `language: MtLanguage`; the Language select renders only for `subject === "mt"`; `toBody` sends `language: subject === "mt" ? language : null`. Settings: the *By subject* table sits under the provider/model form as its own section (`section-head` "By subject" + help "New assignments follow their subject's model; each assignment can still pin its own."); rows keep local draft state and save independently; reuse the provider-tile and model-select markup from `AssignmentEditor`'s Model section by extracting it into `web/src/components/ModelPicker.tsx` (`{providers, keys, value: {provider, model, extractorModel}, onChange}`) and using it in both places.
- [ ] **Step 4:** PASS; `npx tsc --noEmit` clean. **Step 5:** commit `feat(web): MT and Computing subjects; model by subject in Settings`.

---

### Task 10: Frontend — files in the student hand-in, downsizing on teacher uploads, Files block on the detail page

**Files:**
- Create: `web/src/components/FilesBlock.tsx`
- Modify: `web/src/lib/files.ts` (`isProgramFile`, `PROGRAM_ACCEPT = ".py,.sb3,.xlsx,.zip"`, `fmtSize`), `web/src/student/HandIn.tsx`, `web/src/components/DropZone.tsx` (`accept` prop), `web/src/pages/NewSubmission.tsx`, `web/src/pages/ClassAssignmentPage.tsx` (per-student upload), `web/src/pages/SubmissionDetail.tsx`, `web/src/api/types.ts` (`SubmissionDetail.input_kind`, `files: SubmissionFile[]`; `StudentAssignmentDetail.subject`, `accepts_files`)
- Test: `web/src/student/__tests__/HandIn.test.tsx`, `web/src/pages/__tests__/ClassAssignmentPage.test.tsx`, `web/src/pages/__tests__/NewSubmission.test.tsx`, `web/src/components/__tests__/FilesBlock.test.tsx`

**Interfaces:**
- Consumes: `downscale(file)` from `web/src/lib/image.ts`; detail `files` shape (Task 3); the student assignment detail must expose `subject` (add it in `services/student.py::student_assignment` if missing — one field).
- Produces: `SubmissionFile = {id: number; name: string; kind: "py" | "sb3" | "xlsx"; size: number; text_rendered: string | null; deleted: boolean; matched: boolean}`; `prepareUploads(files: File[]): Promise<File[]>` in `web/src/lib/files.ts` — downscales every image (`canThumbnail`), passes PDFs and program files through unchanged.

- [ ] **Step 1: Tests**: HandIn — for a Computing assignment an *Add files* button (`input accept=".py,.sb3,.xlsx,.zip"`) appears beside the photo buttons; adding `prog.py` and one photo lists both in order (name + "1.2 KB" for the file, thumbnail for the photo); *Hand in* sends both as `files` parts and the photo was passed through `downscale` (mock `../lib/image`); for a Maths assignment there is no *Add files*. ClassAssignmentPage — the per-student upload calls `prepareUploads` before POST (a 4000 px PNG fixture becomes ≤ 2000 px via the mocked `downscale`), and the dropped list shows the reduced size. NewSubmission — same `prepareUploads` before POST. FilesBlock — renders one row per file (name, kind label "Python" / "Scratch" / "Excel", size), "Show text" expands `text_rendered` in a `<pre>`, an unmatched file shows the note "Not used for any part", a deleted file shows "Deleted after marking".
- [ ] **Step 2:** FAIL. **Step 3:** implement. `HandIn`: the `Page` item gains `kind: "photo" | "file"`; `add()` accepts program files when `detail.accepts_files` (subject computing); the list renders `<li>` with either the thumbnail or a file icon + name + `fmtSize`; the upload loop uses `prepareUploads`. `DropZone` gets an optional `accept` prop and hint; `ClassAssignmentPage`'s per-student input uses `ACCEPT + ",.py,.sb3,.xlsx,.zip"` when the assignment subject is computing. `SubmissionDetail`: render `<FilesBlock files={d.files} />` above the marks when `d.files.length > 0`; the meta line says "2 pages · 3 files".
- [ ] **Step 4:** PASS; `tsc` clean. **Step 5:** commit `feat(web): hand in files with photos; downsize photos on every upload; files on the detail page`.

---

### Task 11: Frontend — bulk upload on the class assignment page

**Files:**
- Create: `web/src/components/BulkUpload.tsx`
- Modify: `web/src/pages/ClassAssignmentPage.tsx` (toolbar button **Bulk upload**), `web/src/api/types.ts` (`BulkPreview`, `BulkResult`)
- Test: `web/src/components/__tests__/BulkUpload.test.tsx`, `web/src/pages/__tests__/ClassAssignmentPage.test.tsx`

**Interfaces:**
- Consumes: routes of Task 8.

- [ ] **Step 1: Tests**: clicking **Bulk upload** opens a dialog (`role="dialog"` `aria-label="Bulk upload"`) with a drop for one `.zip`; after choosing, it POSTs `…/bulk/preview` and lists matched students ("#7 Amirah — 07_a.py, 7.jpg"), unmatched files under "Not matched" and ambiguous ones under "More than one student"; students already handed in show "already handed in — will be skipped" and a checkbox "Replace existing hand-ins" flips the commit URL to `?replace=1`; **Upload** POSTs `…/bulk` and shows "Created 2 · Skipped 0 · Not matched 1"; the roster refreshes.
- [ ] **Step 2:** FAIL. **Step 3:** implement with the app's existing dialog pattern (see the Release dialog in `ClassAssignmentPage`); the zip is sent as multipart field `zip`; errors surface `e.message`.
- [ ] **Step 4:** PASS; `tsc` clean. **Step 5:** commit `feat(web): bulk upload a zip matched by register number`.

---

### Task 12: Docs and final verification

- [ ] README **Web app**: paragraphs for **Files** (what is accepted, read-only marking, mixed with photos, limits), **MT** (language, feedback language), **Computing**, **Model by subject**, **No double penalisation**, **Bulk upload**; Settings list gains *By subject*; roadmap updated. `docs/setup-guide/README.md` §12/§13 numbering untouched — add one short paragraph to **Good to know** ("Computing assignments accept .py, .sb3 and .xlsx files, alone or with photos; MT assignments give feedback in the script's language"). Do not rebuild the PDF in this task (the guide is regenerated separately).
- [ ] Full verification: `uv run python -m pytest -q`; `cd web && npx vitest run && npx tsc --noEmit && npm run build`; local click-through with a scratch data dir: Settings → By subject → set Computing to a keyed provider → editor → new Computing assignment (note visible) → class assignment → per-student upload of `ok.py` + one photo → detail shows Files block → Settings → MT row hint visible. Screenshots to the scratchpad; report paths.
- [ ] Commit `docs: files, MT, Computing, model by subject, no double penalisation`.

---

## Self-review

- **Spec coverage:** A1 → T3 (intake, limits, codes); A2 → T1 (migration) + T3 (storage, cleanup); A3 → T2; A4 → T4 (segmenter, mixed, truncation, unmatched via `matched`); B → T1 + T7; C → T5; D → T6 + T9; E → T9, T10, T11 (+ downsizing in T10); F → T3/T4 (codes, no execution, zip cap); H → tests in every task.
- **Type consistency:** `Rendered` (T2) consumed by T4's `run(files=)`; `classify_uploads/Intake` (T3) by T8; `TextSource/TextSegmentInput` (T4) only inside T4; `DoublePenalty` (T5) on `ReviewedScriptV2`; `for_template/_overlay/subject_default` (T6) consumed by T6's `effective_model` and unchanged callers; `feedback_language` (T7) end to end; frontend `Subject`, `SubmissionFile`, `SubjectModels`, `BulkPreview` named identically across T9–T11.
- **Placeholders:** none — the three UI tasks specify labels, roles, payloads and assertions; the rubric-kind double-penalty test body is described in one line and must be written by the implementer as a real test (band kept, note appended).

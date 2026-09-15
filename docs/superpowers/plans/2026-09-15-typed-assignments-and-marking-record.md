# Typed Assignments, Per-Part Marking & Marking Records — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teachers create an assignment by type (mark scheme or rubric) with a question paper, scheme and notes; scripts are marked per question part against that scheme; each student gets a downloadable marking record (.docx, bulk .zip + .xlsx) with a "Teacher's mark" column; student pages are deleted once a script is done.

**Architecture:** Extend the batch-2 assignment bank (`assignment_templates` with `scheme_kind/questions_json/scheme_json`, paper pages) with two LLM extraction jobs (paper → questions, scheme PDF → rows) and an editable wizard. Add a v2 marking path in the pipeline (per-part marker/reviewer/merge with `in_scheme` escalation) chosen by the assignment's `scheme_kind`, persisted as `final_marks_json` version 2. Add a pure record builder + `python-docx`/`openpyxl` renderers behind download endpoints, and a deletion step on `done`.

**Tech Stack:** as slice 1/batch 2 (FastAPI, SQLAlchemy Core + Alembic, instructor/atomic-agents, React + TS + Vite) plus `python-docx`, `openpyxl`.

**Spec:** `docs/superpowers/specs/2026-09-15-typed-assignments-and-marking-record-design.md` (binding). Batch-2 code to build on: `src/sms/web/services/assignments.py` (pydantic `Question`, `MarkPoint`, `MarkSchemeEntry`, `Band`, `RubricCriterionBands`, `attach_paper`), `src/sms/worker/{jobs,worker,reflect_job}.py` (job kinds, `enqueue_unique`, payload), `web/src/pages/{Assignments,NewSubmission,SubmissionDetail,Review}.tsx`.

## Global Constraints

- `uv run …`; deps via `uv add`; portable SQL (SQLite + Postgres; `batch_alter_table` for column changes); every commit ends with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`; `uv run pytest -q` green with no warnings summary and `cd web && npx vitest run && npx tsc --noEmit && npm run build` clean before each commit.
- Backward compatibility: slice-1/batch-2 runs (`final_marks_json` without `version`) must still render in the detail page, review queue and record ("version 1": rows are questions, columns are criteria).
- "Teacher to review" is the only wording for escalated parts on teacher-facing surfaces; the record never contains page images.
- Escalation rules (v2): illegible part, `in_scheme == false`, reviewer ESCALATE/disagreement, confidence below threshold.
- Deletion rule: student pages are deleted only when a submission reaches `done`; question-paper/scheme pages are never deleted; `pages.deleted_at` set and file removed; page route → 410 `gone`.
- Timestamps via `sms.timeutil.iso_utc`; API errors `{"error": {"code","message"}}`.

## File structure

**Backend — create**
- `src/sms/migrations/versions/0004_typed_marking.py`
- `src/sms/schemas/scheme.py` — canonical pydantic models moved from `services/assignments.py` (`Question`, `MarkPoint`, `MarkSchemeEntry`, `Band`, `RubricCriterionBands`) + `PaperExtract`, `SchemeExtract`, `RubricExtract` IO schemas.
- `src/sms/schemas/marking_v2.py` — `PartMark`, `AllocationMark`, `RubricMark`, `MarkedScriptV2`, `ReviewVerdictV2`, `ReviewedScriptV2`, `MarkingInputV2`, `ReviewInputV2`.
- `src/sms/agents/paper_extractor.py`, `src/sms/agents/scheme_extractor.py`, `src/sms/agents/marker_v2.py`, `src/sms/agents/reviewer_v2.py`.
- `src/sms/subjects/scheme_prompts.py` — mark-scheme and rubric prompt config (shared across subjects).
- `src/sms/pipeline/marking_pipeline_v2.py`
- `src/sms/worker/extract_jobs.py` — `run_paper_extract_job`, `run_scheme_extract_job`.
- `src/sms/records/builder.py` (pure), `src/sms/records/docx.py`, `src/sms/records/xlsx.py`, `src/sms/records/bundle.py` (zip).
- `src/sms/web/routers/records.py`; `src/sms/web/services/pages_cleanup.py`.
- Tests mirroring each module under `tests/unit`, `tests/integration`, `tests/web`.

**Backend — modify**
- `src/sms/web/services/assignments.py` (import models from `schemas/scheme.py`; `delete_pages_after_marking`; scheme upload), `src/sms/web/routers/assignments.py` (`POST /{id}/scheme`, `POST /{id}/extract/{paper|scheme}`, `GET /{id}/extract`), `src/sms/worker/worker.py` (dispatch `paper_extract`, `scheme_extract`; nightly page sweep), `src/sms/worker/mark_job.py` (choose v1/v2; delete pages on done), `src/sms/web/services/submissions.py` + `queue.py` (v2 serialisation; delete on last resolve), `src/sms/web/routers/pages.py` (410), `src/sms/providers/settings.py` + `routers/settings.py` (`delete_pages_after_marking` global default), `src/sms/pipeline/router.py` (`scheme_prompt_config`).

**Frontend — create**
- `web/src/pages/AssignmentEditor.tsx` (routes `/assignments/new`, `/assignments/:id`), `web/src/components/{QuestionsTable,MarkSchemeTable,RubricTable,AllocationPicker,BandPicker}.tsx`, `web/src/lib/scheme.ts` (shapes, validation, totals), tests.

**Frontend — modify**
- `types.ts` (v2 marks, template fields, extract status), `Assignments.tsx` (New assignment → editor; open row → editor), `NewSubmission.tsx` (assignment-first flow), `SubmissionDetail.tsx` (v2 parts, download button, pages-deleted state), `Review.tsx` (allocation/band pickers), `Submissions.tsx` (bulk download), `Settings.tsx` (delete-after-marking default), `App.tsx`/`Nav.tsx`.

---

### Task 1: Migration 0004 + canonical scheme models + settings default

**Files:** create `0004_typed_marking.py`, `src/sms/schemas/scheme.py`; modify `services/assignments.py`, `providers/settings.py`, `routers/settings.py`, `routers/assignments.py` (body fields); tests `tests/unit/test_scheme_models.py`, `tests/unit/test_db_portability.py` (+1), `tests/unit/test_settings_store.py` (+1), `tests/web/test_assignments_api.py` (+2).

**Interfaces produced**
- Migration 0004: `assignment_templates.delete_pages_after_marking` bool nullable (NULL = follow global default); `settings.delete_pages_after_marking` bool not null default true; `pages.deleted_at` DateTime nullable; `submissions.marks_version` int not null default 1; `jobs` unchanged (kinds `paper_extract`/`scheme_extract` use `payload_json` `{"template_id": n}` and `dedupe_key` `paper:{id}` / `scheme:{id}`).
- `schemas/scheme.py`: the five batch-2 models moved verbatim (services import from here; keep names), plus `q_label(q_id) -> str` ("1a" → "1(a)", "2bii" → "2(b)(ii)"; `q1`→"Q1" fallback) and `scheme_total(kind, questions, scheme) -> int`.
- `Settings.delete_pages_after_marking: bool = True` round-trips through load/save/public_dict/PUT; templates accept `delete_pages_after_marking: bool | None`; `list/get_template` return it plus `effective_delete_pages` (template value or global default).

**Steps:** write the tests (model move keeps existing tests green; `q_label` cases; migration columns present; settings round-trip; template PUT/GET of the flag) → RED → implement → GREEN → full suite → commit `feat: migration 0004, canonical scheme models, delete-pages-after-marking setting`.

---

### Task 2: Paper & scheme extraction agents + jobs + API

**Files:** create `agents/paper_extractor.py`, `agents/scheme_extractor.py`, `worker/extract_jobs.py`; modify `worker/worker.py`, `services/assignments.py`, `routers/assignments.py`; tests `tests/integration/test_extract_agents.py` (factories build; stub-client run), `tests/unit/test_extract_jobs.py`, `tests/web/test_assignments_api.py` (+4).

**Interfaces produced**
- `PaperExtract(BaseIOSchema)`: `questions: List[Question]` — prompt: read the paper pages, list every question **and part** in order with `q_id` like `1a`, `1bii`, the full text, `max_marks` from the paper (0 if absent). `build_paper_extractor(client, model, model_api_parameters=None)`.
- `SchemeExtract(BaseIOSchema)`: `items: List[MarkSchemeEntry]`; `RubricExtract`: `items: List[RubricCriterionBands]`. `build_scheme_extractor(client, model, kind, questions: List[Question] | None, ...)` — for `mark_scheme` the prompt includes the question list so rows align by `q_id`; allocation labels M1/A1/B1/… preserved.
- `run_paper_extract_job(db, storage, settings_store, template_id, bucket=None)` → transcribes the template's paper pages (from `pages WHERE template_id`), writes `questions_json`; `run_scheme_extract_job(...)` → reads the scheme pages (`pages.kind = 'scheme'` — add nullable `pages.kind` text default `'student'` in 0004: values `student|paper|scheme`), writes `scheme_json`. Both record `error` on the job only (no separate runs table).
- API: `POST /api/assignments/{id}/scheme` (multipart, replaces scheme pages, kind `scheme`), `POST /api/assignments/{id}/extract/paper` and `/extract/scheme` → 202 `{job_id}` / 409 `already_running` (via `enqueue_unique`), `GET /api/assignments/{id}/extract` → `{paper: {status, error}, scheme: {status, error}}` from the latest jobs. Template dicts include `paper_page_ids`, `scheme_page_ids`.

**Steps:** tests first (job with a stub agent writes JSON; second extract 409; upload replaces; status endpoint) → implement → commit `feat: extract questions and mark schemes from uploaded pages`.

---

### Task 3: v2 schemas, prompts, agent factories

**Files:** create `schemas/marking_v2.py`, `subjects/scheme_prompts.py`, `agents/marker_v2.py`, `agents/reviewer_v2.py`; modify `pipeline/router.py`; tests `tests/unit/test_schemas_v2.py`, `tests/integration/test_agent_factories.py` (+2).

**Interfaces produced**
- `AllocationMark{label: str, got: bool, why: str}`; `PartMark{q_id, awarded: List[AllocationMark], total: int, justification: str, in_scheme: bool, confidence: float}`; `RubricMark{criterion, band, marks, descriptor_met: str, justification, confidence}`; `MarkedScriptV2{kind: Literal["mark_scheme","rubric"], parts: List[PartMark], rubric: List[RubricMark]}` with a validator that `total == sum(marks of got allocations)` for mark-scheme parts.
- `MarkingInputV2{extracted: ExtractedScript, questions: List[Question], scheme: List[MarkSchemeEntry] | List[RubricCriterionBands], notes: str, kind}`; `ReviewInputV2` same minus justifications; `ReviewVerdictV2{q_id (or criterion), verdict, adjusted: PartMark | RubricMark | None, reviewer_note}`; `ReviewedScriptV2{verdicts}`.
- `scheme_prompts.MARK_SCHEME` / `RUBRIC` dicts with marker/reviewer background/steps/output_instructions (mark exactly against the allocation; award M marks for method even if the final answer is wrong when the scheme allows; set `in_scheme=false` for a valid-looking method the scheme doesn't cover; never invent allocations). `SubjectRouter.scheme_prompt_config(kind)`.
- `build_marker_v2(client, model, kind, subject, db=None, model_api_parameters=None)` (keeps the rubric-notes/exemplar context providers), `build_reviewer_v2(...)`.

**Steps:** tests (validator; factories build with the stub client; prompt config keys) → implement → commit `feat: per-part marking schemas, prompts and agent factories`.

---

### Task 4: Pipeline v2 + worker dispatch + persistence

**Files:** create `pipeline/marking_pipeline_v2.py`; modify `worker/mark_job.py`, `agents/extractor.py` (optional `questions` in `ExtractionInput` — add `questions: List[Question] = []` and a prompt line "segment by these labels"; keep default behaviour when empty); tests `tests/integration/test_pipeline_v2.py`, `tests/unit/test_worker.py` (+2).

**Interfaces produced**
- `MarkingPipelineV2(db, extractor, marker, reviewer, feedback, kind, confidence_threshold).run(images, template: dict, submission_id) -> MarkingResultV2(run_id, extracted, final: MarkedScriptV2, escalations: Dict[q_id, reason], feedback)`.
- Merge rules per spec §2; `final_marks_json` = `{"version": 2, "kind": ..., "parts": [...], "rubric": [...]}`; `marking_runs.rubric_json` stores `{"scheme_kind", "questions", "scheme", "notes"}` for v2 runs; `submissions.marks_version = 2`; `teacher_queue` rows per escalated part with `reason` in {`illegible`, `not in scheme`, `reviewer escalated`, `low confidence`, `marker/reviewer disagree`}.
- `mark_job`: if the submission's assignment has `scheme_kind in (mark_scheme, rubric)` → v2 path (agents built with `build_marker_v2` etc., extractor gets `questions`); else v1 as today. Feedback input for v2 is adapted (per-part comments keyed by `q_id`).

**Steps:** tests with stub agents covering each escalation reason, `in_scheme=false`, rubric kind, persistence shape, v1 path unchanged → implement → commit `feat: per-part marking pipeline (v2) selected by assignment scheme kind`.

---

### Task 5: v2 serialisation for detail, list totals and review resolve

**Files:** modify `services/submissions.py` (`compute_totals_v2`, detail `parts`), `services/queue.py` (v2 items: `question_text`, `scheme_row`, `proposed: PartMark|RubricMark`), resolve accepts `{allocations: [{label, got}], reason}` or `{band, marks, reason}` and writes `criterion_scores_json` as the v2 shape; tests `tests/web/test_submissions_api.py` (+3), `tests/web/test_queue_api.py` (+3).

**Interfaces produced** (JSON): detail `marks_version`, `parts: [{q_id, label, question_text, scheme: {answer, marks|bands}, extracted, workings, awarded: [...], total, max, justification, in_scheme, confidence, escalated, reason, queue_id, teacher: {allocations|band, total} | null}]`; totals as today (range while pending). Queue item gains `marks_version`, `scheme_row`, `proposed`. Resolve for v2 validates labels against the scheme row / band against the rubric.

**Steps:** tests → implement → commit `feat: v2 marks in detail, list totals and review resolve`.

---

### Task 6: Marking record — builder, docx, xlsx, zip, endpoints

**Files:** `uv add python-docx openpyxl`; create `records/{builder,docx,xlsx,bundle}.py`, `routers/records.py`; tests `tests/unit/test_record_builder.py`, `tests/unit/test_record_docx.py` (open with python-docx, assert header text, table shape, "Teacher to review" cell, totals row), `tests/unit/test_record_xlsx.py`, `tests/web/test_records_api.py`.

**Interfaces produced**
- `build_record(submission_detail: dict, template: dict | None) -> Record{title, student, marked_at, model, rows: [RecordRow{label, scheme_answer, student_answer, justification, awarded: str, teacher: str}], total_awarded, total_upper, total_max, to_review_count, rubric_page: [...] | None}` — pure; v1 runs produce rows per question with criteria summarised; "(illegible)" and truncation at 600 chars; teacher-resolved parts show `"n / m (teacher)"`.
- `render_docx(record) -> bytes` (A4 landscape, 6-column table, shaded "Teacher to review", empty last column, totals rows); `render_xlsx(records) -> bytes` (sheets `Markbook`, `Rows`); `bundle_zip(records) -> bytes`.
- `GET /api/submissions/{id}/record.docx` (filename `<label>-marking-record.docx`), `POST /api/submissions/records.zip {ids}` → zip of docx + `markbook.xlsx`; 404 for unknown ids; 409 `not_marked` if a submission has no run yet.

**Steps:** tests → implement → commit `feat: per-student marking record (.docx) and bulk zip + markbook.xlsx`.

---

### Task 7: Delete student pages on done + nightly sweep + 410

**Files:** create `services/pages_cleanup.py` (`delete_submission_pages(db, storage, submission_id) -> int`, `sweep_done_submissions(db, storage, older_than_hours=24) -> int`); modify `worker/mark_job.py` (after `done`), `services/queue.py` (after last resolve → `done`), `worker/worker.py` (sweep once per hour), `routers/pages.py` (410 `gone` when `deleted_at`), detail serialisation (`pages_deleted: bool`); tests `tests/unit/test_pages_cleanup.py`, `tests/web/test_pages_api.py`, worker sweep test.

**Rules:** effective flag = template value if not NULL else settings default; only `kind='student'` pages; never delete a page whose `storage_path` is still referenced by another undeleted `pages` row (content-addressed sharing); set `deleted_at`, remove the file if unreferenced.

**Steps:** tests → implement → commit `feat: delete student pages once a script is done (with nightly sweep)`.

---

### Task 8: Frontend — assignment editor (wizard)

**Files:** create `AssignmentEditor.tsx`, `QuestionsTable.tsx`, `MarkSchemeTable.tsx`, `RubricTable.tsx`, `lib/scheme.ts` + tests; modify `Assignments.tsx` (primary "+ New assignment" → `/assignments/new`; row click → editor), `App.tsx`, `types.ts`.

**Behaviour:** Step 1 type segmented (Maths/Science mark scheme · Essay rubric · Quick mark); Step 2 sections: title; **Question paper** drop zone → upload → "Read questions" button (POST extract/paper) with polling of `GET /extract` → editable `QuestionsTable` (label, text, marks; add/remove/reorder; total); **Mark scheme** (drop zone + "Read mark scheme" → `MarkSchemeTable`: question & part / expected answer / allocations chips (label+marks) / notes; amber "no scheme row" per unmatched question) or **Rubric** (`RubricTable`: criterion, bands with marks + descriptor); **Notes** textarea; **Delete student pages after marking** checkbox (tri-state: follow default / on / off); Save (disabled with reason until valid per spec). Draft autosave on blur via PUT. Copy in plain sentences; red only on Save.

**Tests:** `lib/scheme.ts` (validation, totals, label matching), editor gating test, tables add/remove.

**Commit** `feat(web): assignment editor with question paper, mark scheme / rubric and notes`.

---

### Task 9: Frontend — marking flow, detail, review, downloads, deleted state

**Files:** modify `NewSubmission.tsx` (assignment-first: choose assignment → hides the criteria table when the assignment has a scheme; shows questions summary; Quick mark still shows criteria), `SubmissionDetail.tsx` (v2 parts table: label, scheme answer, extracted, justification, awarded chips, escalated pill; "Download marking record" secondary button; "Pages deleted after marking" state), `Review.tsx` (`AllocationPicker` checkboxes M1/A1… with marks, or `BandPicker`; reason; keyboard: digits toggle nth allocation), `Submissions.tsx` (checkbox column + "Download marking records" for selected or all shown), `Settings.tsx` (delete-after-marking default), `types.ts`; tests for the pickers and the detail v2 render.

**Commit** `feat(web): per-part marks in detail and review, marking-record downloads, deleted-pages state`.

---

### Task 10: Docs, live check, deploy

- README: assignment types, marking record, page deletion, new env-free settings; roadmap updated.
- Opt-in live test `tests/live/test_mark_scheme_live.py`: one real mark-scheme assignment (fixture paper + scheme + one script under `tests/fixtures/`) on the configured provider, asserting a v2 run and a rendered record.
- Push to `main` (Railway auto-deploy once the GitHub App has repo access; else `railway up`), verify `/api/health`, create one assignment on the live instance, mark one script, download the record.

**Commit** `docs: typed assignments and marking records`.

## Self-review

Spec coverage: §1 → Tasks 1, 2, 8; §2 → 3, 4, 5, 9; §3 → 6, 9; §4 → 1, 7, 9; §6 testing → every task + 10. Types consistent: `Question/MarkSchemeEntry/RubricCriterionBands` are the single source (Task 1) used by Tasks 2–6 and mirrored in `types.ts`; `PartMark/RubricMark` (Task 3) are what Tasks 4–6 and 9 serialise; `enqueue_unique` keys `paper:{id}`/`scheme:{id}` (Task 2) match the worker dispatch; `effective_delete_pages` (Task 1) is what Task 7 reads. No placeholders: each task names its files, interfaces, tests and commit.

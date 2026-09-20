# File submissions, Mother Tongue and Computing (slice 4) — design

**Date:** 2026-09-20 · **Status:** approved in conversation, pending implementation plan
**Builds on:** slice 3 (`2026-09-17-insights-telegram-models-design.md`): per-assignment models (`SettingsStore.for_template`),
classes and student hand-in (slice 2), the v2 per-part pipeline (`pipeline/marking_pipeline_v2.py`).

## Goal

Teachers and students can submit **Python (`.py`), Scratch (`.sb3`) and Excel (`.xlsx`) files — alone, together, or mixed
with photographed pages — and the app marks them by reading them (never running them). Two new subjects, **MT**
(Mother Tongue: Chinese, Malay, Tamil; handwritten) and **Computing**, each with a **default model chosen per subject**.
Across every subject, **an error costs marks exactly once**.

## A. Submissions made of files and pages

### A1. Input kinds

A submission's `input_kind` is derived from what was uploaded, never chosen: `pages` (only images/PDFs — today's
behaviour, untouched), `files` (only code/sheet files), `mixed` (both). Accepted file types: `.py`, `.sb3`, `.xlsx`, plus
`.zip` as a container that is expanded on upload (its images/PDFs count as pages, its `.py/.sb3/.xlsx` as files, anything
else is ignored and listed back). Files are accepted for **every** subject; the UI only offers them for Computing.

Limits: 12 files per submission, 2 MB per file, 60 pages (existing), 200 KB of rendered text per submission (see A3).
Rejections are per file with the file named: `bad_file` (type), `too_large`, `zip_nothing_usable`, `too_many_files`.

### A2. Storage

New table `submission_files` (migration 0011): `id`, `submission_id` (FK, cascade), `name`, `kind` (`py|sb3|xlsx`), `size`,
`sha256`, `stored_path`, `text_rendered` (nullable; filled at first render), `created_at`. `submissions.input_kind`
(text, default `pages`, backfilled). Files are stored under `PageStorage` beside pages (`files/<submission>/<n>.<ext>`).
The "delete student pages after marking" policy deletes files too; the rendered text stays in the marking record like a
transcription does, so records/CSV/Insights keep working after deletion.

### A3. Reading files — `sms/files/`

Renderers turn a file into plain text the marker can read. They never execute, evaluate or recalculate anything.

- `python.py::render(bytes) -> Rendered` — UTF-8 (fallback latin-1) source with 1-based line numbers; a leading note
  `syntax: ok` or `syntax: error at line N: <msg>` from `ast.parse` (parse only).
- `scratch.py::render(bytes) -> Rendered` — unzip, read `project.json`; per sprite (and Stage): variables, lists,
  broadcasts, then each script as indented block text from opcodes and inputs, e.g.
  `when green flag clicked` / `  repeat (10)` / `    move (10) steps` / `  if <touching [edge]?> then`. Unknown opcodes
  print as `[opcode]`. Costumes/sounds are counted, not dumped.
- `excel.py::render(bytes) -> Rendered` — `openpyxl` loaded twice (formulas, then `data_only` cached values); per sheet
  the non-empty cells in row order as `B4 = =SUM(B1:B3) → 42` (formula and cached value; value only when no formula),
  merged ranges, named ranges, charts (type and series range), data-validation and conditional-format counts. Macros
  (`.xlsm`) are not accepted.
- `Rendered{text: str, summary: str, truncated: bool}`; `render_all(files) -> List[Rendered]` applies the 200 KB budget
  (largest file truncated first, with a `… truncated: N more lines` marker) and sets `truncated`.

### A4. Text segmentation — one `ExtractedScript` per submission

`agents/text_segmenter.py::build_text_segmenter(...)` (atomic-agents, same shape as the vision extractor) with input
`TextSegmentInput{assignment_context, questions: List[Question], sources: [{name, text}]}` and output the existing
`ExtractedScript` — exactly one `ExtractedQuestion` per part when a question list is given; `transcribed_answer`
holds the relevant excerpt(s) prefixed by their source (`[program.py L12-30]`, `[results.xlsx Sheet1]`,
`[handwritten pages]`), `workings` the supporting context, `needs_human_transcription` when nothing in any source
addresses the part.

Pipeline (`marking_pipeline_v2.py::run`) gains a `files` argument:
- `pages` only → unchanged (vision extractor, cached by page hashes).
- `files` only → renderers → segmenter (cached by file hashes + question labels) → marker.
- `mixed` → vision extractor on the pages → its per-part text becomes one extra source named `handwritten pages` → the
  segmenter sees pages + files → one `ExtractedScript`. Marker, reviewer, merge, feedback, records, CSV and Insights
  are unchanged: they consume `ExtractedScript` as before.

A file that renders but maps to no part is not an error: the submission gets an `unmatched_files` note shown on the
detail page. A `truncated` render escalates the affected parts to *Needs you* with reason `input_truncated`.

## B. Subjects

`SubjectRouter.KNOWN_SUBJECTS` gains `mt` and `computing`; `assignment_templates.language` (nullable, migration 0011;
`zh | ms | ta`, required when subject is `mt`). Frontend `Subject` union and `subjectLabel` (MT, Computing) follow.

### B1. MT — Mother Tongue

Handwritten scripts photographed as today. `subjects/mt/prompt.py` provides marker/reviewer background: read the
script in the assignment's language, mark against the rubric bands or scheme rows exactly as written, keep the
scheme's vocabulary. **Student-facing feedback is written in the MT language**; teacher-facing justifications,
reviewer notes and Insights stay in English. The vision `ExtractionInput.assignment_context` carries the language
("Chinese (zh) — transcribe in the script's language, do not translate"). Feedback agent input gains
`feedback_language` (`en` default; `zh|ms|ta` for MT).

### B2. Computing

Files path plus photos. `subjects/computing/prompt.py` background: judge correctness against the task as stated,
logic and control flow, use of the required constructs, data handling and clarity; the marker reads only — it never
asserts runtime behaviour it cannot see, and when a scheme row needs execution to verify it says so and marks what
is verifiable (`confidence` lowered; reviewer may escalate). Excel: formulas are the work, cached values are the
evidence. Scratch: block structure is the work. All three scheme kinds apply.

## C. No double penalisation — every subject

Rule text in `scheme_prompts` marker steps (both kinds): *an error costs marks once, at the first part or criterion
where it occurs; later parts are marked on the work as it stands (error carried forward); the same slip is never
deducted under two criteria.* Reviewer prompts get an explicit check and `ReviewedScriptV2` gains
`double_penalties: List[DoublePenalty{error: str, q_ids: List[str]}]` (default empty). `_merge`: for each entry, the
deduction stays in the first listed part; later parts have the affected allocation restored (`got=True`,
`why="already penalised in <first>"`) or, for rubrics, keep the marker's band and add a note; when the reviewer's
adjusted marks cannot be reconciled the part escalates with reason `double_penalty`. Unit-tested on `_merge`.

## D. Model per subject

Table `subject_models` (migration 0011): `subject` PK, `provider`, `model`, `extractor_model` (nullable), `updated_at`.
Resolution when a job builds its settings: **assignment pin → subject default → global Settings**, in
`SettingsStore.for_template(tpl)` (the middle layer reads `subject_models[tpl.subject]`; a subject default whose
provider has no saved key is ignored with a log line). `stamp_run_model` already records what ran.

API: `GET /api/settings/subject-models` → `{subject: {provider, model, extractor_model} | null}`;
`PUT /api/settings/subject-models/{subject}` body `{provider, model, extractor_model?}` (400 `bad_subject`,
`no_key_for_provider`, `bad_model`); `DELETE …/{subject}` → Auto. Settings page → **By subject** table: one row per
subject, *Auto* or provider + model with the same picker as the assignment editor; hint text recommends a CJK-capable
vision model for MT and a code-strong model for Computing (not enforced). The assignment editor's Auto caption shows
the subject default when one exists ("Using Qwen · qwen3.6-vl from the MT default").

## E. UI

- **Student hand-in** (`web/src/student/HandIn.tsx`): for a Computing class assignment, *Add files* (`.py .sb3 .xlsx .zip`)
  appears beside *Take photo / Choose from gallery*; one ordered list (thumbnails for photos, name + size for files),
  one *Hand in*. Other subjects unchanged.
- **Teacher upload** (`ClassAssignmentPage`): the per-student drop accepts photos, PDFs and files together.
  **Bulk upload**: a `.zip` where each top-level file or folder starts with the register number (`07_amirah.py`,
  `07/…`, `7 - amirah/`); `POST /api/classes/{id}/assignments/{caid}/bulk/preview` returns matches, ambiguous and
  unmatched entries; `POST …/bulk` creates one submission per matched student (mixed kinds allowed). Existing
  hand-ins are not replaced unless `replace=1`.
- **Assignment editor**: subject select gains MT (with *Language*: Chinese / Malay / Tamil) and Computing; a Computing
  assignment shows "Students can hand in files (.py, .sb3, .xlsx) and photos".
- **Submission detail**: a *Files* block (name, size, kind, rendered text expandable, unmatched note) beside the page
  strip when both exist.
- **Settings**: the *By subject* model table (§D).

## F. Errors and limits

Per-file rejection codes as in A1; a zip with nothing usable is rejected whole. Rendering is pure Python on the
bytes: no `exec`, no formula recalculation, no macro evaluation; `.sb3` and `.xlsx` are opened with
`zipfile`/`openpyxl` on in-memory bytes with a 20 MB decompressed cap (`zip_bomb`). Segmenter failure retries like the
extractor and fails the job with the model error, never a stack trace.

## G. Out of scope

Running student code or tests; `.xlsm`, `.csv`, `.ipynb`, `.java`; Scratch 2 (`.sb2`); recalculating formulas;
per-student MT language (it is per assignment); translating existing English feedback.

## H. Testing

- Unit: each renderer on fixture files (a `.py` with a syntax error, a two-sprite `.sb3` with a broadcast, an `.xlsx`
  with formulas + cached values + a chart, a malformed `.sb3`), the 200 KB budget and truncation marker, zip expansion
  and the zip-bomb cap, the register-number matcher, `_merge` double-penalty handling, three-level model resolution
  (pin > subject > global; keyless subject default ignored), `input_kind` derivation.
- API: file upload validation codes, mixed upload creates one submission with pages + files, bulk preview/commit,
  subject validation (`mt` requires `language`), subject-model CRUD, `submission detail` exposing files.
- Pipeline: files-only and mixed runs end to end with mocked extractor/segmenter/marker/reviewer, asserting the
  segmenter receives the `handwritten pages` source only for mixed; MT feedback language reaches the feedback agent.
- Frontend: hand-in with one photo + one `.py`; bulk-upload preview; editor MT language select and Computing note;
  Settings by-subject table (Auto/pin, keyless providers disabled); submission detail Files block.

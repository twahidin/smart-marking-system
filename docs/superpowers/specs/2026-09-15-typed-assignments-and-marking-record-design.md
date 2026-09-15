# Typed assignments, per-part marking, marking records — design

**Date:** 2026-09-15 · **Status:** approved in conversation, pending implementation plan
**Builds on:** slice 1 (`2026-09-15-web-app-slice-1-design.md`) and batch 2 (assignment bank with
`scheme_kind`, `questions_json`, `scheme_json`, question-paper pages; run-reflection; Gemini provider).

## Goal

A teacher creates an assignment by choosing its **type**, uploading the **question paper**, the
**mark scheme** (maths/science) or **rubric** (essays), and **notes**; marks one or many scripts against
it; and downloads a **marking record** per student — a table that follows the mark scheme row for row,
with an empty column for the teacher's own mark. Uploaded student pages are **deleted once a script is
done**; the marking record is the artefact that remains.

## 1. Assignment creation (type-driven)

Route `/assignments/new` (and `/assignments/:id` to edit), replacing the JSON-only path from batch 2.

**Step 1 — Type.** Segmented control: *Maths / Science (mark scheme)* → `scheme_kind = mark_scheme`;
*Essay / open response (rubric)* → `scheme_kind = rubric`. (The batch-2 `criteria` kind stays as
"Quick mark" for a one-off worksheet with no paper.)

**Step 2 — Essentials** (all on one page, saved as a draft on every change):

1. **Question paper** — required. `DropZone` (PDF/JPG/PNG/HEIC) → `POST /api/assignments/{id}/paper`
   (batch 2) → a new `paper_extract` job transcribes the pages into `questions_json`:
   `[{q_id: "1a", label: "1(a)", text, max_marks}]`, parts included. The teacher sees an editable
   **Questions table** (label / text / marks) and corrects it; total marks shown.
2. **Mark scheme** (maths/science) — upload the MS as PDF/photo → `POST /api/assignments/{id}/scheme`
   → a `scheme_extract` job turns it into `scheme_json`:
   `[{q_id, answer, marks: [{label: "M1"|"A1"|"B1"|…, marks: 1, for: "…"}], accept: [...], notes}]`,
   aligned to `questions_json` by label; or type it into the **Mark scheme table** (question & part /
   expected answer / mark allocation / accept-reject notes). Unmatched rows are flagged amber
   ("Question 3(c) has no scheme row").
   **Rubric** (essays) — upload or type: `[{criterion, max_marks, bands: [{band, marks, descriptor}]}]`.
3. **Additional notes** — free text stored in `context` (e.g. "penalise missing units once"; "accept
   any correct method"; "ECF applies").

"Save" requires: type, ≥1 question, a scheme/rubric row for every question (mark scheme) or ≥1
criterion (rubric). Everything else can be a draft. Import/export JSON carries all of it.

**Mark a script** then asks only for the student's pages (+ label); subject/context/scheme come from
the assignment. A script can still be "Quick marked" with a criteria list (today's behaviour).

## 2. Per-part marking engine

Applies when the submission has an assignment with `mark_scheme` or `rubric`.

- **Extractor** receives the questions list (labels + text) and segments the student's pages by those
  labels; returns one `ExtractedQuestion` per **part** (`q_id` = part id), `needs_human_transcription`
  as today, plus `page_refs: [{page_index, region_hint}]` (which page the answer is on — used by the
  review queue and the record; region is best-effort text, not coordinates).
- **Marker** (mark scheme): for each part it gets the question text, the MS row (answer, mark
  allocation, accept/reject, notes) and the transcription; returns
  `{q_id, awarded: [{label: "M1", got: true|false, why}], total, justification, in_scheme: bool,
  confidence}`. `in_scheme = false` when the answer isn't covered by the scheme (different method,
  partially legible) — this always escalates.
  (rubric): per criterion → `{criterion, band, marks, descriptor_met, justification, confidence}`.
- **Reviewer**: same inputs minus the marker's justification (anti-anchoring, as today); per part
  APPROVE / ADJUST / ESCALATE.
- **Merge/escalation** rules (superset of today's): illegible → escalate; `in_scheme = false` →
  escalate; reviewer ESCALATE or disagreement → escalate; confidence below threshold → escalate.
  Escalated parts show **Teacher to review** everywhere (queue, detail, record).
- **Feedback**: unchanged for mark schemes (per-part comments); for rubrics it speaks in band
  language ("Band 4 for organisation because…").
- **Schemas**: new `MarkedPart`, `RubricMark` models beside the existing ones; `final_marks_json`
  stores the new shape with a `version: 2` field so slice-1 runs (version 1 / absent) still render.
- **Review queue**: rows are parts; the decision column shows the MS row's mark allocation as
  checkboxes (M1/A1…) or the rubric bands as a picker, plus the reason box. Totals per part.
- **Subject prompts**: `math`/`science` share the mark-scheme prompt module; `language` uses the
  rubric prompt module. The `SubjectRouter` gains `scheme_prompt_config(scheme_kind)`.

## 3. Marking record (download)

**Per student — `.docx`**, generated from stored data (no re-marking), A4 landscape:

Header: assignment title · student label · marked on · provider/model · totals (`awarded / max`,
with "n parts to review" when any are open).

Table, one row per question part in scheme order:

| Question & part | Marking scheme answer | Student's answer (extracted) | Justification | Awarded mark | Teacher's mark |
|---|---|---|---|---|---|

- Col 2: the MS `answer` plus the allocation labels (`[M1 A1]`); for rubrics, the criterion and the
  band descriptors.
- Col 3: the transcription (workings included, ≤ ~600 chars, "…" beyond); "(illegible)" when flagged.
- Col 4: the marker's justification, referencing the allocation ("M1 for the substitution; A1 lost —
  final answer 3.5 not 4"); for escalated parts the reason ("Answer not in the scheme — different
  method"; "Unclear handwriting"; "Marker and reviewer disagreed").
- Col 5: `2 / 2`, or **Teacher to review** (bold, amber shading) for escalated parts. If the teacher
  has already resolved it in Review, this shows the teacher's mark with "(teacher)" and col 6 stays
  empty.
- Col 6: empty (shaded header "Teacher's mark") — for the teacher to concur or overwrite on paper.
- Footer rows: Total awarded (excluding "to review" parts, shown as a range as in the app) / Total
  max; a blank "Teacher's total".
- Second page (rubric assignments only): the rubric with the awarded band per criterion.
- Never includes the student's page images.

**Bulk** — from the Submissions list, "Download marking records" for the selected/filtered scripts:
a `.zip` of the per-student `.docx` files plus **`markbook.xlsx`** (one sheet: student label, then one
column per part with the awarded mark or "Review", total, max; a second sheet with every record row
flattened — the same six columns plus student label — for departments that prefer Excel).

Endpoints: `GET /api/submissions/{id}/record.docx`, `POST /api/submissions/records.zip {ids: [...]}`.
Generated on request with `python-docx` and `openpyxl`, streamed, not stored.

## 4. Deleting uploaded pages

- Setting on the assignment: **Delete student pages after marking** (default **on**), plus a global
  default in Settings. Quick-mark scripts follow the global default.
- A submission's pages are deleted when it reaches **`done`** — i.e. marking finished with nothing to
  review, or the teacher resolved the last escalated part. While a part *Needs you*, pages stay so the
  review queue can show them. Deletion = remove the `pages` rows' files from the volume and set
  `pages.deleted_at`; page routes return 410 `gone` afterwards; the detail page shows "Pages deleted
  after marking" in place of the viewer. The extraction cache (text keyed by page hash) is kept.
- Question-paper and scheme pages belong to the assignment and are **not** deleted.
- A nightly sweep also deletes pages of any `done` submission older than 24 h in case the inline
  deletion failed (volume hiccup).

## 5. Out of scope (later)

Classes/students (slice 2), student hand-in, page sorter; editing the marking record in the app
(teacher's column is for paper/Word); OCR of the teacher's handwritten marks back into the app.

## 6. Testing

Unit: questions/scheme extraction parsing (fixture PDFs → expected JSON); per-part merge/escalation
rules incl. `in_scheme`; record builder from stored JSON (rows, "Teacher to review", teacher-resolved
marks, totals, range); docx/xlsx generation (open the file, assert table dimensions and key cells);
page deletion on `done` and on last-resolve; 410 after deletion.
API: assignment create/save gating; paper/scheme upload + extraction job status; record downloads
(content-type, filename, zip members).
Frontend: assignment wizard gating; questions/scheme tables; download buttons; "Pages deleted" state.
Live (opt-in): one real mark-scheme assignment end to end on the configured provider.

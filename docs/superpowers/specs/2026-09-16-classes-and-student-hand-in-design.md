# Classes, classlists, student hand-in and feedback (slice 2) — design

**Date:** 2026-09-16 · **Status:** approved in conversation, pending implementation plan
**Builds on:** slice 1 (`2026-09-15-web-app-slice-1-design.md`) and typed assignments / marking records
(`2026-09-15-typed-assignments-and-marking-record-design.md`). Mockups: `docs/design-handoff/`
(teacher T2–T7, student S1–S11).

## Goal

A teacher creates a **class**, uploads its **classlist**, sets an assignment from the bank to the class
with a due date, and pastes one link into Google Classroom. Students open the link on their phone,
type their register number, photograph their pages and **hand in**. The existing pipeline marks each
hand-in; the teacher clears the review queue, **releases feedback**, and downloads marks. Students then
read their marks and feedback on the same link.

## Approach

A hand-in **is** a `submissions` row (with the bank template as `assignment_id`) plus three nullable
columns linking it to the class assignment and the student. The worker, review queue, marking
records, page deletion, retry guard and "Marked by" stamp all keep working unchanged. A separate
student-submission table was rejected: it would duplicate everything the last two slices built.

## 1. Data model (migration `0007_classes`)

| Table | Columns |
|---|---|
| `classes` | `id`, `name` (text, e.g. "4E2 Mathematics"), `code` (text, unique, 4 chars), `archived_at` (datetime, null), `created_at`, `updated_at` |
| `students` | `id`, `class_id` (FK classes, cascade), `reg_no` (int), `name` (text), `last_seen_at` (datetime, null), `created_at`; unique `(class_id, reg_no)` |
| `class_assignments` | `id`, `class_id` (FK classes, cascade), `template_id` (int, the bank template; not a FK — the template can be deleted with `force`, see §7), `title` (text, copied from the template at set time, editable), `due_at` (datetime, null), `status` (`draft` \| `open` \| `released`), `allow_student_uploads` (bool, default true), `released_at` (datetime, null), `created_at`, `updated_at` |
| `submissions` (+) | `class_assignment_id` (int, null), `student_id` (int, null), `handed_in_at` (datetime, null), `source` (text, `teacher` \| `student`, default `teacher`); partial unique index `uq_submissions_student_assignment` on `(class_assignment_id, student_id)` where both are not null |

**Class code**: 4 characters from `23456789ABCDEFGHJKMNPQRSTUVWXYZ` (no 0/O, 1/I/L), generated with
`secrets.choice`, retried on collision. Codes are compared case-insensitively (input is upper-cased).
**Student ID** is `CODE-reg_no`, e.g. `CE4R-12`.

Class assignment **status** is set by the teacher (`draft` → `open` → `released`); "Marking" in the
mockups' pill is derived (open with at least one submission not yet `done`). A class assignment
inherits subject, scheme and notes from its template; changing the template later affects future
marking only (existing runs keep their snapshot).

## 2. Student identity and session

- `GET /c/:code` (SPA route) pre-fills the code; `/join` takes the whole `CODE-12`.
- `POST /api/student/lookup {code, reg_no}` → `{class_name, student_name, reg_no}` or 404
  `no_such_student` ("No student #37 in this class — check the number on your class list") / 404
  `no_such_class`. Archived classes and unknown codes answer identically. Goes through the login
  rate limiter (same bucket as teacher sign-in: per client IP + global cap).
- `POST /api/student/session {code, reg_no}` sets a second signed cookie **`sms_student`**
  (itsdangerous, same `SECRET_KEY`, 30-day max age, `HttpOnly`, `SameSite=Lax`) carrying
  `{class_id, student_id}` and updates `students.last_seen_at`. `DELETE /api/student/session` clears it
  ("Not me").
- `require_student` dependency resolves the cookie to the `students` row (401 `student_session` if
  missing/invalid, or the student/class was removed or archived). Teacher routes are untouched by this
  cookie; student routes never accept the teacher cookie.

## 3. Teacher API

All under `/api/classes`, teacher-only.

| Route | Purpose |
|---|---|
| `GET /api/classes` | list (unarchived first): `id, name, code, student_count, open_assignments, archived_at` |
| `POST /api/classes {name}` · `GET/PUT/{id}` (`{name}`) | create / read / rename |
| `POST /{id}/archive` · `POST /{id}/unarchive` · `POST /{id}/regenerate-code` | settings tab actions; regenerating invalidates the old link (student sessions keep working — they hold ids, not the code) |
| `POST /{id}/students/preview` (multipart `file`) | parse the CSV and return `{rows: [{reg_no, name, issues: []}], errors: []}` without saving |
| `PUT /{id}/students {rows: [{reg_no, name}]}` | replace the classlist (upsert by `reg_no`; students no longer listed are removed **only if they have no submissions**, otherwise kept and flagged `not_on_list`) |
| `GET /{id}/students` | `id, reg_no, name, submissions, last_seen_at` |
| `GET /{id}/assignments` · `POST /{id}/assignments {template_id, title?, due_at?, allow_student_uploads?}` | list / set an assignment from the bank |
| `GET/PUT/DELETE /{id}/assignments/{caid}` | read (with roster) / edit `title, due_at, allow_student_uploads, status` / delete (only while it has no submissions; 409 `in_use` otherwise) |
| `POST /{id}/assignments/{caid}/release` | release gate (§5); 409 `needs_you` with the count while any queue item is pending |
| `POST /{id}/assignments/{caid}/students/{student_id}/upload` (multipart `files`) | teacher hands in for one student (creates the submission, `source = teacher`) |
| `DELETE /{id}/assignments/{caid}/students/{student_id}/submission` | remove a hand-in so the student can redo it (deletes the submission and its pages/jobs) |
| `GET /{id}/assignments/{caid}/marks.csv` | `reg_no, name, <one column per part in scheme order>, total, max, status` — "Review" for pending parts, blank for not handed in |

**CSV classlist**: UTF-8 (BOM tolerated), header row required with columns `name` and `reg_no` in any
order, case- and whitespace-insensitive (`Reg No`, `reg_no`, `REGNO` all match). `reg_no` must be a
positive integer; issues are per-row (`missing_name`, `bad_reg_no`, `duplicate_reg_no`) and the
preview shows them inline; `PUT` rejects any row with issues (400 `bad_rows`).

**Roster** (in `GET .../assignments/{caid}`): one row per student — `student_id, reg_no, name,
pages, handed_in_at, late (bool), source, submission_id, status, total, total_upper, total_max,
needs_you_parts: [labels]` — with `status` one of `not_handed_in | handed_in | marking | needs_you |
ready | released`, plus `counts` for the progress strip. `late` = handed in after `due_at`.

**Hand-in → submission**: `create_submission(label=f"#{reg_no} {name}", assignment_id=template_id,
class_assignment_id, student_id, source, handed_in_at=now)` — the existing function gains those
keyword arguments; everything downstream (job enqueue, scheme_kind snapshot, no_scheme check) is
reused.

## 4. Student API

All under `/api/student`, `require_student` unless noted.

| Route | Purpose |
|---|---|
| `POST /lookup`, `POST /session`, `DELETE /session` | §2 (no session needed for the first two) |
| `GET /me` | `{class_name, code, student_name, reg_no}` |
| `GET /assignments` | the class's non-draft assignments: `id, title, due_at, status: to_hand_in \| handed_in \| checking \| feedback_ready, handed_in_at, allow_student_uploads` |
| `POST /assignments/{caid}/hand-in` (multipart `files`, ≤ 20 pages, same upload limits/types as teacher uploads) | creates the submission; 409 `already_handed_in` if one exists; 403 `uploads_closed` when `allow_student_uploads` is false or the assignment is not `open` |
| `GET /assignments/{caid}` | `status`, `handed_in_at`, page count; once **released**: `feedback` (`summary, strengths, improvement_plan, next_steps`), `total/max`, `questions: [{label, mark, max, comment, try_next, transcription, page_ids}]`, where `mark` is the final mark (teacher correction wins) — never the pipeline's reasons, confidence, or reviewer notes |
| `GET /pages/{page_id}` | the student's own page image (404 for anyone else's; 410 once deleted) |

Status mapping for a student: no submission → `to_hand_in`; submission not `done`/`needs_you` →
`handed_in`; marked but class assignment not released → `checking`; released → `feedback_ready`.

## 5. Rules

- **Draft** assignments are invisible to students. **Open**: hand-in allowed once per student, late
  allowed (roster shows "late"); marking starts on hand-in as it does for teacher uploads.
- **Release** requires zero pending `teacher_queue` items across the assignment's submissions and at
  least one marked submission (and the assignment must be `open`); it sets `status = released`,
  `released_at`. Release closes student hand-ins; pages the **teacher** uploads for a student after
  release are marked and shown to that student as soon as the script is `done` (no second release).
  There is no un-release.
- **Remove hand-in** (teacher) deletes the student's submission, pages, queue items and jobs; the
  student sees "To hand in" again.
- Student pages follow the existing delete-after-marking rule; the feedback screen shows the
  transcription when pages are gone.

## 6. Teacher UI

- **Nav**: `Classes` first, then Submissions, Assignments, Review, Learning, Settings.
- `/classes` — cards: name, code, students, open assignments; **New class** (name only) primary.
  Archived classes in a collapsed section.
- `/classes/:id` — header with code and **Copy link** ("Paste this into Google Classroom", copies
  `https://<host>/c/CODE`); tabs:
  - **Students** — empty state explains the CSV; drop zone / file picker → preview table (name, #,
    issues inline) → **Confirm classlist**; afterwards a table of `#, name, submissions, last seen`
    with **Replace classlist**.
  - **Assignments** — rows with status pill (`Draft`, `Open`, `Marking`, `Released`), due date,
    counts; **Set assignment** dialog: pick from the bank (search by title), title, due date,
    "Students can submit their own pages" toggle; created as `draft`, **Open** from the row.
  - **Settings** — rename, regenerate code (confirm: "the old link stops working"), archive.
- `/classes/:id/assignments/:caid` — mockup T6: title, due, parts/marks, status pill; buttons
  **Download marks CSV**, **Download marking records** (existing `.zip` for the roster's marked
  submissions), **Release feedback** (disabled with tooltip while "Needs you" > 0; confirm dialog).
  Progress strip (five cells, click filters); roster table with per-row **Upload pages** (drop
  zone dialog, for students without a hand-in), link to `/submissions/:id`, **Needs you · 1(a), 2**
  pill linking to `/review?item=`, **Remove hand-in** (confirm).
- **Submissions** page gains a `Class` column (`4E2 · #12`) and the record downloads keep working.
- **Assignments** (bank) delete dialog also says "set in N classes".

## 7. Bank template deletion

`submission_count` already guards deletion; add `class_assignment_count`. With `force`, the class
assignments keep their `template_id` but future hand-ins fail with 409 `template_deleted` and the
class assignment row shows "Assignment deleted from the bank — set it again". Existing runs are
unaffected (they carry their own scheme snapshot).

## 8. Student UI (phone first, 375 px, no teacher nav)

Routes under a separate layout (`StudentLayout`: brand, class/student name, "Not me?"):

1. `/c/:code` and `/join` — **Enter your number**: `CE4R-` prefix shown, numeric input (`inputmode=
   numeric`), **Continue**; errors in plain words. `/join` has a single input for the whole ID.
2. `/s/confirm` — "Are you **Tan Wei Ling**, #1 of 4E2?" — **Yes, that's me** / **Not me**.
3. `/s` — **Home**: list of assignments with title, due date and one of **To hand in** (primary
   button), *Handed in · marking*, *Marked — your teacher is checking*, **Feedback ready**.
4. `/s/a/:caid/hand-in` — camera (`<input type=file accept=image/* capture=environment>`) or gallery
   (multiple); thumbnails in order with **move up/down**, **retake**, **delete**; images are
   downscaled client-side to ≤ 2000 px on the long edge as JPEG (quality 0.85) before upload;
   **Hand in N pages**; done state "Handed in Tue 3:12 pm". A failed upload keeps the photos and shows
   "Couldn't hand in — check your signal and try again" with **Try again**. PDF is also accepted (some
   students scan with a phone app).
5. `/s/a/:caid` — **Waiting** ("Handed in Tue 3:12 pm. Marking usually takes a day. We'll show your
   feedback here." — no spinner) or **Feedback** (S6–S9): total with a block bar, summary, *What you
   did well*, *Question by question* (each expands to comment, "Try next", transcription or page
   image), *Work on next*, *Next steps*.

Copy never uses "escalation", "confidence" or "reviewer". Touch targets ≥ 44 px; body ≥ 16 px on
mobile; marks always shown as text (`3 / 5`), never colour alone. Reuses `tokens.css`.

## 9. Testing

- Unit: class-code generator (alphabet, length, uniqueness retry); CSV parser (header variants, BOM,
  duplicates, bad numbers, empty names); roster/status derivation; marks CSV shape.
- API: class CRUD + archive + regenerate; classlist preview/confirm/replace (keeps students with
  submissions); set/edit/open/delete class assignment; student lookup (404 wording, archived class,
  case-insensitive code, rate limited), session cookie scope (student A cannot read B's assignment,
  page or feedback), hand-in once / uploads closed / draft invisible, teacher upload for a student,
  remove hand-in, release gate (409 with pending queue; success; late hand-in after release), feedback
  hidden before release and complete after, marks.csv content, Submissions list Class column,
  template delete counts classes.
- Frontend (vitest): Classes list, class page tabs (CSV preview issues, copy link), class assignment
  page (strip filtering, release disabled, per-row upload), student enter/confirm/home/hand-in
  (reorder, failed upload keeps photos)/waiting/feedback.
- Postgres smoke: migration 0007 and the partial unique index.

## 10. Out of scope (slice 3)

Bulk-scan page sorter (T8); teacher student-detail with editable feedback (T9); blur detection;
Google sign-in; per-class learning memory; student-side re-hand-in without the teacher.

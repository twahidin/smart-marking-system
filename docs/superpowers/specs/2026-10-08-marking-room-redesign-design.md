# The Marking Room: playful redesign, live crew, student reflection

**Date:** 2026-10-08
**Status:** approved design (mockups: https://claude.ai/artifact/PNS4JympCNCkdkp14kEsGG)

## 1. Goal

Make marking visible and engaging without changing what the app does. Teachers watch three
characters (the Reader, the Marker and the Checker) work through a class set in a cosy voxel
"Marking Room", and can read what each one is thinking. Students read feedback from the same
crew on their phone and, within a window the teacher sets, submit one correction per part they
lost marks on; the Marker re-marks it and the teacher releases the new mark.

Three things ship together:

1. **A brighter visual system** applied across the app (colour, type, pill navigation).
2. **The Marking Room**: a live view of marking in progress, driven by real stage events from the
   pipeline, with a teacher-only thought panel per crew member.
3. **Reflect and correct**: a bounded student correction flow with AI re-marking and teacher release.

## 2. Decisions already made

| Question | Decision |
|---|---|
| What the thought bubbles contain | Real reasoning (marker justifications, reviewer notes, reader doubts), **teachers only**. Students see the crew working and the released feedback, never raw reasoning. |
| Limit on reflection | A **time window** per assignment (default 7 days after release) **and one correction per part** that lost marks. |
| Who marks corrections | The **AI re-marks** against the same scheme; the **teacher can override** and must release before the student sees the new mark. |
| Devices | **Laptops** get the 3D room; **phones** get a lighter 2D version of the same crew. Reduced motion and no-WebGL degrade to static. |
| Art direction | Cosy voxel classroom (reference: isometric low-poly office). Sprites generated on Artlist; palette lifted from them. |

## 3. What changes, by surface

### 3.1 Visual system (all pages)

- Tokens: cream ground `#FFF7E6`, butter `#FFE8A3`, gold `#F2C94C`, mint `#9EDFC0`, green `#5CC9A0`,
  teal `#3E9E97`, coral `#F2836B`, oak `#E7B97C`, ink `#2B2A33`, muted `#5C5A66`.
  Crew colour code everywhere: Reader = green, Marker = coral, Checker = gold. Lost / warning / full
  marks reuse the same three.
- Type: Fredoka 700 for headings, marks and names; Nunito 400/700 for everything else. Google Fonts.
- Shapes: 16 to 24 px radii, pill buttons and nav, 2 px ink borders on chips, soft warm shadows.
- Pages that stay structurally as they are, recoloured: Assignments and editors, Classes, Settings,
  Records, Insights, Sign in and Setup. The playful layer lives where waiting happens: hand in,
  marking in progress, reading feedback.

### 3.2 Teacher: the Marking Room (replaces the Submissions list as the default landing)

- Header: class set picker, counts (sorted / read / marked / checked), elapsed time since the set
  started, "Needs you" count linking to Review.
- The room: on laptops a three.js scene (phase 2) or, in phase 1 and on phones, the isometric
  room image with positioned 2D sprites. Three desks with a name tag each; the tag shows the stage
  and the script on that desk. Scripts animate along the conveyor from the sorter to the Reader.
  A crew member bobs while busy and idles when the desk is empty.
- Clicking a name tag opens the **thought panel** (teachers only): the student on that desk,
  elapsed time on it, and timestamped notes for that crew member. Buttons: Show answer (the crop
  from the answer-crops feature) and Open in Review.
- "On the desks right now" list and the full queue below it, replacing the old Submissions table
  one for one (same filters, same links).
- Live updates arrive over Server-Sent Events; the page falls back to the existing 5 s polling
  when the stream is unavailable.

### 3.3 Teacher: Hand in (the sorter)

The upload page keeps its behaviour (photos, PDFs, .py/.sb3/.xlsx, class zip, browser downsizing,
register-number matching) and gains the sorter visual: files fall into the funnel, a progress
bar, three result tiles (photos / files / unsure), and the unmatched rows with "Pick a student".

### 3.4 Teacher: Review gains a Corrections tab

Each correction shows the original answer crop and mark, the student's correction (text or photo),
the Marker's re-mark with justification, the Checker's verdict, and three actions: Accept, Override
(enter a mark), Reject (with a one-line reason the student sees). "Release corrections" releases
every accepted or overridden correction of a class assignment at once; individual release is also
possible from the row.

### 3.5 Student: Feedback and Reflect (phone first)

- Feedback: mark, the crew's one-line summary, the "Reflect and correct · N days left" pill when the
  window is open, then parts. A part that lost marks shows "Try a correction · 1 left" while the
  window is open and no correction exists; after release it shows "After reflection: a / b".
- Reflect: the original answer crop and the Marker's comment, a "what went wrong" tag (sign slip,
  wrong method, rushed it, misread the question), corrected working typed or photographed (one
  photo, downsized in the browser as hand-ins are), and Send. After sending: "Sent to the Marker.
  Your teacher checks it before you see the new mark." Rejected: the teacher's reason and no retry.
- Delight, kept small: the crew nods when feedback opens, the Marker stamps a full-mark part, the
  "After reflection" badge pops in. All of it fades instead under reduced motion.

## 4. Architecture

### 4.1 Stage events from the pipeline

`MarkingPipelineV2.run` gains an optional `on_event: Callable[[StageEvent], None]`. It calls it at
the start and end of each stage, and once per part after the stages that produce per-part notes:

| Stage | Emitted when | Per-part note (teacher-only) |
|---|---|---|
| `read` | before/after `_extract` or `_segment` | extractor doubts (illegible, out of scheme, page located) |
| `mark` | before/after `marker.run` | `justification` per part |
| `check` | before/after `reviewer.run` | `reviewer_note` + verdict per part |
| `feedback` | before/after `feedback.run` | none |
| `done` | after `_persist` | escalation reasons per flagged part |

The worker's `run_mark_job` passes a recorder that writes each event to a new table and bumps
`submissions.stage`. A pipeline without a recorder (CLI, tests) behaves exactly as today.

```
marking_events(id, submission_id FK cascade, stage TEXT, kind TEXT 'started'|'finished'|'note',
               q_id TEXT NULL, note TEXT NULL, created_at DateTime default now())
index (submission_id, id)
submissions.stage TEXT NULL  -- 'queued'|'read'|'mark'|'check'|'feedback'|'done'; NULL for old rows
```

### 4.2 Room API (teacher)

- `GET /api/room?class_assignment_id=` → `{counts: {queued, read, mark, check, feedback, done,
  needs_you}, started_at, desks: [{stage, submission_id, student: {reg_no, name}, since}],
  queue: [...the existing submission list items...]}`. `class_assignment_id` optional (all open sets).
- `GET /api/room/events?class_assignment_id=&after=<event id>` → SSE stream of
  `{id, submission_id, stage, kind, created_at}` (notes are **not** streamed; they are fetched on
  demand). Heartbeat every 15 s. Honours `Last-Event-ID`.
- `GET /api/submissions/{id}/thoughts` → `{reader: [...], marker: [...], checker: [...]}` with
  `{at, q_id, note}` per entry, teacher session required. Returns 404 for a student session.

Implementation: a `RoomBroker` in the web process that the worker notifies through the existing
job store (the worker is embedded in the web service, so an in-process broker suffices; a
database poll every 2 s inside the SSE generator is the fallback when they are separate).

### 4.3 Corrections

```
class_assignments.reflect_days INTEGER NULL   -- NULL = follow settings.reflect_days (default 7); 0 = off
settings.reflect_days INTEGER NOT NULL default 7
student_corrections(id, submission_id FK cascade, q_id TEXT, reason TEXT, text TEXT NULL, page_id FK NULL,
            submitted_at DateTime, remark_run_id TEXT NULL, remark_total REAL NULL, remark_max REAL NULL,
            remark_note TEXT NULL, status TEXT 'submitted'|'remarked'|'accepted'|'overridden'|'rejected'|'released',
            teacher_total REAL NULL, teacher_reason TEXT NULL, error TEXT NULL, released_at DateTime NULL)
unique (submission_id, q_id)
```

(Named `student_corrections` because `teacher_corrections`, the teacher's Review decisions, already exists.
A correction photo is stored as a `pages` row with `kind = 'correction'`.)

Rules, enforced in a `student_corrections` service and covered by tests:

- A correction is accepted only when the class assignment is released, `now < released_at +
  reflect_days`, the part's mark is below its max, and no correction exists for that part.
- Submitting enqueues `remark_correction_job(correction_id)`: it builds a one-part extracted
  script from the correction text (or the OCR of the photo through the existing extractor), runs
  the marker and the reviewer with the assignment's scheme restricted to that part, stores the
  re-mark and note, and sets `remarked`. Failures leave `submitted` with an error the Review tab shows.
- The student sees status words only (sent, being re-marked, waiting for the teacher, released,
  rejected) until `released`, then `remark_total` or `teacher_total`.
- Records (.docx) and the marks CSV gain an "after reflection" column when any correction is released.

Student endpoints: `POST /api/student/assignments/{caid}/corrections` (multipart: `q_id`, `reason`,
`text` or one `photo`) → 201 with the correction row; `student_assignment` includes
`reflection: {window_ends_at, days_left, parts: {q_id: {can_correct, status, new_mark}}}`.

Teacher endpoints: `GET /api/review/corrections?class_assignment_id=`,
`POST /api/corrections/{id}/accept|override|reject`, `POST /api/class-assignments/{caid}/release-corrections`.

### 4.4 Front end

- `web/src/scene/` holds the room: `RoomScene2D` (phase 1: the isometric image as a backdrop,
  absolutely positioned sprite layers, CSS/Motion animation) and `RoomScene3D` (phase 2: three.js,
  lazy-loaded, GLB models). A `useDeviceTier()` hook picks `3d` on laptops with WebGL and fine
  pointer, `2d` on phones or no WebGL, `static` under reduced motion.
- Libraries: `motion` (transitions), `lottie-web` via `@lottiefiles/dotlottie-react` (crew sprites
  on phones), `three` (phase 2). Each is a dynamic import so Sign in, Settings and the student
  pages that do not need them keep today's bundle.
- Budgets: phase 1 adds under 250 KB gzipped to the teacher bundle and under 120 KB to the student
  bundle; the 3D scene (phase 2) stays under 1.5 MB of GLB and pauses when the tab is hidden.
- Assets: the four Artlist sprites in `web/public/art/` (room, crew sheet, sorter, student corner);
  phase 2 adds GLBs made with Artlist image-to-3D from the same sprites, optimised with
  gltf-transform. If the generated models are not good enough, phase 2 is dropped and the 2D room
  remains the laptop experience; nothing else depends on it.

### 4.5 Phasing

- **Phase 1 (this plan):** visual system, stage events + SSE, the 2D Marking Room with thought panel,
  the sorter visual on Hand in, corrections end to end, phone feedback and reflect screens, records
  column, guide update.
- **Phase 2 (separate plan, optional):** three.js room on laptops from approved GLBs.

## 5. Error handling

- Event recording never fails marking: the recorder swallows and logs database errors.
- SSE: on disconnect the client reconnects with `Last-Event-ID`; after three failures it switches
  to polling and shows nothing to the teacher (the room still updates, just less often).
- Correction re-mark failures surface in the Review tab as "Re-mark failed · mark it yourself", with
  Override available; the student still sees "waiting for the teacher".
- Window expiry during a submission: the server checks at submit time; a 409 shows "The reflection
  window closed" on the phone.

## 6. Security and privacy

- Thoughts and corrections review are teacher-session only; the student session cannot reach
  `/api/submissions/*/thoughts` or `/api/room*` (404, as for other teacher routes today).
- Correction photos are stored like hand-in pages (same storage, same retention: the answer crop
  of the corrected part is kept; the page follows the assignment's retention mode).
- No model reasoning is written into student-visible responses; `feedback_view` stays the only
  projection students get.

## 7. Testing

- Backend: stage events recorded in order with per-part notes (pipeline fed fakes); recorder failure
  does not fail the job; `/api/room` counts and desks; SSE endpoint streams and heartbeats;
  thoughts route teacher-only; corrections rules (window, one per part, below-max only, released
  only); re-mark job stores mark and note; accept/override/reject/release transitions; student view
  shows the right status words; records column; migrations on Postgres (chain test extended).
- Web: device tier hook; room panel renders desks from a snapshot and applies an event; thought
  panel switches crew member; feedback parts render "Try a correction" only when allowed; reflect
  form submits and shows the sent state; reduced-motion renders without animation classes.
- Manual on production after deploy: one class set marked while watching the room; one correction
  from a phone, re-marked, released, and visible.

## 8. Out of scope

Multiplayer avatars or chat with the crew, points or badges beyond the "after reflection" one,
student-visible model reasoning, moving the worker to a separate service, and the three.js scene
itself (phase 2).

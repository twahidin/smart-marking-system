# School scenes: Classes, Assignments, Review and Learning as places

**Date:** 2026-10-09
**Status:** implemented (plan: docs/superpowers/plans/2026-10-09-school-scenes.md; mockups: https://claude.ai/artifact/YKzFPxUW7yTkt6JvFRwW9E)
**Builds on:** `2026-10-08-marking-room-redesign-design.md` (phase 1, shipped)

## 1. Goal

Give the four remaining teacher pages the same warmth as the Marking Room, without changing what
they do. Each page opens on a painted voxel scene that is a real control surface, with the
existing list or table underneath it:

| Page | Scene | What the picture is |
|---|---|---|
| Classes | **The school** | One classroom tile per class, painted for its subject, on a campus that grows with the class list. The dotted plot is New class. |
| Assignments | **The teacher's desk** | Folders in a rack, tabbed by subject; the blank pad is New assignment; the pinboard shows what is due soon. |
| Review | **The marking desk** | The Checker at her desk: a flagged tray (Needs you), a ticked tray (ready to release), two drawers (Parts, Corrections). |
| Learning | **The library** | Shelves of approved rulings by subject, drafts on the reading table, worked examples on the notice board, a trophy for milestones. |

Everything in a scene is reachable from the plain list below it, so a teacher who ignores the
picture loses nothing.

## 2. Decisions already made

| Question | Decision |
|---|---|
| How the school grows | **Tiles.** One painted classroom tile per subject (Maths, English, Science, Mother Tongue, Computing, plus a plain one for classes with no subject). Tiles sit in a responsive grid on the cream ground; the dotted plot is always the next slot. The single painted four-room school is the empty state only. |
| Motion | **CSS and SVG overlays** on the stills, plus an optional **film loop** per scene (a 5 s muted mp4 made from the still, poster = the still). No three.js. |
| Labels | Hidden until hover or keyboard focus on laptops; tap pins one open. A **Show labels** switch opens them all and is remembered. A **Tour** button walks the labels one every 3 s, once round, then stops. Phones (coarse pointer) start with labels on. |
| Where the data comes from | Existing endpoints wherever they already carry the numbers; three small additions where they do not (§4.3). |
| Art | Artlist Nano Banana 2.1, image-to-image from the Marking Room painting so the camera, palette and crew match. Backgrounds flood-filled to the cream token so tiles float on the page. |

## 3. What changes, by surface

### 3.1 Shared scene behaviour

- A scene is a card holding the painting (or its film loop), positioned **hotspots** and their
  **labels**, and ambient **effects**. Hotspots are real buttons or links with an accessible name;
  labels are the black pill tags from the Marking Room, with a subject or crew dot.
- Label states: off (opacity 0, lifted 20 %), on. A hotspot's label shows while it is hovered or
  focused, while it is pinned (tapped), while **Show labels** is on, and while the tour is on it.
- **Show labels** is a pill switch above the painting, stored in `localStorage` as
  `sms.scene.labels` (`"on"` | `"off"`). Default: on when the pointer is coarse, otherwise off.
- **Tour** cycles the hotspots in order, 3 s each, once round, then switches itself off; pressing
  it again stops it early. Hover and pin still work during a tour.
- Ambient effects are decorative (`aria-hidden`), CSS only, and keyed to data: a glowing doorway
  or lamp means something is open or in progress, a waving flag means something needs the teacher,
  bobbing dots mean marking is happening. Every effect is removed under `prefers-reduced-motion`
  (the `static` tier) and the film loop is never started there.
- The **film loop**, when a scene has one: a `<video>` over the still, `autoplay muted loop
  playsinline`, poster = the still, started only on the `2d` tier when `navigator.connection.saveData`
  is not set; a playback error or a missing file leaves the still. A **Film** switch next to Show
  labels turns it off for the session (`sessionStorage` `sms.scene.film`). Hotspots and effects sit
  above the video, so nothing changes for the teacher except that the painting breathes.
- Cues: a page can ask its scene to play a one-shot effect (a script sliding from the flagged tray
  to the ticked tray, a stamp thump, a book sliding onto a shelf). Cues last under 1.5 s, never block
  anything, and are skipped on the `static` tier.
- Phones: the scene keeps its aspect ratio and the grid below it stacks to one column; hotspot
  targets are at least 44 px.

### 3.2 Classes: the school

- Header: "Your school", "Every classroom is a class with its own hand-in code", a count pill
  (`N classrooms · M students`) and **+ Build a classroom** (the existing New class dialog, which
  gains an optional **Subject** picker).
- The campus: a grid of classroom tiles (`repeat(auto-fill, minmax(260px, 1fr))`, 1 column under
  480 px), one per live class in the current order (name), then the dotted **plot** tile that opens
  the same dialog. Each tile is a link to `/classes/:id`, with the class's name tag as its label
  (`4E2 Mathematics` · `4KEF · 4 students · 0 open`).
- A tile's painting is chosen by the class's subject: `math`, `language`, `science`, `mt`,
  `computing`, or `general` when the class has none. The subject is the one saved on the class, else
  the subject of its most recently set class assignment, else none.
- Tile state (from the classes list): `open_assignments > 0` lights the doorway and shows a paper
  stack; `marking > 0` bobs chalk dots over the teacher; `needs_you > 0` waves a small coral flag
  and the tag gains `· N need you`. Hovering a tile lifts it 6 px.
- Archived classes stay in the collapsed "Archived" list below, as plain cards; they do not get a
  tile.
- Empty state: the painted four-room school with the plot label "Build your first classroom" and
  the existing help text.
- The class page (`/classes/:id`) gains a **Subject** select beside the rename control so a tile
  can be changed later.

### 3.3 Assignments: the desk

- Header: "Your desk", the count pill (`N folders · M class sets`), the existing **+ New
  assignment**, Import JSON and Export JSON.
- The scene: the desk painting with hotspots on the **folder rack** (one per subject that has at
  least one saved assignment; label `Maths · 2 folders` and the first two titles), the **blank pad**
  (New assignment), the **pinboard** (class sets due within 7 days: `3N1 · Comprehension Unit 4 ·
  Fri`), and the **lamp** (lit while any script is on the desks in the Marking Room; label
  `Marking now · N scripts`, links to `/room`).
- Clicking a folder-rack hotspot filters the table below to that subject; a subject chip row above
  the table shows the active filter with a clear control, so the filter is visible without the
  picture. The pinboard links to the soonest class set; its label names it and lists the next two.
- Ambient: lamp glow when marking, notes fluttering on the pinboard when something is due within
  7 days, a paper tab peeking from a folder whose subject has an open class set.
- The table keeps every column and action it has today; rows gain a subject-coloured tab on the
  left and the table is restyled to the soft-card look.

### 3.4 Review: the marking desk

- Header: "The marking desk", two count pills (`N need you` coral, `M ready to release` mint).
- The scene: the Checker at her desk. Hotspots: the **flagged tray** (Needs you · N parts, opens
  the Parts tab), the **ticked tray** (Ready to release · M class sets; links to the first, its label names it and lists the rest), the **drawers** (Parts and Corrections tabs; the mint drawer's label carries
  `· N re-marked` while corrections wait), and the **Checker** (label explains what she does; links
  to the Marking Room).
- Cues: resolving a part slides a script from the flagged tray to the ticked tray; "Released N
  corrections" and a class release thump the stamp; the flag waves while anything needs the
  teacher.
- The Parts and Corrections tabs below are unchanged in behaviour; the tab buttons stay as the
  plain control and the drawers are a second way to reach them.

### 3.5 Learning: the library

- Header: "The library", count pills (`N active rulings · M examples`, `K drafts to approve`), the
  existing subject select and **Run reflection**.
- The scene: the library painting. Hotspots: the **shelves** (active rulings by subject; label lists
  the per-subject counts; clicking sets the subject select and filters both tables to it), the
  **reading table** (drafts: notes and exemplars not yet active; scrolls to the first draft), the
  **notice board** (exemplars; scrolls to that table), the **trophy** (total scripts marked, from
  `/api/stats` marker runs; purely informative).
- Ambient: the table lamp glows while drafts exist; stars twinkle on the trophy; a book slides onto
  a shelf as a cue when a note or exemplar is approved.
- The two tables gain a subject filter driven by the same select (today the select only chooses
  what to reflect on); rows show the subject's colour dot. The stats strip and Recent runs stay.

## 4. Architecture

### 4.1 Front end

- `web/src/scene/Scene.tsx`: the shared scene card. Props: `art` (still src), `film?` (mp4 src),
  `alt`, `hotspots: Hotspot[]` (`{ id, left, top, label, sub?, color?, href?, onPick? }`),
  `effects?: ReactNode` (absolutely positioned children), `cue?: { id: string; key: number }`,
  `tier: DeviceTier`, `tourable?: boolean` (default true). Owns hover, focus, pin, Show labels,
  Tour, Film and the cue class.
- `web/src/scene/useSceneLabels.ts`: the persisted Show labels preference and the coarse-pointer
  default. `web/src/scene/useTour.ts`: the 3 s cycle with cleanup on unmount and on stop.
- `web/src/scene/effects.tsx`: small presentational effects (`Glow`, `Flag`, `Dots`, `Paper`,
  `Stamp`, `Tick`, `Book`, `Star`) and their keyframes in `styles/app.css`, each `aria-hidden`.
- `web/src/scene/ClassTile.tsx`: one classroom tile (painting by subject, state effects, tag).
- Pages: `Classes.tsx`, `Assignments.tsx`, `Review.tsx`, `Learning.tsx` mount a `Scene` above their
  existing content; the Marking Room keeps `RoomScene2D` (it is live-event driven and already
  shipped) but shares the tag CSS.
- `useDeviceTier` is unchanged (`2d` | `static`). The film loop is a further gate inside `Scene`:
  `tier === "2d"` and film not switched off and `saveData` not set.
- No new libraries. `motion` is already present and is not needed for these effects.

### 4.2 Art

- Stills in `web/public/art/`: `tile-math.jpg`, `tile-language.jpg`, `tile-science.jpg`,
  `tile-mt.jpg`, `tile-computing.jpg`, `tile-general.jpg` (1:1, 1024 px, background flood-filled to
  `--cream`), `desk.jpg`, `review.jpg`, `library.jpg` (4:3, 1400 px), `school.jpg` (empty state).
  Each under 150 KB.
- Film loops, optional, in `web/public/art/film/`: `desk.mp4`, `review.mp4`, `library.mp4` and one
  per tile, 5 s, 1040 px wide, H.264, no audio, under 300 KB each. The code treats a missing file as
  "no film". Generating the loops costs Artlist credits (about 750 per clip) and is a separate,
  approved step after the stills ship.
- Hotspot coordinates are percentages of the painting's box, kept in one table per scene next to
  the page, as `RoomScene2D` does with `SPOT`.

### 4.3 Backend additions

- Migration `0015_class_subject`: `classes.subject TEXT NULL`.
- `GET /api/classes` rows gain `subject` (saved, else derived from the most recent class
  assignment's template, else null), `marking` (submissions on this class's assignments with status
  `queued` or `marking`) and `needs_you` (status `needs_you`). `POST /api/classes` and
  `PUT /api/classes/{id}` accept an optional `subject` validated against the known subjects.
- `GET /api/review/summary` → `{ needs_you, remarked, ready_to_release }`: pending queue items,
  student corrections with status `remarked`, and open class assignments that have at least one
  submission and none in `queued`, `marking` or `needs_you`.
- `GET /api/class-assignments/due?days=7` → `[{ id, class_id, class_name, title, due_at, status }]`
  for class assignments with `status = 'open'` and a `due_at` within the window, soonest first.
- Everything else the scenes show comes from existing routes: `/api/assignments`, `/api/room`
  (counts for the lamp), `/api/queue`, `/api/notes`, `/api/exemplars`, `/api/stats`.

### 4.4 Device tiers and budgets

- `2d`: effects, hover lift, film loops. `static`: still paintings, labels on, no effects, no video.
- Bundle: no new dependencies; the scene module is small and shared. Paintings are loaded lazily
  below the fold except the one on the current page.

## 5. Error handling

- A scene never blocks its page: if the summary or due-list call fails, the scene renders with the
  numbers it has and the page's existing error notice shows the problem once.
- A film that fails to play (`error` event, or `play()` rejecting) hides the video and leaves the
  still; nothing is logged to the teacher.
- A class whose subject is removed from the known list later renders the general tile.

## 6. Security and privacy

- All four pages and the three new routes are teacher-session only, as today.
- Nothing new is stored about students; `needs_you` and `marking` are counts.

## 7. Testing

- Backend: classes list carries `subject`, `marking`, `needs_you` with the derivation rule; subject
  validation on create and rename; review summary counts under each status; due list window and
  ordering; migration 0015 on SQLite and Postgres (chain test extended).
- Web: `Scene` shows a label on hover, focus and pin; Show labels persists and defaults on for a
  coarse pointer; Tour advances every 3 s with fake timers, runs once round and stops, and clears
  its timer on unmount; film gate obeys tier, switch and `saveData`; `ClassTile` picks the painting
  by subject and applies state classes; each page renders its scene from mocked API data and the
  table or list beneath it unchanged; reduced motion renders no effect elements.
- Manual on production after deploy: build a classroom from the plot, filter assignments from the
  folder rack, settle a part and watch the script slide, approve a draft and watch the book shelve.

## 8. Out of scope

Three.js, Lottie, a student-side school, per-class film loops generated automatically, editing
class assignments from the pinboard, and moving the Marking Room onto the shared `Scene` component
(a later clean-up).

## 9. Phase differences

What shipped differently from this design:

- The Classes page has Show labels and Film but no Tour: its tiles are links, not a single painting.
- The paper-stack-on-the-desk and folder paper-tab effects are not built.
- A failed decoration fetch is silent rather than shown in the error notice.
- Tile films play only while the tile is in view, and at most six at once.
- The desk, marking desk and library have no film loop: at full width the generated clips looked soft and
  invented detail next to the crisp paintings, so those scenes animate with CSS effects only.

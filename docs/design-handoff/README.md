# Handoff: Smart Marking — Teacher and Student flows

## Overview
Teacher-facing screens for **Smart Marking**, a web app for a Singapore secondary school where AI agents mark handwritten scripts against a teacher's rubric. Teachers sign in, create classes, upload classlists, set assignments, watch marking progress, resolve low-confidence questions in a review queue, release feedback and download marks. The marking engine already exists; these screens are the UI over it.

Full product brief: `smart-marking-claude-design-prompt.md` (bundled). This package covers the teacher flow (T1–T9), the student flow (S1–S11) and a component sheet (C).

Screenshots of every artboard are in `screenshots/` (1× PNG, named by artboard id).

## About the Design Files
`Smart Marking - Teacher.dc.html`, `Smart Marking - Student.dc.html` and `Smart Marking - Components.dc.html` are **design references created in HTML** — static canvases of artboards showing intended look and copy. It is not production code. Recreate these screens in the target codebase's environment (React/Next, Vue, etc.) using its own component patterns. If no front end exists, a React + TypeScript app with plain CSS (the design system is plain CSS variables) is a sensible choice.

The artboards load the **Modernist** design system stylesheet (`_ds/modernist-.../styles.css`, bundled). Port its `:root` tokens and component classes (`.btn`, `.table`, `.input`, `.seg`, `.nav`, `.dialog`, `.tag`) into the codebase's styling layer rather than re-deriving values.

## Fidelity
**High-fidelity.** Colours, type, spacing, rules and copy are final. Match them closely. Only the "Settings" tab, hover/focus states and the loading states are implied rather than drawn — use the design system's built-in states (`:hover` tint from the accent ramp, 2 px accent `:focus-visible` ring).

## Design language (Modernist)
- Flat, architectural. **Zero border radius anywhere.**
- Ground `#f3f2f2`, surface `#eae9e9`, ink `#201e1d`, accent red `#ec3013`.
- Divider `color-mix(in srgb, #201e1d 40%, transparent)`; **2 px rules** separate major bands (header, progress strip, columns), 1 px rules between table rows.
- Everything flush left, including labels inside wide buttons.
- One font: **Archivo** (400 / 600 / 800). Headings 800, letter-spacing −0.015em, line-height 1.12.
- Photographs/scans render through `filter: grayscale(1) contrast(1.08)`.
- Icons: Lucide, stroke 2 (2.5 for small ones), on `currentColor`.

## Colour roles (product-specific)
- **Red `#ec3013`** — primary action only. One per screen. Hover `#dd2b0f`, active `#ae1800`. Red text on the light ground uses `#ae1800` (accent-700) for AA contrast.
- **Amber — "Needs you" only.** Fill `oklch(0.96 0.05 85)`, border `oklch(0.80 0.12 80)`, text `oklch(0.40 0.09 70)`, emphasis stripe `oklch(0.72 0.15 75)`. Always paired with the word "Needs you" and/or a Lucide `triangle-alert` icon — never colour alone.
- **Ink `#201e1d` solid** — finished states: Released, Ready to release.
- **Grey `#eae7e7` (neutral-200)** — in-progress states: Marking, Submitted.
- **Outline** — Draft (1 px divider border) and Open (1 px red border, `#ae1800` text).
- Secondary text `#5c5958`; tertiary/placeholder `#7d7979`.

## Shared chrome
**Top nav** (`.nav`): 14 px 48 px padding, 2 px bottom rule. Brand "Smart Marking" 800/18 px, links "Classes", "Help" 14 px (current = red), right: 28×28 ink square with initials "SR" + "Mr Rahman".
**Page header**: 32 px top padding, breadcrumb link 13 px ("← Classes"), H1 34–36 px, actions right-aligned at the baseline. 48 px horizontal gutter throughout at 1440; 32 px at 1024.
**Tabs**: 15 px, 28 px gap, 12 px vertical padding, 2 px bottom rule; current tab 600 weight with 2 px red underline.
**Status pill**: inline-flex, 12 px, 3 px 10 px padding, leading 8×8 square swatch, no radius.
**Buttons**: min-height 44 px (40 px for in-table controls, 48 px for form footers), 14–15 px, weight 800. Primary = red fill / ground text; secondary = 1 px divider border; ghost = red text.
**Table** (`.table`): th 11 px uppercase, 0.08em tracking, 60% ink, 2 px bottom rule; td 8 px padding (16 px on tall rows), 1 px rule; row hover 4% ink tint. Numbers `font-variant-numeric: tabular-nums`. Student IDs and class codes in `ui-monospace`.

## Screens

### T1 Sign in — 1440 × 820
Two columns: 560 px form panel (2 px right rule) + photo panel.
Form: brand top-left; vertically centred block: H1 "Sign in" 36 px; sub "Teachers only. Students use the class link their teacher shares." 15 px `#5c5958`; secondary block button 48 px "Continue with school Google account" (Lucide icon leading, label flush left); "or" divider (1 px lines, 12 px text); Email + Password fields (label 13 px, input 44 px / 15 px, surface fill, 1 px divider border); primary block button "Sign in"; link "Forgot password" 13 px. Footer 12 px `#7d7979`: "Ministry of Education Singapore · Bukit View Secondary School".
Right: 56/64 px padding; grayscale photo placeholder 420 px tall; caption 22 px/600: "Handwritten scripts marked against your rubric. You check the doubtful ones, then release."

### T2 Classes — 1440
Header H1 "Classes", sub "2026 · Term 3", primary button "+ New class" right.
Table columns: Class (38%, name 600 + 13 px grey sub-line), Code (mono 16 px, 0.08em), Students, Open assignments (count + grey titles), Needs you (amber pill "4 questions" with icon, else "—"), trailing "→". Row padding 16 px. Archived class row in `#7d7979`.
Rows: 4E2 Mathematics / CE4R / 40 / 2 (Worksheet 3, Trigonometry quiz) / 4 questions; 4E1 Mathematics / M7PK / 38 / 1; 3NA2 Mathematics / XU8H / 32 / None open; 4E2 Mathematics (2025) archived / 41.

### T3 Class page · Students · empty + CSV preview dialog — 1440
Class header: H1 "4E2 Mathematics"; right, a 1 px bordered code box: "CLASS CODE" 11 px uppercase over "CE4R" 26 px/800 0.1em; 1 px vertical divider; "CLASS LINK" over `smartmarking.sg/c/CE4R` mono 14 px; primary button "Copy link" (Lucide `copy`). Tabs: Students (current) / Assignments / Settings.
Body: 2-column grid, 64 px gap, 48 px padding. Left: H2 "No students yet" 26 px; copy explaining CSV with `name` and `reg_no` codes (inline code = neutral-200 fill, 2 px 6 px); `<pre>` sample (white, 1 px border, 13 px/1.6, 320 px max); link "Download a blank template". Right: 2 px dashed drop zone, min 320 px, content left-aligned: upload icon 32 px, "Drop your classlist here" 18 px/600, "CSV or Excel, up to 1 MB" 14 px grey, secondary button "Choose a file".
Dialog (`.dialog-backdrop` 50% neutral-900; dialog 760 px, ground fill, 28 px padding, top-aligned 120 px): title "Check your classlist" 24 px; meta "4E2_classlist.csv · 40 rows found"; amber notice with icon: header-case warning + "2 rows need fixing before you can confirm."; preview table (#, Name, Reg no, note) max-height 330 scroll; problem rows amber-tinted `oklch(0.97 0.03 85)` with 13 px amber-text note ("Duplicate of row 4 — two students can't share #4", "Missing register number"); trailing "… 32 more rows, all fine". Footer: helper text left; Cancel / Edit rows (secondary) / "Add 40 students" (primary, **disabled** while errors exist).

### T4 Class page · Students · loaded — 1440
Same header; Copy link button now secondary with check icon: "Copied — paste this into Google Classroom".
Toolbar: "**40 students** · 37 have opened the class link" left; right: search input 260 px "Find a student", secondary "Replace classlist", "Add student" (40 px).
Table: # / Name (600) / Student ID (mono `CE4R-1`) / Submissions ("2 of 2"; "1 of 2 · Worksheet 3 not handed in" 13 px grey) / Last seen (grey; "Never opened the link" tertiary) / →. 8 rows + "… 32 more students".

### T5 Class page · Assignments + New assignment panel — 1440
Grid `1fr 520px`. Main: header with primary "+ New assignment"; tabs (Assignments current).
Table: Assignment (title 600 + "Maths · 5 questions · 25 marks" sub-line) / Due / Status pill / Handed in ("37 / 40") / Needs you.
Rows: Worksheet 3 — Marking (grey) — 37/40 — amber "4 questions"; Trigonometry quiz — Open (red outline) — 12/40; Indices and standard form — Worksheet 2 — Released (ink) — 40/40; Simultaneous equations — Worksheet 1 — Released; Coordinate geometry — Worksheet 4 — Draft (outline), row text grey, sub "rubric not set".
Side panel (white, 2 px left rule, 32/40 px padding, 20 px gap): "New assignment" 24 px + 40 px icon close button; Title input (44 px); 2-col: Subject segmented control (Maths ✓ / English / Science, 10 px 12 px padding, full width) + Due input; Rubric header with link "Upload JSON instead"; criteria table Q / Criterion / Description / Max (right) with 5 rows (Factorise 4, Complete the square 5, Formula 5, Word problem 6, Sketch 5), footer "+ Add criterion" link and total 25 (600); toggle row between 1 px rules: "Students can submit their own pages" 600 + sub "Off means you upload the scanned booklets yourself.", switch 48×28 red fill with 22×22 white square knob (no radius); footer buttons 48 px: secondary "Save as draft", primary "Open for hand-in" (flex 1, label flush left).

### T6 Assignment page — 1440
Breadcrumb "← 4E2 Mathematics"; H1 "Quadratic equations — Worksheet 3" 34 px; meta "Due Wed 10 Sep · 5 questions · 25 marks" + grey "Marking" pill. Actions right: secondary "Bulk upload scans" (upload icon), secondary "Download marks CSV" (download icon), primary "Release feedback" **disabled** with tooltip "4 questions still need you".
**Progress strip**: 5 equal cells between 2 px top/bottom rules, 1 px rules between cells, 18/20/16 px padding; count 36 px/800 line-height 1, label 14 px grey below. Cells: 3 Not handed in · 2 Handed in · 6 Marking · **4 Needs you · 4 questions** (selected: amber fill, 4 px amber inset bottom stripe, `triangle-alert` icon 22 px, label 600) · 25 Ready to release. Each cell is a filter toggle.
Below: "Showing **4 students** with questions that need you" + link "Show all 40"; right primary "Open review queue" with key badge "4".
Roster table: # / Name / Pages / Handed in / Status / Total (right) / →. Status = amber pill "Needs you · Q3" (lists escalated questions). Total shows a **range** while a question is open: "15–17 / 25" (upper bound `#7d7979`). Row 31 handed-in text: "Uploaded by you, Wed 8:15 am".
Footer notes strip (1 px top rule, 4 columns, 14 px grey) with the release rules.
**Key badge** (`.key`): 11 px/600, 1 px divider border, 3 px 6 px, min-width 22 px; on red buttons white text with 50% white border.

### T7 Review queue — 1024 (iPad)
Toolbar (14/32 px, 2 px rule): "← Worksheet 3", "Needs you" 600, "1 of 4"; right: keyboard legend 12 px grey with key badges: ← → move · A accept · 1–5 set mark · ↵ save & next.
Two equal columns, 2 px rule between.
**Left (evidence)**: STUDENT label 12 px uppercase → "Muhammad Danish Bin Rosli · #2 · 4E2" 18 px; "PAGE 3 · Q3 (CROP)" → grayscale page crop 300 px tall, 1 px border; buttons Zoom / Whole page / Rotate (40 px secondary); "WHAT WE READ" → transcription box (white, 1 px border, 15 px/1.6); amber note "**Why this is here** — …" 14 px.
**Right (decision)**: "QUESTION 3 · FORMULA" + question text grey; criteria table Criterion / Proposed (right) / Your mark (88 px, right): each row has criterion 600 + quoted evidence 13 px grey; proposed "1 / 1"; input 56 px wide, 40 px tall, right-aligned. Uncertain row amber-tinted, evidence text amber, proposed "0–1 / 1", input empty with placeholder "?" and red border. Footer row: "Question total" 600, proposed "4–5 / 5", your total 18 px/600 "4 / 5". Textarea "Reason (goes into the student's feedback)" 72 px min. Footer (2 px top rule, 48 px buttons): secondary "← Previous", secondary "Accept proposed [A]", primary "Save & next [↵]" flex 1, label left and key badge right.
Keyboard: ←/→ previous/next card, A accept all proposed, 1–5 set focused criterion mark, Enter save & next.

### T8 Bulk upload · page sorter — 1024
Toolbar: "← Worksheet 3", "Sort scanned pages" 600, "booklets_4E2.pdf · 158 pages · 12 unsorted"; right: secondary "Add more scans", primary "Start marking 146 pages" (disabled until unsorted = 0).
Grid `1fr 440px`, 2 px rule.
**Left — Unsorted pages**: header "Unsorted pages · drag onto a student, or type their # on the page" + note "We matched 146 pages by the register number written on page 1." 4-column grid of page cards, 12 px gap: grayscale page thumbnail (aspect 1/1.35, 1 px border, top-left ink tag "p.147") + 40 px input placeholder "#". States: dragging (2 px red border, −1.5° rotate, "dragging…"); too dark (dimmed thumb + amber note "Too dark to read — rescan"); typed "31" (red border); blank page ("Blank page" label + secondary "Discard").
**Right — Students** list: header + 120 px "Jump to #" input; rows 14 px padding, 1 px rules: "#2 Name" 15 px + right meta "4 pages"; strip of 36×48 page thumbs, 6 px gap. Drop target row: accent-100 fill, 3 px red inset left stripe, meta "Drop here → page 4" in `#ae1800` 600, dashed 2 px red empty slot at end. Order problem row (#4 Lim Jun Hao): amber pill "Order looks wrong", thumbs numbered bottom-right (out-of-order pages amber-bordered and amber-numbered), ghost button "Fix order" (opens a reorder view — drag thumbs). Empty row (#7): grey text "No pages yet", dashed slot.

### T9 Student detail (teacher view) — 1440
Header: "← Worksheet 3"; H1 "Tan Wei Ling · #1 · 4E2" (suffix grey 400); meta "Quadratic equations — Worksheet 3 · handed in Tue 9 Sep, 3:12 pm · 4 pages"; right: "TOTAL" label + "18 / 25" (40 px/800, denominator 22 px grey) + ink pill "Ready to release".
Two equal columns under a 2 px rule.
**Left — Pages**: title + page-key pager (1 selected = ink fill); grayscale page 620 px tall.
**Right**: "Marks by question" + ghost "Adjust a mark"; table rows Q1 Factorise 4/4 p.1 · Q2 Complete the square 5/5 p.1 · Q3 Formula 3/5 p.2 · Q4 Word problem 3/6 p.3 · Q5 Sketch 3/5 p.4 (mark 600 right-aligned, page ref tertiary). Below a 2 px rule: "Feedback report" + secondary "Edit feedback" (Lucide `pencil`); summary paragraph; H6 "What you did well" bullets; H6 "Question by question" rows "Q3 · 3/5" (96 px label column) + comment with italic "Try next:". Copy is in the HTML file — use it verbatim as sample data.

## Student flow (phone first, 375 × 812; two screens also at 1024)

Students have no account. They open the class link (`…/c/CE4R`), type their register number, and are identified as "Tan Wei Ling · #1" on every screen with a "Not you?" link. Body text is never below 16 px; controls are ≥ 44 px (primary 52 px). The words escalation / confidence / reviewer / rubric never appear.

**Shared phone chrome**: 44 px status row; header (8/20/12 px padding, 2 px bottom rule) with brand 16 px/800 or a "← Assignments" back link 15 px on the left, identity 14 px `#5c5958` right-aligned; footer (2 px top rule, 12/20/28 px padding) holding the stacked 52 px buttons. Primary button labels are flush left with a trailing "→".

**Mark display**: number "3 / 5" (tabular, 600) plus a row of 10 px squares, filled ink for marks earned and outlined for marks missed. Never colour alone.

### S1 Enter your number
H1 "Enter your register number" 30 px; helper "It's the number next to your name on the class list." Input row 72 px tall, 2 px ink border: fixed prefix cell "CE4R-" (26 px/800, neutral-200 fill, grey text) + numeric input 40 px/800 on white (`inputmode="numeric"`). Link "Different class? Type the whole ID, like CE4R-1". Primary "Continue →". The numeric keypad is drawn to show layout; use the OS keyboard.
**S1b error**: input border amber, amber notice with `triangle-alert`: "No student #37 in this class — check the number on your class list. 4E2 has students 1 to 40." Button becomes "Try again →".

### S2 Confirm
Eyebrow "ARE YOU"; name 40 px/800; "#1 · 4E2 Mathematics" 20 px grey; 2 px rule; privacy line "Anyone with your class code and number can see your work, so keep them to yourself." Footer: primary "Yes, that's me", secondary "Not me — go back".

### S3 Home
H1 "4E2 Mathematics", "4 assignments". One block per assignment separated by 2 px rules: title 18 px/600, "Due Wed 10 Sep" grey, then one state:
- **To hand in** — primary block button "Hand in →".
- **Handed in · marking** — grey pill (ink 8 px swatch) + handed-in time right. After marking but before release the pill reads "Marked — your teacher is checking".
- **Feedback ready** — solid ink 52 px bar, "Feedback ready" 17 px/800 left, "22 / 30 →" right; the whole bar is the link.
Nothing else on this screen.

### S4 Hand in
Eyebrow assignment title, H1 "Hand in", helper "Photograph every page. Drag to reorder." 2-column page grid (`.pg`, gap 14/12 px): thumbnail 116 px tall, grayscale, 1 px border, ink number tag top-left; under each, ghost "Retake" and "Delete" (44 px, split row). States: **blurry** (2 px amber border, blurred thumb, amber note "Page 2 looks blurry — retake?", secondary "Retake page 2" on white); **dragging** (−2° rotate, red border, `--shadow-md`, "moving…"). Footer: secondary "Take photo" (Lucide `camera`) + "Gallery" (`image`) side by side, then primary "Hand in 4 pages →". Pages may be added in any order; order is whatever the strip shows at hand-in.

### S5 Handed in · waiting
H1 "Handed in" with `check` icon; 2-col fact strip between 2 px rules: WHEN "Tue 9 Sep, 3:12 pm", PAGES "4". Copy: "Marking usually takes a day. We'll show your feedback here." + "You can come back to this link any time. If you spot a missing page, you can add one until marking starts." 56 px thumbnail strip. Footer: secondary "Add a page", "Back to assignments". No spinner.

### S6 / S7 / S9 Feedback (one scrolling page)
Header right shows "Worksheet 3 · 18 / 25" once the total scrolls off. Order:
1. Eyebrow "Quadratic equations — Worksheet 3 · released Thu 11 Sep"; total "18" 64 px/800 + "/ 25" 26 px grey; 25-square row (18 filled).
2. Summary paragraph (2–3 sentences).
3. 2 px rule, H2 "What you did well" 20 px, bullets.
4. 2 px rule, H2 "Question by question": rows (`.qrow`, 14 px padding, 1 px rules) "Q3 · Formula" 600 left; right: squares + "3 / 5" + chevron. **Expanded (S7)**: comment; "Try next:" callout (white fill, 2 px ink left rule, 10/12 px padding); criteria table (criterion / mark, 6 px row padding); "YOUR PAGE 2" grayscale crop 76 px + link "Open full page".
5. 2 px rule, H2 "Work on next" — 3–5 bullets.
6. 2 px rule, H2 "Next steps" — numbered concrete actions.
7. Footer note grey: "Marked by Smart Marking and checked by Mr Rahman. If a mark looks wrong, ask your teacher in class." Buttons: secondary "See my pages", "Back to assignments".

### S8 Hand in · offline mid-upload
Full-width amber banner under the header (Lucide `wifi-off`): "**You're offline.** 2 of 4 pages are sent. The rest are saved on this phone and will go when you're back online." H1 "Handing in…". Page grid: sent pages show `check` + "Sent"; unsent pages at 60% opacity with "Waiting for signal". Copy: "Keep this page open, or come back later — your pages stay on this phone until they're sent." Primary "Try again now ↻". Store pending pages locally (IndexedDB) and retry on `online`.

### S10 Feedback — 1024 (iPad / Chromebook)
Same content, two columns under a 2 px rule (`1fr 400px`): report left (summary, "What you did well" as a 2-col bullet grid, question rows with the expanded question on white), the student's page right with a 1/2/3/4 page-key pager and the criteria table under it. Header carries brand + back link left, identity + "Not you?" right; total "18 / 25" 56 px in the page header. Breakpoint: ≥ 768 px.

### S11 Hand in — 1024 (iPad / Chromebook)
Page grid becomes 4 columns; primary "Hand in 4 pages →" moves to the page header. Right column (`360px`): "Add pages" — 2 px dashed drop zone ("Drop photos or a PDF here", "JPG, PNG, HEIC or PDF. Pages are added to the end.", secondary "Choose files"), secondary "Use the camera" (webcam via `getUserMedia`), and a grey hint that a phone photo is usually clearer and the same link works there.

## Component sheet (`Smart Marking - Components.dc.html`, screenshot `C-components.png`)
Every product-specific component with its states and values, in one 1440 sheet: colour roles; buttons (primary / disabled / secondary with icon / ghost / wide with key badge / phone 52 px / split ghost pair); status pills (Draft, Open, Marking, Handed in · marking, Marked — your teacher is checking, Needs you, Order looks wrong, Released, Ready to release, Feedback ready bar); student ID input (empty / focused / error) and the teacher class-code box; mark display (squares, totals, ranges, header sizes); rubric criteria table in authoring / review / reading forms; page thumbnails (strip, card, blurry, dragging, too dark, unsent, page-key pager); amber notices and empty states; progress strip and tabs. Build these as the shared components; the screens are compositions of them.

## Interactions & behaviour
- Progress strip cells filter the roster; selected cell shows the amber/ink fill and "Show all 40" clears.
- "Release feedback" disabled while any question is in "Needs you"; click → confirm dialog (`.dialog`) "Release feedback to 40 students?" → status Released; students see marks. Before release students see "Marked — your teacher is checking".
- "Copy link" copies `https://smartmarking.sg/c/CE4R` and swaps to the "Copied — paste this into Google Classroom" secondary state for ~3 s.
- CSV upload: accept header rows in any case/spacing (`Name`, `Reg No` → `name`, `reg_no`); show preview; block confirm while duplicates or missing reg numbers exist; "Edit rows" makes the two cells editable inline.
- Review queue: saving records per-criterion marks + reason, clears that question's escalation, advances. Range totals collapse to a single number when all questions resolved.
- Page sorter: drop appends the page to the student's strip at the highlighted slot; typing a register number does the same; "Start marking" enabled when unsorted = 0 and no order warnings (warnings can be dismissed).
- No hover-only affordances; all controls ≥ 40 px, primary ≥ 44 px.
- Student: the class link stores the confirmed `CE4R-1` in localStorage so returning students skip S1/S2; "Not you?" clears it. Unknown register number → S1b. Hand-in uploads pages one by one; the assignment moves to "Handed in · marking" only when all pages are sent.
- Student feedback rows toggle in place (one open at a time is fine); "Open full page" opens the page viewer with the page-key pager from S10.

## State
- Class: `{id, name, code, students[], assignments[], archived}`
- Student: `{regNo, name, id: code+'-'+regNo, submissionsCount, lastSeen}`
- Assignment: `{title, subject, due, rubric[{q, criterion, description, max}], studentsCanSubmit, status: draft|open|marking|released}`
- Submission: `{regNo, pages[], handedInAt, uploadedBy: student|teacher, status: notSubmitted|submitted|marking|needsYou|ready, marks[{q, criteria[{mark|null, proposed, evidence}], total, totalMax}], escalations[]}`
- Review card: `{submission, q, crop, transcription, reviewerNote, proposedMarks[], teacherMarks[], reason}`

## Design tokens
See `styles.css` `:root`. Key values: spacing 4/8/12/16/24/32; radius 0; shadows `--shadow-sm/md/lg`; type 42/32/25/20/16/13 (h1–h6), body 15 px/1.55 (screens use 15 px body, 13 px secondary, 11–12 px uppercase labels at 0.08em).

## Assets
- Lucide icons: `plus`, `copy`, `check`, `upload`, `download`, `triangle-alert`, `pencil`, `x`.
- Photo placeholders only (sign-in hero, page scans) — supply real grayscale imagery.

## Files
- `Smart Marking - Teacher.dc.html` — teacher artboards T1–T9 (open in a browser; requires the `_ds/` folder beside it).
- `Smart Marking - Student.dc.html` — student artboards S1–S11.
- `Smart Marking - Components.dc.html` — component sheet C.
- `screenshots/` — PNG of every artboard.
- `_ds/modernist-74c12b6c-c14e-4137-a9d0-95bc689f713c/styles.css` — design tokens + component CSS.
- `smart-marking-claude-design-prompt.md` — original product brief.

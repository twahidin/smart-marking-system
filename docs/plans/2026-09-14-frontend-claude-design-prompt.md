# Claude Design prompt — Smart Marking front end

Paste everything below the line into Claude Design.

---

Design the front end for **Smart Marking**, a web app for a Singapore secondary school. AI agents mark handwritten scripts (photographed or scanned pages) against a teacher's rubric and write each student a feedback report. Teachers set the work up and check the marking; students hand in and read their feedback. The marking engine already exists — design only the screens people touch.

## Two audiences, two devices

**Teacher — desktop and iPad first.** Signs in, creates a class, uploads a classlist, sets assignments, watches marking progress, resolves the questions the AI was unsure about, releases feedback, downloads marks.

**Student — phone first (375 px), no account.** Opens a link the teacher pasted into Google Classroom, types their class code and register number, photographs their pages, and later reads their marks and feedback. Sec 3–4 students on their own phones, often in a hurry, sometimes on a bus. Everything must work one-handed with a thumb.

## Identity: class code + register number

- A class gets a 4-character code from an alphabet with no ambiguous glyphs (no 0/O, 1/I/L): e.g. `CE4R`.
- A student's ID is `CE4R-1` — class code, hyphen, register number from the classlist.
- The class link `…/c/CE4R` pre-fills `CE4R-` so the student only types their number. A plain `…/join` page accepts the whole `CE4R-1`.
- After entry the app shows the name from the classlist — "Tan Wei Ling · 4E2 · #1" — with a clear "Not you?" so a wrong number is caught before anything is submitted.
- There is no password. Anyone with the code and number can see that student's work; that is an accepted trade-off. Do not design a login, email, or OTP for students.

## Teacher flow (design these screens)

1. **Sign in** — school Google account or email + password; one screen, nothing clever.
2. **Classes** — cards or rows: class name, code, student count, open assignments. "New class" is the primary action.
3. **Class page** with tabs:
   - **Students** — the classlist. Empty state explains the CSV: two columns, `name, reg_no`, drag-and-drop or pick a file, show a preview table before confirming, flag duplicate or missing register numbers inline. After upload: table of name, #, submissions, last seen. The class code and the share link sit at the top with a one-tap **Copy link** ("Paste this into Google Classroom").
   - **Assignments** — list with status pills: Draft, Open, Marking, Released. "New assignment": title, subject (Maths / English / Science), due date, rubric (upload a JSON file or fill a simple criteria table: criterion, description, max marks), and a toggle "Students can submit their own pages".
   - **Settings** — rename, archive, regenerate code.
4. **Assignment page** — the teacher's working view:
   - Progress strip: Not submitted / Submitted / Marking / Needs you / Ready — counts, click to filter.
   - Roster table: #, name, pages, submitted at, status, total mark, "Needs you" badge when any question was escalated.
   - **Bulk upload** for scanned booklets: drop many images or PDFs, then a page-sorting view where the teacher assigns page groups to register numbers (drag pages onto a student, or type the number). Order matters — pages out of order must be fixable here.
   - **Release feedback** — one button, with a confirm; before release students see "Marked — your teacher is checking" not marks.
   - **Download marks CSV**.
5. **Review queue** ("Needs you") — the questions the AI flagged as low-confidence, illegible, or disputed between marker and reviewer. One question per card: the student's page crop, the transcription, the rubric criteria with the AI's proposed marks and its quoted evidence, the reviewer's note, and a control for the teacher to enter the mark per criterion plus a short reason. Keyboard-friendly on desktop: next/previous, accept, adjust. This screen is where the teacher spends most time — make it fast and calm.
6. **Student detail** (teacher view) — the student's pages side-by-side with per-question marks and the feedback report; an "Edit feedback" affordance.

## Student flow (design these screens, phone first)

1. **Enter your number** — `CE4R-` pre-filled, big numeric-friendly input, "Continue". Errors in plain words: "No student #37 in this class — check the number on your class list."
2. **Confirm** — "Are you Tan Wei Ling, #1 of 4E2?" — Yes / Not me.
3. **Home** — the class's assignments as a list: each shows title, due date, and one of — **To hand in** (primary button), **Handed in · marking**, **Feedback ready** (highlighted). Nothing else on this screen.
4. **Hand in** — take photos with the camera or pick from gallery; thumbnails in order with drag-to-reorder, retake, delete; a gentle quality hint when a page is dark or blurry ("Page 2 looks blurry — retake?"); "Hand in 4 pages" button; a done state with a timestamp. Must still work if the student adds pages in the wrong order.
5. **Feedback** — the main student screen. Built from this data, in this order:
   - Total at the top: `18 / 25`, with a short 2–3 sentence summary in plain language.
   - **What you did well** — 2–4 concrete strengths.
   - **Question by question** — for each question: the mark (`Q3 · 3/5`), a comment, and "Try next: …" (a suggested action). Each question expands to show the rubric criteria with marks per criterion and the student's own page for that question.
   - **Work on next** — 3–5 practice areas.
   - **Next steps** — concrete actions.
   Marks must not rely on colour alone. No jargon: the words "escalation", "confidence", "reviewer" never appear on a student screen.
6. **Handed in, waiting** — a calm state: "Handed in Tue 3:12 pm. Marking usually takes a day. We'll show your feedback here." No spinner that implies it is happening right now.

## Design direction

- Light theme, plenty of white, one accent colour, a second colour reserved for "needs attention". Readable at arm's length on a phone; nothing smaller than 16 px body on mobile.
- Feel: a well-made school tool, not a startup dashboard — calm, direct, unhurried. Copy in short plain sentences, Singapore school vocabulary (class 4E2, register number, hand in).
- Touch targets ≥ 44 px. WCAG AA contrast. Works without hover.
- Show real-looking content: class **4E2 Mathematics**, code **CE4R**, assignment **"Quadratic equations — Worksheet 3"** with 5 questions worth 25 marks, students Tan Wei Ling #1, Muhammad Danish #2, Priya Nair #3, Lim Jun Hao #4. Use realistic mark distributions and feedback text a maths teacher would write.
- Empty, loading, error, and offline states for every screen — students will lose signal mid-upload; teachers will upload a CSV with a header row in the wrong case.

## Deliverables

- Student flow: 6–8 phone artboards (375 × 812).
- Teacher flow: 6–8 desktop artboards (1440 wide) plus the review queue and the bulk-upload page sorter at iPad width (1024).
- One component sheet: buttons, status pills, the student ID input, the mark display (`3/5`), the rubric criteria table, the page-thumbnail strip, empty states.

Out of scope: the marking agents themselves, a rubric editor beyond the simple criteria table, any student login, analytics or dashboards beyond the progress strip.

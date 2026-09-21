# Smart Marking System

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/smart-marking-1?utm_medium=integration&utm_source=button&utm_campaign=smart-marking)

**New here?** Read the [step-by-step setup guide](docs/setup-guide/README.md) (also as a [PDF](docs/setup-guide/Smart-Marking-Setup-Guide.pdf)) — every screen is the real app, from deploying on Railway to students reading feedback on their phones.

AI agents that mark, review, and give feedback on student scripts from images, built on [atomic-agents](https://github.com/eigenwise/atomic-agents). Agents get smarter and faster with every teacher correction.

## How it works

```
images -> Extractor (vision OCR, per-question transcription)
       -> Marker (per-rubric-criterion marks with evidence)
       -> Reviewer (independent second pass, anti-anchoring: marker rationale hidden;
                    APPROVE / ADJUST / ESCALATE verdicts)
       -> Feedback (student-facing report)
       -> SQLite
```

- **Escalation**: low-confidence or ambiguous questions land in a teacher queue. Use `--confidence-threshold` to escalate any question the Marker marks below a given confidence; illegible transcriptions are always escalated.
- **Smarter (learning loop)**: teacher corrections on the queue feed a nightly Reflection job that distills rubric notes and exemplar cases as *drafts*; the teacher approves them, and approved notes/cases are injected into Marker/Reviewer system prompts via atomic-agents Context Providers on every subsequent run.
- **Faster (speed loop)**: SHA-256 content-hash extraction cache (re-marks of the same image skip the vision call) and per-agent latency/token metrics recorded automatically via instructor completion hooks (`sms stats`).
- **Subjects**: math is fully supported (MVP); language and science ship with prompt data — add factories once validated.

## Quickstart

Smart Marking is a CLI first — the web app below is a friendlier front end over the same pipeline.

```sh
uv sync
export OPENAI_API_KEY=sk-...
sms mark script1.png script2.png --subject math --rubric rubric.json --db sms.db
```

Minimal `rubric.json`:

```json
{
  "criterion_defs": [
    {"id": "c1", "description": "Correct method", "max_score": 2},
    {"id": "c2", "description": "Correct final answer with units", "max_score": 3}
  ]
}
```

## CLI reference

| Command | Purpose |
|---|---|
| `sms mark IMAGES... --subject --rubric --context --db --model --confidence-threshold --provider --api-key` | Mark scripts from images |
| `sms reflect --subject --lookback --db --model --provider --api-key` | Nightly learning job |
| `sms evaluate --db` | Agent-teacher agreement % |
| `sms stats --db` | Per-agent latency/token metrics |
| `sms queue list --db` | List teacher escalations |
| `sms queue resolve QUEUE_ID --teacher-mark INT --reason --db` | Resolve an escalation; records the correction (agent mark recovered automatically) that feeds the learning loop |
| `sms notes list --db` | List rubric notes (draft/active) |
| `sms notes approve NOTE_ID --db` | Approve a draft note (draft -> active) |
| `sms exemplars list --db` | List exemplar cases (draft/active) |
| `sms exemplars approve EXEMPLAR_ID --db` | Approve a draft exemplar case (draft -> active) |
| `sms serve --host --port` | Run the web app (API + SPA + embedded worker) |
| `sms worker` | Run a standalone marking worker (for use alongside `sms serve --host 0.0.0.0` with `SMS_EMBEDDED_WORKER=0`) |

`--provider` on `mark`/`reflect` selects the LLM provider (`tokenrouter` \| `openrouter` \| `openai` \| `anthropic` \| `moonshot` \| `qwen` \| `google`); `--api-key` supplies its key. Both default to the configured provider/key when omitted.

## Web app

Smart Marking is also a web app: sign in with a shared teacher password, pick an LLM provider
(TokenRouter, OpenRouter, OpenAI, Anthropic, Moonshot/Kimi, Qwen, Google Gemini) and enter its API key
under **Settings** (keys are kept per provider, so switching provider switches key; a ✓ on the provider tile
means a key is saved), then set up an **Assignment** to mark against.

**Assignments** are created by type: a **mark scheme** (per-question-part allocations like M1/A1/B1,
for math/structured answers), a **rubric** (bands per criterion, for essays), or **criteria** (a flat
list of criteria, no paper — "Quick mark", for a one-off worksheet with no assignment to save). For a
mark-scheme or rubric assignment you upload the **question paper** and click **Read questions** to have
the AI transcribe every question and part (`1(a)`, `1(b)`, …); then upload the **mark scheme / rubric**
and click **Read mark scheme** to transcribe it row-by-row against those questions. Add free-text
**notes** for anything the marker should know (accepted alternatives, ECF, penalties). Saved
assignments are reused from **Mark a script**.

**Mark a script** is assignment-first: pick a saved assignment (or fall back to Quick mark's own
criteria list), upload the student's pages (PDF, JPG, PNG or HEIC), and the pipeline marks each
question part against the assignment's mark scheme or rubric. Low-confidence, illegible, or
out-of-scheme parts land in **Review**, where you resolve a mark-scheme part by ticking the allocations
earned (an **allocation picker**) and a rubric criterion by picking its **band** (a **band picker**).

Every marked script has a downloadable **marking record**: a `.docx` with a landing block (title,
student, marked-on date, model) and a table with six columns — question & part, marking scheme answer,
student's answer (extracted), justification, awarded mark, and a blank "Teacher's mark" column for
notes on paper or a moderation pass. A part still needing a teacher's decision shows **"Teacher to
review"** instead of a mark. From **Submissions**, select several scripts and download a **bulk `.zip`**
of one `.docx` per student plus a `markbook.xlsx` summary (one row per student, one column per
question/part, totals). The default provider is TokenRouter with `z-ai/glm-5.3-flash`; **Load models
from provider** on the Settings page lists every model your key can actually use (some TokenRouter keys
include the free `z-ai/glm-5.3-free`, limited to 8 requests/min).

**Page deletion**: student pages are deleted as soon as a script is done (marked with nothing left to
review, or the last escalated part resolved); the marking record keeps the transcription and every
mark. This follows the **"Delete pages after marking"** setting, defaulting on; an individual
assignment can override it (always keep / always delete / follow the default — a new essay (rubric)
assignment starts on "Off", since the whole transcription is what the record keeps). Question-paper
and mark-scheme pages are never deleted.

**Classes and student hand-in** turn marking into a class routine. Under **Classes**, create a class
and upload its classlist as a CSV (`name, reg_no`); the preview flags any bad rows before **Confirm
classlist** replaces the roster. Each class gets a four-character code and a link (`/c/CODE`) —
**Copy link** and paste it into Google Classroom once. Then **Set assignment** from the assignment bank,
with an optional due date, and **Open** it. Students open the link on their phone, type their register
number, photograph their pages (camera or gallery, reorder, up to 20 pages) and hand in; marking runs
as usual and the class assignment page shows a progress strip and a per-student roster (not handed in,
handed in, marking, needs you, ready — late hand-ins are flagged). Clear anything in **Review**, then
**Release feedback** — until then a student only sees that their work is in (or marked and being
checked); afterwards they see their marks and feedback on the same link. Releasing closes student
hand-ins; the teacher can still **Upload pages** for a student, and those are marked and shown to them
automatically. **Download marks CSV** gives one row per student;
**Download marking records** the bulk `.zip`.

There is no student password — the class code plus register number is the accepted trade-off, since
the link lives in a closed Google Classroom and a student can only ever see their own work. A student
who handed in the wrong pages asks their teacher, who clicks **Remove hand-in** on the roster so they
can redo it (a second hand-in is refused while the first stands); the teacher can also **Upload
pages** for a student who has no phone.

A class assignment page has **Roster** and **Insights** tabs. **Insights** turns a marked class set
into a class-level report: a marks-by-part chart (weakest parts highlighted), a most-lost-allocations
list, an AI narrative (summary, strengths, gaps, recommended next steps) and a students-to-support
table, plus score distribution. It (re)generates automatically when a class set's marking queue drains
and again on **Release feedback**, or on demand via **Regenerate**; **Download PDF** exports the same
report. The narrative is a single model call over anonymised samples — only register numbers reach the
model, never student names — and the app joins names back in for display. Before anything is marked the
tab shows "Nothing marked yet"; while a report is generating it polls and shows "Generating…".

**Telegram notifications** keep a teacher's phone in sync without checking back on the app. Create a
bot with [@BotFather](https://t.me/BotFather), paste its token under **Settings → Notifications** and
save, then open that bot in Telegram and press **/start** — the app polls Telegram for updates, so
nothing needs a webhook or a public URL, and pressing /start from a different chat later simply moves
the link there. Once linked, the bot sends instant messages for new hand-ins and for marking finishing
(with links straight to Review/Insights), plus a daily digest at a configured local time (default
`07:00` `Asia/Singapore`) summarising hand-ins, marks and what still needs attention across every class.
Instant messages can be turned off to keep just the digest. The **App URL** field controls the links
those messages use, defaulting to the deployment's Railway public domain. Messages are queued in an
outbox and flushed by the worker, so a slow or blocked bot never delays an upload or a marking job: a
refused send keeps its reason and is retried after a growing delay (20 s doubling to an hour), given
up after twenty attempts, and cleared from the outbox thirty days after it went.

**Model per assignment**: an assignment's editor has a **Model** section — **Auto — follow Settings**
(the default) or **Choose a model**, picking a provider (only providers with a saved key are
selectable; others show "No key saved") and a model, with an optional separate page-reading model. This
overrides the global provider/key for marking that assignment (and generating its Insights narrative);
the assignments list shows the chosen model as a caption. **My models**, on the Settings page, lets you
add custom model ids for OpenRouter and TokenRouter (with a label and whether the model reads pages) —
each one then appears in every model picker across the app, next to the curated list and whatever
**Load models from provider** returns.

**Files**: a submission can be made of files instead of, or alongside, photographed pages — Python
(`.py`), Scratch (`.sb3`) and Excel (`.xlsx`), or a `.zip` bundling any of those with images/PDFs (its
other contents are ignored and listed back). Files are read, never run: Python is shown as numbered
source with a parse-only syntax check, Scratch as each script's blocks in indented text per sprite, and
Excel as each sheet's non-empty cells with formula and cached value side by side, plus merged/named
ranges and charts; `.xlsm` (macros) is refused. A mixed submission runs its pages through the usual page
extractor first, then feeds every page and file through one text segmenter, so the marker always reads
text — never an image alongside a file. Limits: 12 files per submission, 2 MB per file, 20 MB per zip
once unpacked, 50 MB per upload overall (pages keep the existing 60-page cap). A file that renders but
answers no part is listed on the submission detail page rather than silently dropped; a file too large
to fit the marker's text budget sends its affected parts to **Review** as "input truncated" instead of
guessing from a cut-off excerpt.

**MT (Mother Tongue)**: Chinese, Malay or Tamil handwritten scripts, marked like any photographed
submission. An MT assignment also picks a **Language**, and student-facing feedback is written in that
language (Chinese, Malay or Tamil) while everything the teacher reads — justifications, reviewer notes,
Insights — stays in English. MT assignments need the language field, so create and edit them from the
assignment editor; Quick mark's one-off criteria list has nowhere to put a language and can't save one.

**Computing**: Python, Scratch and Excel submissions (with or without photographed pages) judged on
logic, control flow, the constructs the task asked for, data handling and clarity — the marker reads
the file, it never claims to have run it, and marks only what it can verify from what's on the page
when a scheme row needs execution to check (lowering its confidence so **Review** can weigh in). For
Excel the formulas are the work and the cached values are supporting evidence; for Scratch it's the
block structure.

**Model by subject**: beyond the global Settings model and an assignment's own pin, each subject can
have its own default under **Settings → By subject** — useful for picking a CJK-capable model for MT or
a code-strong one for Computing without changing what math or language assignments use. Resolution order
is **assignment pin → subject default → Settings**; a subject default whose provider has lost its saved
key is skipped in favour of Settings, with the assignment editor's Auto caption naming which one it's
actually using.

**No double penalisation**: across every subject, an error costs marks once — at the first question
part or rubric criterion where it occurs — and is carried forward as a given for every later part, never
deducted twice under two different marking points. The reviewer checks for this explicitly; where it
finds the marker deducted the same slip twice, the merge restores the later deduction (crediting the
allocation, or keeping the marker's rubric band with a note), or — where the two passes can't be
reconciled — sends the part to **Review** flagged "double penalty".

**Bulk upload**: from a class assignment page, **Bulk upload** takes one `.zip` of the whole class's
work at once — a top-level file or folder per student, named starting with their register number
(`07_amirah.py`, `07/…`, `7 - amirah/`). The zip is previewed before anything is created: matched
students and what each one will get, entries that didn't match a register number, and register numbers
that matched more than one student. Ticking **Replace existing hand-ins** lets the upload overwrite a
student who has already handed in; left unticked, that student is skipped and everyone else still goes
through. Photos inside a bulk zip are **not** downsized in the browser the way a single upload's are,
so the whole archive may unpack to at most 50 MB — past that, downsize the photos or split the class
into two zips.

### Settings

- **Delete pages after marking** — global default for the page-deletion behaviour above; an assignment
  can override it per-assignment.
- **Auto reflect** — whether the nightly reflection job (rubric notes / exemplar cases distilled from
  teacher corrections) runs automatically.
- **Notifications** — the Telegram bot token, linked-chat status with **Send test message** / **Unlink**,
  an instant-messages toggle, the daily digest time and timezone, and the App URL used in message links.
- **My models** — custom model ids for OpenRouter and TokenRouter, each shown with a label and whether
  it reads pages; they appear in every model picker (Settings, assignment editor) alongside the curated list.
- **By subject** — a default model per subject (math, language, science, MT, Computing), used when an
  assignment of that subject doesn't pin its own model; falls back to the global Settings model when a
  subject has none or its provider's key is gone.

### Run locally

```sh
uv sync
(cd web && npm ci && npm run build)
SECRET_KEY=dev TEACHER_PASSWORD=dev uv run sms serve
# open http://localhost:8000 — uses ./sms.db (SQLite) and ./data for page images
```

Frontend development with hot reload: `cd web && npm run dev` (proxies `/api` to :8000).

### Deploy on Railway

The quickest way is the marketplace template — https://railway.com/deploy/smart-marking-1 — which creates
the web service, a Postgres database and the `/data` volume, generates `SECRET_KEY` and
`TEACHER_PASSWORD` for you (read the password from the service's Variables, or set your own before
deploying), and leaves the model key for the Settings page. To set it up by hand instead:

One service (this repo, Dockerfile) + a Postgres database + a volume mounted at `/data`.

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `SECRET_KEY` | a long random string — signs sessions and encrypts stored API keys (changing it invalidates both) |
| `TEACHER_PASSWORD` | the password teachers use to sign in |
| `STORAGE_DIR` | `/data` |
| `LLM_PROVIDER` | optional — `tokenrouter` (default), `openrouter`, `openai`, `anthropic`, `moonshot`, `qwen`, `google` |
| `LLM_MODEL` | optional — defaults to the provider's default model |
| `LLM_API_KEY` | optional — pre-seeds the key for `LLM_PROVIDER` so the settings page can be skipped |

Health check: `/api/health`. The marking worker runs inside the web service; to run it separately,
add a second service from the same repo with start command `uv run --no-sync sms worker` and set
`SMS_EMBEDDED_WORKER=0` on the web service.

## The learning workflow

1. Mark scripts: `sms mark ...`
2. Review escalations in the queue and resolve them with your marks: `sms queue resolve ...`
3. Run the nightly reflection job: `sms reflect ...`
4. Approve the distilled notes and exemplar cases: `sms notes approve ...`, `sms exemplars approve ...`
5. Next runs are smarter — approved notes and exemplar cases are injected into agent prompts automatically.

Track progress with `sms evaluate` (agreement %) and `sms stats` (latency/tokens).

## Development

```sh
uv run pytest -q
```

The suite runs on SQLite. To also exercise the Postgres code paths (`RETURNING`, `FOR UPDATE SKIP
LOCKED`, aggregate and timestamp types), point `SMS_TEST_DATABASE_URL` at a scratch Postgres database
— migrations run against it and the smoke tests clean up the rows they create:

```sh
SMS_TEST_DATABASE_URL=postgresql://sms:sms@localhost:5432/sms_test uv run pytest tests/postgres -q
```

Two opt-in suites under `tests/live/` exercise real provider calls (skipped by default — nothing runs
in CI or a plain `pytest -q`):

```sh
# TokenRouter text + vision probe
SMS_LIVE_TESTS=1 TOKENROUTER_API_KEY=... uv run pytest tests/live/test_tokenrouter_live.py -q

# Full mark-scheme pipeline: paper -> scheme -> marking -> record, against whichever key is set
SMS_LIVE_TESTS=1 TOKENROUTER_API_KEY=... uv run pytest tests/live/test_mark_scheme_live.py -q
# (or OPENROUTER_API_KEY / GOOGLE_API_KEY — the test picks the first one it finds)
```

Project layout:

```
src/sms/
  schemas/    # pydantic + atomic-agents IO schemas
  agents/     # Extractor, Marker, Reviewer, Feedback, Reflection
  pipeline/   # end-to-end marking orchestration
  memory/     # SQLite store, extraction cache, metrics, context providers
  subjects/   # subject registry and prompts (math MVP)
  learning/   # nightly reflection job
docs/plans/   # design doc + implementation plan
```

See [docs/plans/2026-09-04-smart-marking-system-design.md](docs/plans/2026-09-04-smart-marking-system-design.md) for the full design.

## Status / roadmap

**Status**: MVP — math marking via CLI, plus a FastAPI + React web app (sign-in, settings, typed
assignments with mark-scheme/rubric editors and paper/scheme extraction from uploaded pages,
assignment-first marking, per-part review, downloadable marking records, automatic page deletion,
and classes with a student phone hand-in and released feedback).

Done since the original MVP:

- Typed assignments (mark scheme / rubric / criteria) with per-part marking, review, and downloadable
  marking records (`.docx`; bulk `.zip` + `markbook.xlsx`)
- Reading the question paper and mark scheme / rubric from uploaded pages (`Read questions` /
  `Read mark scheme`) instead of typing them in
- Classes and students (classlist CSV, class link, assignments set from the bank, per-student roster,
  marks CSV, feedback released per assignment)
- Student phone flow (students open the class link, type their register number, photograph and hand
  in their own pages, and see their feedback once released)
- Insights: per-class-assignment statistics, an AI narrative and a downloadable PDF, generated when a
  class set finishes marking, on release, or on demand
- Telegram notifications: own bot via `/start` linking (no webhook), instant hand-in/marking-finished
  messages and a daily digest
- Per-assignment model choice (provider, model, optional page-reading model) and "My models" — custom
  OpenRouter/TokenRouter model ids available in every picker
- File submissions (`.py`, `.sb3`, `.xlsx`, alone or zipped with photos) read and marked as text, never
  executed; MT (Mother Tongue: Chinese/Malay/Tamil, feedback in the script's language) and Computing
  subjects; a default model per subject (assignment pin → subject default → Settings); no double
  penalisation for the same error across every subject; class-wide bulk upload of one zip matched to
  students by register number

Roadmap:

- Bulk-upload page sorter (split a multi-script batch scan into per-student submissions when filenames
  don't carry a register number — bulk upload by filename has shipped)
- Per-class memory (rubric notes and exemplar cases scoped to a class, not just per subject)
- Language and science subject factories (prompts already ship)
- SymPy verification for math marking
- Ensemble marking

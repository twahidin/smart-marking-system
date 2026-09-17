# Insights, Telegram notifications, per-assignment models (slice 3) — design

**Date:** 2026-09-17 · **Status:** approved in conversation, pending implementation plan
**Builds on:** slice 2 (`2026-09-16-classes-and-student-hand-in-design.md`), per-provider keys (migration 0008).

## Goal

After a class set is marked, the teacher gets (A) an **Insights** page and PDF for the assignment — where
the class lost marks, what went well, what to teach next, who needs help — (B) **Telegram** messages when
marking finishes, when students hand in, and a daily digest with links, and (C) the ability to choose
**which model marks each assignment**, with their own model lists for OpenRouter and TokenRouter.

## A. Insights

### A1. Statistics (computed, no model call)

`services/insights.py::compute_stats(db, jobs, ca) -> dict` over every marked submission of the class
assignment (`run_id` set), using `get_submission` detail (v2 `parts`, v1 `marks`; teacher corrections
win, pending parts count as unresolved):

```
{
  "n_students": 40, "n_marked": 38, "n_pending": 3,
  "totals": {"mean": 15.2, "median": 16, "max": 25, "buckets": [{"from":0,"to":5,"n":2}, …]},   # 5 equal buckets of the max
  "parts": [ {"q_id":"9b","label":"9(b)","max":2,"attempted":38,"mean_pct":41.0,"full":9,"zero":18,
              "allocations":[{"label":"M1","lost":21},{"label":"A1","lost":27}],
              "not_in_scheme":3,"illegible":1,"pending":2}, … ],           # scheme order
  "weakest": ["9b","8b","10"],                                          # by mean_pct asc, min 5 attempts
  "most_lost": [{"q_id":"9b","label":"A1","lost":27,"of":38}, …],        # top 8 allocations by lost count
  "students": [ {"student_id":1,"reg_no":1,"name":"Tan Wei Ling","total":10,"max":13,
                 "weak_parts":["9b","8b"]}, … ]                          # weak = parts scored < 50%
}
```
Rubric assignments use criteria as parts and bands as the "allocation" (lost = below the top band).

### A2. Narrative (one model call)

New agent `agents/insights.py::build_insights` (atomic-agents, same pattern as reflection) with input
`InsightsInput{assignment_title, subject, scheme_kind, stats (the block above minus names), samples}` where
`samples` is ≤ 40 anonymised `{part, reg_no, extracted (≤300 chars), awarded, justification (≤200 chars)}`
rows drawn from the weakest 4 parts (10 each, lowest scores first). **Student names never reach the
model**; the narrative refers to register numbers and the app joins names back.

Output `InsightsReport`:
```
summary: str                                  # 3–4 sentences, plain teacher language
strengths: [str]                              # 2–4
gaps: [{part_ids: [str], title: str, what_went_wrong: str, students_affected: int}]   # 2–5
recommendations: [{title: str, detail: str, part_ids: [str]}]                        # 3–5 concrete next-lesson actions
students_to_support: [{reg_nos: [int], focus: str}]                                  # groups by gap
```
Forbidden words in student-facing surfaces do not apply here (teacher-only), but the prompt keeps to
mark-scheme vocabulary and never invents parts not in `stats`.

### A3. Job, storage, triggers

- Table `assignment_insights` (migration 0009): `class_assignment_id` PK, `stats_json`, `report_json`
  (null until the model call succeeds), `n_marked`, `provider`, `model`, `generated_at`, `error`.
- Job kind `insights`, payload `{class_assignment_id}`, `enqueue_unique` key `insights:{caid}`. The job
  recomputes stats, calls the agent with the assignment's effective settings (§C), upserts the row.
  A failure stores `error` and keeps the previous `report_json` (stats are still refreshed).
- Triggers: (1) after a `mark` job finishes, if the submission has a `class_assignment_id` and that
  class assignment now has **no** submission in `uploaded/queued/marking` and ≥ 1 marked → enqueue;
  (2) on **Release**; (3) `POST /api/classes/{id}/assignments/{caid}/insights/regenerate` (409 if a job is
  already queued/running). Stats alone are always available live via `GET …/insights` even before a
  report exists (computed on request when no row).
- API: `GET /api/classes/{id}/assignments/{caid}/insights` → `{stats, report, generated_at, provider,
  model, error, job: {status}}`; `GET …/insights.pdf`.

### A4. Page and PDF

**Insights** tab on the class assignment page (`/classes/:id/assignments/:caid?tab=insights`):
header (n marked / pending, mean, generated when, model), **Marks by part** bar chart (mean % per part
in scheme order, weakest highlighted amber), **Most-lost allocations** list, the narrative in four blocks
(Summary · Strengths · Gaps · Recommended next steps), **Students to support** table (names joined from
`students`, each with their weak parts), score distribution. **Regenerate** and **Download PDF** buttons;
"Generating…" state while the job runs (poll every 5 s).

`records/insights_pdf.py::render_insights_pdf(ca, stats, report) -> bytes` with ReportLab (A4 portrait):
title block, summary, a drawn bar chart (ReportLab graphics), most-lost list, gaps, recommendations,
students table. Added to `pyproject.toml` (`reportlab>=4.2`).

## B. Telegram

### B1. Settings

`settings` gains (migration 0009): `telegram_bot_token_enc` (Fernet, same cipher as keys),
`telegram_chat_id` (text, null until linked), `telegram_instant` (bool, default true),
`telegram_daily_time` (text `HH:MM`, default `07:00`), `timezone` (text, default `Asia/Singapore`),
`app_url` (text, null → derived from `RAILWAY_PUBLIC_DOMAIN` at runtime → `https://<domain>`),
`telegram_daily_last_sent` (date text), `telegram_update_offset` (int).

`Settings` dataclass gains the fields; `public_dict` exposes `telegram_linked: bool`, `telegram_bot_hint`
(last 4 of the token), never the token. `PUT /api/settings` accepts the new fields (`telegram_bot_token`
blank = keep; `DELETE /api/settings/telegram` unlinks and clears the token).
`POST /api/settings/telegram/test` sends "Smart Marking is connected ✓" to the linked chat.

### B2. Linking (no webhook)

`services/telegram.py::TelegramClient(token)` over httpx: `get_updates(offset, timeout=0)`,
`send_message(chat_id, html)`, `get_me()`. The worker calls `poll_telegram()` every 10 s while a token is
stored: any update whose message text starts with `/start` links that chat (`telegram_chat_id`), replies
"Linked to Smart Marking ✓ — you'll get marking updates here", and advances `telegram_update_offset`.
A `/start` from a second chat replaces the link (one chat per deployment — the department group or the
teacher). Any other message is ignored. Poll errors are logged and retried on the next tick.

### B3. Outbox and events

Table `notifications` (migration 0009): `id`, `kind` (`hand_in` | `marking_done` | `daily`), `class_assignment_id`
(null for daily), `payload_json`, `created_at`, `sent_at`, `error`. The worker flushes unsent rows every
10 s (`flush_notifications()`), batching same-kind rows for the same class assignment into one message.

- **hand_in**: `create_submission` with a `class_assignment_id` and `source='student'` inserts one row
  `{reg_no, name}`. Flush collates: "📥 *4E2 · Worksheet 3* — 5 new hand-ins: #1 Tan Wei Ling, #4 …"
  (names in Telegram are fine — the chat is the teacher's).
- **marking_done**: the same after-`mark` check as §A3 trigger (1) inserts one row when the class
  assignment's queue drains, guarded by `class_assignments.last_done_notified_at` so a drain fires once
  until a new hand-in arrives (the column is nulled on each new submission). Message: "✅ *4E2 · Worksheet 3*
  — marking finished: 38 marked, 3 need you → Review · Insights ready" with links.
- **daily**: at the first worker tick after `telegram_daily_time` local time (`zoneinfo`) on a day when
  `telegram_daily_last_sent` ≠ today, build the digest: per class with activity in the last 24 h —
  hand-ins, marked, needs you, released, each assignment as a link, "Insights ready" link where a report
  exists. Nothing happened → no message. Then set `telegram_daily_last_sent`.
- Links: `app_url + /classes/{id}/assignments/{caid}` (`?tab=insights`, `/review`). Messages use
  Telegram HTML parse mode; text is escaped.
- `telegram_instant=false`: hand_in and marking_done rows are not inserted. The daily digest is sent
  whenever a chat is linked.

Settings page → **Notifications** section: token field with hint, status "Not linked — open your bot and
press /start" / "Linked ✓ (chat …1234)", buttons **Send test message**, **Unlink**; toggles for instant
messages; daily time + timezone select (IANA list, default Asia/Singapore); app URL field with the
detected default as placeholder.

## C. Per-assignment model and custom model lists

### C1. Assignment override

`assignment_templates` gains `provider`, `model`, `extractor_model` (all nullable; migration 0009).
NULL provider = **Auto — follow Settings**. `PUT/POST /api/assignments` validates: provider known and has
a saved key (400 `no_key_for_provider`), model non-blank. Template dict exposes the three fields plus
`effective_model: {provider, model, extractor_model}` for display.

`SettingsStore.for_template(tpl: dict | None) -> Settings` returns the global settings with provider,
model, extractor_model (and the key for that provider, `base_url` = provider default) overlaid when the
template sets them. `mark_job`, `extract_jobs` (paper/scheme), and the insights job build their
clients from `for_template`. `stamp_run_model` already records what marked each run.

Rate limiting: the worker keeps one `TokenBucket` **per provider** (`_bucket_for(provider, rpm)`): the
global provider uses `settings.rpm_limit`, any other provider its `default_rpm`.

Editor (`AssignmentEditor`): a **Model** section — segmented "Auto — follow Settings | Choose a model";
when choosing: provider tiles (only providers with a saved key, others disabled with "no key saved"),
model select (curated + *My models* + *Load models from provider* + custom id), optional page-reading
model. Assignments list shows the model as a small caption when set.

### C2. My models

Table `custom_models` (migration 0009): `provider`, `model_id`, `label`, `vision` (bool), `created_at`,
PK (`provider`, `model_id`). `ProviderSpec.custom_models: bool` — true for `tokenrouter` and
`openrouter`. API: `GET/POST/DELETE /api/settings/models/{provider}` (`{model_id, label?, vision}`);
`GET /api/providers` merges saved custom models into each provider's `models` (flagged `custom: true`)
so every picker (Settings, assignment editor) sees them. Settings page: under those two providers a
**My models** list with add (id, label, "reads pages" checkbox) and remove, and a tick-to-add button
next to each id returned by *Load models*.

## D. Out of scope

Cross-assignment/longitudinal student analytics; per-student Telegram or parent messages; Telegram
commands beyond `/start`; email/WhatsApp; custom models for providers other than the two aggregators.

## E. Testing

- Unit: `compute_stats` on seeded v2/v1 runs incl. corrections and pending parts; sample selection and
  anonymisation (no names in `InsightsInput`); PDF renders and contains the part labels; Telegram message
  formatting/escaping and batching; daily-digest gating (time zone, once per day, nothing-happened skip);
  `/start` linking and offset advance (httpx mocked); `for_template` overlay; per-provider buckets.
- API: insights endpoint before/after a report, regenerate 409, PDF content-type; settings round trip
  for the Telegram/timezone fields (token never leaked), test-message and unlink; custom models CRUD and
  their appearance in `/api/providers`; assignment override validation (no key → 400).
- Worker: mark-job finish enqueues `insights` and a `marking_done` row exactly once per drain; outbox
  flush batches hand-ins; failed send keeps the row with `error`.
- Frontend: Insights tab (chart rows, narrative, students table, Regenerate/Download), Settings
  Notifications section, My models list, assignment Model section (providers without keys disabled).

# Smart Marking web app — slice 1 design

**Date:** 2026-09-15
**Status:** approved (brainstorm), pending implementation plan

## Goal

Turn the existing `sms` CLI into a web app that a teacher can deploy to Railway with one click,
sign in to, point at any of six LLM providers with their own API key (default: TokenRouter's free
`z-ai/glm-5.3-free`), upload a student script (PDF or photos), have it marked in the background, and
resolve the questions the AI was unsure about — all in the browser, in the visual style of the
Modernist design handoff in `docs/design-handoff/` (see "Design references" below).

Slice 1 deliberately has **no classes, students or assignments**. It is the CLI workflow in the
browser, deployed. Those come in later slices:

| Slice | Contents |
|---|---|
| **1 (this spec)** | Provider layer, settings, Postgres + volume, FastAPI, worker, teacher SPA (sign-in, settings, mark a script, results, review queue, learning), Railway template |
| 2 | Classes, classlist CSV, assignments + rubric, assignment page, release, marks CSV, student detail |
| 3 | Student phone flow: class link → register number → hand in (camera/gallery/PDF, offline queue) → feedback |
| 4 | Bulk-upload page sorter |

## Decisions already made

- **Auth:** one shared teacher password from `TEACHER_PASSWORD` (option A). No accounts, no Google.
- **Database:** Postgres (Railway plugin) via SQLAlchemy Core; SQLite locally and in tests.
- **Model picker:** provider dropdown + curated model list per provider + "custom model id" field.
- **Key storage:** encrypted in Postgres; optional env-var pre-seed.
- **Topology:** one Railway service; the worker runs in-process, written as a separate module so it
  can become a second service by changing a start command.
- **Uploads:** PDF, JPG, PNG, HEIC accepted everywhere; everything is rasterised to one JPEG per
  page. Anthropic's native PDF input is *not* used (one code path for six providers; the UI needs
  per-page images anyway; the extraction cache is keyed on page hashes). Noted as a possible later
  optimisation.
- **First deliverable is Railway-runnable** before any further screens are built.

## Architecture

```
Browser (React SPA, web/dist)  ──/api──▶  FastAPI (sms.web)  ──▶  Postgres (SQLAlchemy Core)
                                              │                      ▲
                                              │ lifespan thread      │
                                              ▼                      │
                                         sms.worker  ──▶  MarkingPipeline (unchanged) ──▶ LLM provider
                                              │
                                              ▼
                                        STORAGE_DIR (/data volume): pages/<sha256>.jpg
```

One container. FastAPI serves `/api/*` and the built SPA (SPA fallback for every other path).

## 1. Provider layer — `src/sms/providers/`

### Registry (`registry.py`)

```python
@dataclass(frozen=True)
class ModelSpec:
    id: str; label: str; vision: bool

@dataclass(frozen=True)
class ProviderSpec:
    id: str                 # "tokenrouter" | "openrouter" | "openai" | "anthropic" | "moonshot" | "qwen"
    label: str
    transport: str          # "openai_compatible" | "openai" | "anthropic"
    base_url: str | None
    mode: str               # instructor mode name: "JSON" | "TOOLS" | "ANTHROPIC_TOOLS"
    default_model: str
    default_rpm: int
    models: tuple[ModelSpec, ...]
    key_url: str            # where to get a key
    note: str = ""          # shown under the provider in the UI
```

| id | transport | base_url | mode | default model | rpm |
|---|---|---|---|---|---|
| `tokenrouter` (default) | openai_compatible | `https://api.tokenrouter.com/v1` | JSON | `z-ai/glm-5.3-free` | 8 |
| `openrouter` | openai_compatible | `https://openrouter.ai/api/v1` | JSON | `z-ai/glm-5.3-flash` | 60 |
| `openai` | openai | (SDK default) | TOOLS | `gpt-5-mini` | 60 |
| `anthropic` | anthropic | (SDK default) | ANTHROPIC_TOOLS | current Claude Sonnet | 60 |
| `moonshot` | openai_compatible | `https://api.moonshot.ai/v1` | JSON | Kimi vision model | 60 |
| `qwen` | openai_compatible | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | JSON | `qwen3-vl-plus` | 60 |

Curated model ids and the Anthropic/Moonshot defaults are verified against provider docs during
implementation, not hard-coded from memory. `note` for TokenRouter: "Free tier: 8 requests a
minute — about 30 s per script. Create the key with Allowed Models locked to z-ai/glm-5.3-free."

### Client factory (`client.py`)

`build_client(provider_id, api_key) -> instructor.Instructor`
- `openai_compatible` / `openai`: `instructor.from_openai(openai.OpenAI(api_key=..., base_url=...), mode=...)`
- `anthropic`: `instructor.from_anthropic(anthropic.Anthropic(api_key=...), mode=...)`
- Unknown provider → `ValueError`.

The agent factories in `sms/agents/*` are unchanged — they already take `client` and `model`.

### Settings (`settings.py`)

Single row in table `settings`:

| column | type | notes |
|---|---|---|
| id | int PK = 1 | |
| provider | text | provider id |
| model | text | |
| extractor_model | text, nullable | blank = use `model` for the Extractor |
| api_key_enc | text, nullable | Fernet(`SECRET_KEY`)-encrypted |
| rpm_limit | int | defaults from provider on provider change |
| confidence_threshold | float | default 0.0 |
| updated_at | timestamp | |

`SettingsStore.load()` returns a `Settings` dataclass with the key decrypted; `save()` encrypts.
`key_hint` = last 4 chars. On first boot (`ensure_seeded()`), if no row exists: create one from
`LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` env vars (defaults `tokenrouter`, provider default
model, no key).

### Test connection (`probe.py`)

`probe(provider, model, extractor_model, api_key) -> ProbeResult{text: Check, vision: Check}` where
`Check{ok, latency_ms, error}`.
- Text: one structured call expecting `class Pong(BaseIOSchema): ok: bool`.
- Vision: a generated 64×64 PNG with a random two-digit number rendered in it, sent to
  `extractor_model or model`, expecting `class Digits(BaseIOSchema): number: int`; ok iff it matches.
Errors are the provider's message, trimmed to 300 chars.

### Rate limit & retry (`ratelimit.py`)

`TokenBucket(rpm)` — thread-safe, `acquire()` blocks until a token is free. The worker wraps every
`agent.run()` in it. Retryable errors (HTTP 429, 5xx, timeouts, connection errors) are retried by
the worker with backoff `30s · 2^attempt`, max 5 attempts; everything else fails immediately.

## 2. Data model & storage

### Database access — `src/sms/memory/db.py`

`Database(url)` wraps a SQLAlchemy engine. `execute(sql, params: dict)` and `query(sql, params: dict)`
use `text()` with `:name` parameters. `DATABASE_URL` env (default `sqlite:///sms.db`). Postgres
uses `psycopg` (v3). The existing call sites in `providers.py`, `extraction_cache.py`, `metrics.py`,
`reflection_job.py`, `marking_pipeline.py`, `cli.py` switch from `?` to `:name` parameters. The
`SCHEMA` string is removed; schema lives in Alembic.

### Migrations — `alembic/`

- `0001_baseline`: the seven existing tables (portable types; `created_at` defaults via
  `sa.func.now()`).
- `0002_web`: `settings`, `submissions`, `pages`, `jobs`, `worker_heartbeat`; adds
  `submission_id` to `teacher_queue` and `marking_runs`; adds `criterion_scores_json` to
  `teacher_corrections`.

`alembic upgrade head` runs in the container start command and in `sms serve`. Tests create the
schema by running the migrations against SQLite.

### New tables

**submissions**

| column | type |
|---|---|
| id | int PK |
| label | text |
| subject | text (`math` / `language` / `science`) |
| context | text |
| rubric_json | text |
| status | text: `uploaded` → `queued` → `marking` → `needs_you` \| `done` \| `failed` |
| run_id | text, nullable → `marking_runs.run_id` |
| created_at, updated_at | timestamp |

**pages**: `id`, `submission_id` FK, `page_index` (0-based), `sha256`, `storage_path`,
`source_filename`, `width`, `height`. Unique `(submission_id, page_index)`.

**jobs**: `id`, `kind` (`mark`), `submission_id` FK, `status` (`queued`/`running`/`done`/`failed`),
`attempts` int, `not_before` timestamp nullable (backoff), `error` text nullable, `created_at`,
`started_at`, `finished_at`.

**worker_heartbeat**: `id` = 1, `last_seen` timestamp.

### Files — `src/sms/storage.py`

`STORAGE_DIR` env (default `/data` in the container, `./data` locally). Pages stored
content-addressed at `pages/<sha256>.jpg`. `process_uploads(files) -> list[ProcessedPage]`:
- PDF → PyMuPDF renders each page at 150 dpi.
- HEIC/HEIF → pillow-heif.
- JPG/PNG → Pillow.
- Every page: EXIF-rotate, RGB, long edge ≤ 2000 px, JPEG q=85. Originals are not kept.
- Limits: 50 MB per request, 60 pages per submission. Errors name the file:
  `{"error": {"code": "bad_upload", "message": "scan.pdf: not a valid PDF"}}`.
- Pages are ordered by the order files were sent, then page order inside a PDF.

Page images are served only through `GET /api/pages/{id}` (authenticated).

## 3. HTTP API — `src/sms/web/`

FastAPI app `sms.web.app:app`. Routers: `auth`, `settings`, `submissions`, `pages`, `queue`,
`learning`, `health`. Errors: `{"error": {"code", "message"}}`.

**Auth**
- `POST /api/auth/login {password}` → 204 + signed HttpOnly `sms_session` cookie (itsdangerous,
  `SECRET_KEY`, 30-day expiry, `Secure` when not localhost). Wrong password → 401. Rate limit 5/min
  per IP (in-memory) → 429.
- `POST /api/auth/logout` → clears cookie.
- `GET /api/auth/me` → `{authenticated: true}` or 401.
- All other `/api/*` routes except `/api/health` require the cookie (dependency `require_teacher`).

**Settings**
- `GET /api/providers` → registry as JSON.
- `GET /api/settings` → `{provider, model, extractor_model, rpm_limit, confidence_threshold,
  has_key, key_hint}`. Never the key.
- `PUT /api/settings` → same fields + optional `api_key`; empty/missing `api_key` keeps the stored
  one. Validates provider id; model may be any non-empty string.
- `POST /api/settings/test {provider, model, extractor_model?, api_key?}` → `ProbeResult`.
  Uses the submitted key, else the stored one; 400 if neither.

**Submissions**
- `POST /api/submissions` (multipart: `label`, `subject`, `context`, `rubric` JSON string,
  `files[]`) → 202 `{id, status: "queued", pages: [{id, page_index, width, height}]}`. Validates
  the rubric with the existing `Rubric` model. Creates the submission (`uploaded`), pages, one
  `mark` job, then sets `queued`. 400 if no key is configured.
- `GET /api/submissions` → `[{id, label, subject, page_count, status, total, total_max,
  total_upper, needs_you_qids, created_at}]` newest first. `total_upper` ≠ `total` while a
  question is escalated (range display).
- `GET /api/submissions/{id}` → submission fields, `pages`, `rubric`, and when a run exists:
  `marks: [{q_id, criterion_scores, total, confidence, evidence, rationale, escalated, reason}]`,
  `feedback` (FeedbackReport JSON), `job: {status, attempts, error, started_at, finished_at}`.
- `POST /api/submissions/{id}/retry` → re-queues a `failed` job (409 otherwise).
- `GET /api/pages/{id}` → `image/jpeg`, `Cache-Control: private, max-age=86400`.

**Review queue**
- `GET /api/queue` → pending items: `{id, submission_id, submission_label, q_id, reason,
  question_text (from extraction), transcription, proposed_criterion_scores, evidence,
  reviewer_note, page_ids, criterion_defs}`.
- `POST /api/queue/{id}/resolve {criterion_scores: [int], reason: str}` → inserts
  `teacher_corrections` (`agent_mark` backfilled from `marks_json`, `teacher_mark` = sum,
  `criterion_scores_json`), marks the item `resolved`; if the submission has no pending items
  left, sets its status to `done`. 404 if not pending.

**Learning**
- `GET /api/notes`, `POST /api/notes/{id}/approve`, `GET /api/exemplars`,
  `POST /api/exemplars/{id}/approve`, `GET /api/stats` (MetricsSummary per role).

**Health**
- `GET /api/health` → `{db: "ok", worker_last_seen: iso | null}`; 503 if the DB is unreachable.

## 4. Worker & jobs — `src/sms/worker/`

`Worker(db, storage, settings_store, pipeline_factory)` with `run_forever(stop_event)` and
`run_once() -> bool`. Started as a daemon thread from the FastAPI lifespan when
`SMS_EMBEDDED_WORKER != "0"`; also runnable as `sms worker` for a separate service.

Loop (every 2 s): write heartbeat; claim one job where `status='queued' AND (not_before IS NULL OR
not_before <= now)` ordered by `created_at` (`FOR UPDATE SKIP LOCKED` on Postgres; plain
`UPDATE … WHERE status='queued'` returning rowcount on SQLite); set `running`, `started_at`,
`attempts += 1`; submission → `marking`.

`mark` job:
1. `settings = settings_store.load()`; 400-equivalent failure (non-retryable) if no key.
2. `client = build_client(...)`; extractor uses `extractor_model or model`.
3. Load page bytes from storage in `page_index` order.
4. Build agents with the existing factories, `wire_metrics`, construct `MarkingPipeline` with
   `confidence_threshold` from settings, run it inside the token bucket (`agent.run` wrappers).
5. Success → `marking_runs.submission_id` and `teacher_queue.submission_id` set;
   `submissions.run_id` set; status `needs_you` if escalations else `done`; job `done`.
6. Failure → if retryable and `attempts < 5`: job `queued` with
   `not_before = now + 30s·2^attempts`, submission → `queued`; otherwise job `failed` with
   `error`, submission → `failed`.

On start: any `running` job → `queued` (its submission → `queued`).

`pipeline_factory` is injected so tests use a fake pipeline.

## 5. Frontend — `web/`

React 18 + TypeScript + Vite, react-router, Lucide icons, plain CSS. `web/src/styles/tokens.css`
is the Modernist `styles.css` ported verbatim (tokens + `.btn`, `.table`, `.input`, `.seg`,
`.nav`, `.dialog`, `.tag`); product components in `web/src/components/`. Archivo via Google Fonts
with a system fallback. Build → `web/dist`, served by FastAPI. Dev: `vite` proxies `/api` →
`http://localhost:8000`.

Nav: **Submissions · Review [n] · Learning · Settings**, brand "Smart Marking", sign-out.

Screens (design references in brackets):
1. `/sign-in` — [T1] minus Google/email: password field, primary "Sign in", hero panel. 401 → here.
2. `/settings` — provider (segmented if ≤ 6, else dropdown), model dropdown (vision models marked
   "reads pages"), "Custom model id" text field, API key input with `key_hint` placeholder and
   key URL link, "Different model for reading pages" (optional), requests per minute, confidence
   threshold, **Test connection** (results: "Text ✓ 1.2 s · Vision ✓ 2.8 s" or amber notice with
   the error), Save. Provider note shown under the picker.
3. `/submissions` — [T2 table] label, subject, pages, status pill, total (range while open),
   created. Primary "+ Mark a script". Empty state explains the flow.
4. `/submissions/new` — [T5 panel as a page + T3 drop zone]: label, subject segmented control
   (Maths / English / Science → `math`/`language`/`science`), context, rubric criteria table
   (Q / criterion / description / max, "+ Add criterion", running total) with "Upload JSON
   instead"; drop zone (PDF/JPG/PNG/HEIC, multiple) with a page-card grid (S4/T8 card: thumbnail,
   ink number tag, remove; drag to reorder). Primary "Start marking" → POST → navigate to detail.
   Shows "Marking takes about 30 s per script on the free tier" when provider is TokenRouter.
5. `/submissions/:id` — [T9]: pages with page-key pager left; right: status pill; "Marks by
   question" rows (Q · total / max, squares) expanding to criterion scores, confidence, evidence,
   rationale; escalated rows carry the amber "Needs you" pill linking to `/review?item=…`;
   feedback report (summary, strengths, question by question, work on next, next steps).
   `queued`/`marking`: calm "Marking… started 0:42 ago", polls every 3 s. `failed`: amber notice
   with the provider error + "Retry".
6. `/review` — [T7]: "n of m" toolbar with keyboard legend; left: student page (page pager),
   "What we read" transcription, amber "Why this is here"; right: criteria table with proposed
   marks + inputs, question total, reason textarea; footer Previous / Accept proposed [A] / Save &
   next [↵]. Keys: ← → A 1–5 ↵. Empty state "Nothing needs you".
7. `/learning` — two tables (rubric notes, exemplar cases) with status and Approve; stats strip
   from `/api/stats`.

Shared components: `Button` (variants, key badge), `StatusPill`, `CriteriaTable` (authoring /
review / reading), `MarkDisplay` (squares + `n / m`, ranges), `PageCard`, `PageStrip`, `PagePager`,
`DropZone`, `Notice` (amber), `Dialog`, `EmptyState`, `Nav`. Each screen has empty, loading and
error states.

## 6. Railway & local dev

**Dockerfile** (multi-stage): `node:22-alpine` → `npm ci && npm run build` in `web/`;
`python:3.12-slim` → install `uv`, `uv sync --frozen --no-dev`, copy `web/dist`. `CMD ["sh",
"-c", "alembic upgrade head && uvicorn sms.web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]`.

**railway.json**: builder DOCKERFILE, `healthcheckPath: /api/health`, `restartPolicyType:
ON_FAILURE`.

**Template variables**

| var | value / description |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `SECRET_KEY` | auto-generated 32-byte secret; signs sessions and encrypts API keys |
| `TEACHER_PASSWORD` | required — "the password teachers use to sign in" |
| `STORAGE_DIR` | `/data` (volume mount) |
| `LLM_PROVIDER` | optional, default `tokenrouter` |
| `LLM_MODEL` | optional, default `z-ai/glm-5.3-free` |
| `LLM_API_KEY` | optional — pre-seeds the key so Settings can be skipped |

Services: web (this repo, Dockerfile) + Postgres plugin + volume at `/data`.

Deploy path: build → deploy to the owner's Railway account via the Railway MCP → verify live →
owner publishes the project as a template from the dashboard. README gains "Deploy on Railway"
with the table above, plus "Run locally": `uv sync && (cd web && npm ci && npm run build) &&
TEACHER_PASSWORD=dev uv run sms serve` (SQLite, `./data`).

**New dependencies**: fastapi, uvicorn, python-multipart, sqlalchemy, alembic, psycopg[binary],
cryptography, itsdangerous, pymupdf, pillow, pillow-heif, anthropic.

## 7. Testing

- **Unit (pytest, SQLite):** registry/client factory (base URL + mode per provider; unknown
  provider errors); Fernet round-trip; env seeding creates the row once; `process_uploads`
  (generated 3-page PDF → 3 pages, PNG normalised to JPEG, oversize → error naming the file,
  page limit); `TokenBucket` timing; worker with a fake pipeline (success → `done` / `needs_you`,
  retryable error → `queued` with `not_before`, 5th failure → `failed`, startup resets `running`);
  queue resolve flips submission to `done` only when nothing is pending.
- **API (TestClient):** every route 401 without cookie; login rate limit; settings never leaks the
  key and blank key keeps stored; `POST /submissions` 400 without key, 202 with; page route
  authenticated; `GET /submissions/{id}` shape before and after a run.
- **Frontend (vitest):** rubric table ↔ JSON; mark-range helper; render tests for `StatusPill`,
  `MarkDisplay`, `CriteriaTable`. Manual pass in the in-app browser against the handoff
  screenshots.
- **Live (opt-in):** `SMS_LIVE_TESTS=1 TOKENROUTER_API_KEY=…` runs the probe against
  `z-ai/glm-5.3-free` (text + vision).
- Existing tests (`tests/unit`, `tests/integration`) keep passing on the SQLAlchemy `Database`.

## Design references

The design handoff zip (`UI Mockups Scoping.zip`) is copied into `docs/design-handoff/` (HTML
artboards, `screenshots/`, `_ds/…/styles.css`, README) so the mockups live with the code.

## Out of scope for slice 1

Classes, students, assignments, release, marks CSV, student flow, page sorter, reflection
scheduling ("Run reflection" button), multi-teacher accounts, Google sign-in, Anthropic native PDF
input, websockets/progress bars.

## Amendments (made while writing the implementation plan)

- **`settings.base_url`** (editable per provider, pre-filled from the registry): Alibaba Model Studio now
  issues workspace-specific endpoints (`https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`),
  so Qwen users must be able to paste theirs. Shown in the UI only for providers flagged `base_url_editable`.
- **`ProviderSpec.api_params`** and a `model_api_parameters` passthrough on every agent factory: the
  Anthropic Messages API requires `max_tokens`; the registry supplies `{"max_tokens": 8192}` for Anthropic.
- **Anthropic default model** is `claude-opus-5` (curated: Opus 5, Sonnet 5, Haiku 4.5), per the Claude API reference.
- **Moonshot** curated models: `kimi-k2.6` (default), `kimi-k3` — both vision. Older `moonshot-v1-*` ids are retired.
- **Rubric table** in slice 1 has no per-question "Q" column: the engine applies `criterion_defs` to every
  question. Per-question rubrics come with assignments in slice 2.

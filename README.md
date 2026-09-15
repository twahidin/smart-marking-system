# Smart Marking System

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

`--provider` on `mark`/`reflect` selects the LLM provider (`tokenrouter` \| `openrouter` \| `openai` \| `anthropic` \| `moonshot` \| `qwen`); `--api-key` supplies its key. Both default to the configured provider/key when omitted.

## Web app

Smart Marking is also a web app: sign in with a shared teacher password, pick an LLM provider
(TokenRouter, OpenRouter, OpenAI, Anthropic, Moonshot/Kimi, Qwen) and enter its API key under
**Settings**, upload a script's pages (PDF, JPG, PNG or HEIC) under **Mark a script**, and resolve the
questions the AI was unsure about under **Review**. The default provider is TokenRouter with
`z-ai/glm-5.3-flash`; **Load models from provider** on the Settings page lists every model your key
can actually use (some TokenRouter keys include the free `z-ai/glm-5.3-free`, limited to 8 requests/min).

### Run locally

```sh
uv sync
(cd web && npm ci && npm run build)
SECRET_KEY=dev TEACHER_PASSWORD=dev uv run sms serve
# open http://localhost:8000 — uses ./sms.db (SQLite) and ./data for page images
```

Frontend development with hot reload: `cd web && npm run dev` (proxies `/api` to :8000).

### Deploy on Railway

One service (this repo, Dockerfile) + a Postgres database + a volume mounted at `/data`.

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `SECRET_KEY` | a long random string — signs sessions and encrypts stored API keys (changing it invalidates both) |
| `TEACHER_PASSWORD` | the password teachers use to sign in |
| `STORAGE_DIR` | `/data` |
| `LLM_PROVIDER` | optional — `tokenrouter` (default), `openrouter`, `openai`, `anthropic`, `moonshot`, `qwen` |
| `LLM_MODEL` | optional — defaults to the provider's default model |
| `LLM_API_KEY` | optional — pre-seeds the key so the settings page can be skipped |

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

**Status**: MVP — math marking via CLI, plus a FastAPI + React web app (sign-in, settings,
mark-a-script upload, submission detail, and the teacher review queue).

Roadmap:

- Classes and assignments (organize submissions by class/assignment instead of ad-hoc uploads)
- Student phone flow (students photograph and submit their own scripts)
- Bulk-upload page sorter (split a multi-script batch scan into per-student submissions)
- Language and science subject factories (prompts already ship)
- SymPy verification for math marking
- Ensemble marking

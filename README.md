# Smart Marking System

AI agents that mark, review, and give feedback on student scripts from images, built on [atomic-agents](https://github.com/BrainBlend-AI/atomic-agents). Agents get smarter and faster with every teacher correction.

## How it works

```
images -> Extractor (vision OCR, per-question transcription)
       -> Marker (per-rubric-criterion marks with evidence)
       -> Reviewer (independent second pass, anti-anchoring: marker rationale hidden;
                    APPROVE / ADJUST / ESCALATE verdicts)
       -> Feedback (student-facing report)
       -> SQLite
```

- **Escalation**: low-confidence or ambiguous questions land in a teacher queue.
- **Smarter (learning loop)**: teacher corrections on the queue feed a nightly Reflection job that distills rubric notes and exemplar cases as *drafts*; the teacher approves them, and approved notes/cases are injected into Marker/Reviewer system prompts via atomic-agents Context Providers on every subsequent run.
- **Faster (speed loop)**: SHA-256 content-hash extraction cache (re-marks of the same image skip the vision call) and a hook-ready `agent_metrics` table for latency/token tracking.
- **Subjects**: math is fully supported (MVP); language and science ship with prompt data — add factories once validated.

## Quickstart

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
| `sms mark IMAGES... --subject --rubric --context --db --model` | Mark scripts from images |
| `sms reflect --subject --lookback --db --model` | Nightly learning job |
| `sms evaluate --db` | Agent-teacher agreement % |
| `sms stats --db` | Per-agent latency/token metrics |
| `sms queue list --db` | List teacher escalations |
| `sms queue resolve QUEUE_ID --teacher-mark INT --reason --db` | Resolve an escalation; records the correction that feeds the learning loop |
| `sms notes list --db` | List rubric notes (draft/active) |
| `sms notes approve NOTE_ID --db` | Approve a draft note (draft -> active) |

## The learning workflow

1. Mark scripts: `sms mark ...`
2. Review escalations in the queue and resolve them with your marks: `sms queue resolve ...`
3. Run the nightly reflection job: `sms reflect ...`
4. Approve the distilled notes: `sms notes approve ...`
5. Next runs are smarter — approved notes and exemplar cases are injected into agent prompts automatically.

Track progress with `sms evaluate` (agreement %) and `sms stats` (latency/tokens).

## Development

```sh
uv run pytest -q
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

**Status**: MVP — math marking via CLI.

Roadmap:

- Language and science subject factories (prompts already ship)
- Metrics hook wiring (`completion:response`) into `agent_metrics`
- SymPy verification for math marking
- FastAPI service
- Ensemble marking

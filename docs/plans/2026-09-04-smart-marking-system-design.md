# Smart Marking System — Design Doc

Date: 2026-09-04
Status: Approved

## Summary

A standalone Python package (`sms`) built on the [atomic-agents](https://github.com/eigenwise/atomic-agents) framework that marks student scripts from images. Specialised agents handle marking, review, and feedback across languages, math, and science. Agents improve over time through a case-memory + reflection loop (teacher-corrected ground truth distilled into rubric notes and exemplar cases injected at runtime via Context Providers) and get faster through content-hash caching, confidence-based routing, and hook-based metrics.

## Decisions

- **Standalone package** depending on upstream `atomic-agents` (no fork).
- **Learning loop:** case-memory + nightly reflection. Vector similarity cache deferred (privacy, YAGNI).
- **Human in the loop:** teacher-reviewed corrections are the ground truth source.
- **MVP:** CLI, math subject first. Language/science have prompt templates but unimplemented factories until math validates.

## Pipeline Architecture (Approach B: Reviewer-Adjudicated)

Each role is an `AtomicAgent[InputSchema, OutputSchema]`:

| Role | Job | Key output |
|---|---|---|
| Extractor | Reads script images (`instructor.Image`), transcribes handwriting, segments per question | `ExtractedScript{questions: [{q_id, transcribed_answer, workings, confidence, needs_human_transcription}]}` |
| Marker | Marks each question against rubric criteria with evidence citations | `MarkedScript{marks: [{q_id, criterion_scores, total, confidence, rationale}]}` |
| Reviewer | Independent second pass (sees extraction + rubric, NOT marker rationale, to avoid anchoring). Verdict per question: APPROVE / ADJUST(new_mark) / ESCALATE | `ReviewedScript{verdicts, final_marks, disagreement_flags}` |
| Feedback | Student-facing strengths, gaps, improvement steps | `FeedbackReport{per_question_comments, improvement_plan, next_steps}` |
| Reflection | Offline nightly job; distills teacher corrections into rubric notes, exemplar cases, prompt tweaks | `ReflectionUpdate{rubric_notes, exemplar_cases, prompt_tweaks}` |

**Subject routing:** Marker/Reviewer are instantiated per-subject (same schemas, different `SystemPromptGenerator`). Math emphasizes working steps (sympy verification later); language emphasizes rubric dimensions (content/organisation/mechanics); science emphasizes concept coverage. Extractor and Feedback are subject-agnostic. A `PipelineRouter` selects the Marker/Reviewer pair by the assignment's declared subject.

**Escalation:** Marker confidence below threshold OR Reviewer ESCALATE verdict → script queued in SQLite `teacher_queue` for teacher review. Corrections become reflection input.

## Learning Loop

**Smarter — case memory + reflection:**

- SQLite tables: `marking_runs`, `teacher_corrections`, `rubric_notes`, `exemplar_cases`.
- Nightly Reflection agent reads recent disagreements (teacher mark vs agent mark per question) and emits a structured `ReflectionUpdate` containing rubric clarifications, exemplar cases, and prompt tweaks.
- Updates are human-reviewable: `draft → active` state; a teacher can veto before activation.
- Injection: each subject Marker/Reviewer registers `RubricNotesProvider` and `ExemplarCasesProvider` (atomic-agents `BaseDynamicContextProvider`), whose `get_info()` pulls the latest active notes from SQLite. The same agent instance gets smarter on every run with zero code changes.

**Faster:**

1. **Extraction cache:** SHA-256 content hash of each image → cached `ExtractedScript`. Re-marks (rubric changes, post-feedback reviews) skip the expensive vision call.
2. **Confidence-based routing:** starts fully conservative (full review every time); relaxes to cheap auto-approval for high-confidence, previously-validated patterns as data proves reliability.
3. **Metrics via hooks:** `completion:response` hooks record per-agent latency and token counts to SQLite — speed improvements are measured, not assumed.

## Project Structure

```
smart-marking-system/
├── pyproject.toml              # uv-managed; deps: atomic-agents, instructor, openai
├── src/sms/
│   ├── schemas/                # BaseIOSchema contracts
│   │   ├── extraction.py
│   │   ├── marking.py
│   │   ├── feedback.py
│   │   └── reflection.py
│   ├── agents/
│   │   ├── extractor.py
│   │   ├── marker.py           # marker factory per subject
│   │   ├── reviewer.py         # reviewer factory per subject
│   │   ├── feedback.py
│   │   └── reflection.py
│   ├── pipeline/
│   │   ├── router.py
│   │   └── marking_pipeline.py
│   ├── memory/
│   │   ├── db.py
│   │   ├── providers.py
│   │   ├── extraction_cache.py
│   │   └── metrics.py
│   ├── subjects/
│   │   ├── math/
│   │   ├── language/
│   │   └── science/
│   └── cli.py                  # sms mark / sms reflect / sms evaluate / sms stats
└── tests/
    ├── unit/
    ├── integration/
    └── golden/                 # pre-marked math scripts (image + expected marks)
```

## Data Flow (one script)

images → content-hash check → Extractor (or cache) → PipelineRouter → subject Marker → subject Reviewer → merge/escalate → Feedback → persist run to SQLite

## Error Handling

- Schema validation failures → Instructor retries (via `parse:error` hooks); then escalate to teacher queue.
- Illegible handwriting → Extractor emits low confidence + `needs_human_transcription`; Marker skips; teacher queue.
- LLM API failures → framework retries; unresolvable → run marked `failed`, resumable from last completed stage (stage outputs persisted).

## Testing

- **Unit:** schema round-trips, provider injection, cache hits, router selection, verdict-merge logic. Pure Python, no LLM calls.
- **Integration:** fake instructor client returning canned schemas; pipeline logic end-to-end.
- **Eval:** `sms evaluate` runs the golden set and reports per-question agreement % — the "smarter over time" scoreboard.

## Future / Deferred

- Ensemble marking (Approach C) behind the same interfaces.
- Vector similarity cache for near-duplicate scripts.
- sympy-based math verification tool (atomic-forge style).
- FastAPI service layer; language and science subject factories.

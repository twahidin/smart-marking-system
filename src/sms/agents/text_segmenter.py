"""The text segmenter: the files path's counterpart to the vision extractor.

Where the extractor reads photographed pages, this agent reads the *rendered text* of the files a
student handed in and maps it onto the paper's parts, returning the same `ExtractedScript` the
extractor does. Every excerpt it quotes is prefixed with its source tag — `[prog.py L12-30]`,
`[results.xlsx Marks!B4]`, `[handwritten pages]` — because the submission detail page decides whether
a file was actually used by looking for `"[<file name>"` in the run's transcription.
"""
from typing import Any, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.schemas.extraction import ExtractedScript
from sms.schemas.segment import TextSegmentInput


def build_text_segmenter(client: Any, model: str = "gpt-5-mini", model_api_parameters: Optional[dict] = None
                         ) -> AtomicAgent[TextSegmentInput, ExtractedScript]:
    return AtomicAgent[TextSegmentInput, ExtractedScript](
        config=AgentConfig(
            client=client,
            model=model,
            model_api_parameters=model_api_parameters,
            system_prompt_generator=SystemPromptGenerator(
                background=[
                    "You map a student's submitted files (program source, Scratch pseudo-code, spreadsheet cells) and any "
                    "transcribed handwritten pages onto the parts of an assignment.",
                    "You copy evidence verbatim and never run, complete or correct the student's work.",
                ],
                steps=[
                    "Read every source. For each listed part, find the lines, blocks or cells that address it.",
                    "Put the relevant excerpt(s) in transcribed_answer, each prefixed with its source and location, e.g. "
                    "'[prog.py L12-30]', '[results.xlsx Marks!B4]', '[Cat script 2]', '[handwritten pages]'. Put supporting "
                    "context (helper functions, other cells the excerpt depends on) in workings.",
                    "If no source addresses a part, return an empty transcribed_answer and needs_human_transcription=true.",
                    "Confidence reflects how clearly the excerpt addresses the part, not code quality.",
                ],
                output_instructions=[
                    "Exactly one ExtractedQuestion per listed part, q_id equal to the part's q_id, in the given order.",
                    "Every excerpt opens with its source tag in square brackets: an opening bracket, the source's name "
                    "exactly as it is given to you, a space, the location, then a closing bracket — "
                    "'[prog.py L12-30]', '[results.xlsx Marks!B4]', '[handwritten pages]'. Never shorten, re-spell or "
                    "drop the name: a file whose tag never appears is reported to the teacher as unread.",
                    "Never paraphrase code, formulas or block text; quote them.",
                ],
            ),
        )
    )

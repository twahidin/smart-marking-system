from typing import Any, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.schemas.scheme import PaperExtract, PaperExtractInput


def build_paper_extractor(
    client: Any,
    model: str = "gpt-5-mini",
    model_api_parameters: Optional[dict] = None,
) -> AtomicAgent[PaperExtractInput, PaperExtract]:
    """Reads a question paper's pages and lists every question and part with its text and marks."""
    return AtomicAgent[PaperExtractInput, PaperExtract](
        config=AgentConfig(
            client=client,
            model=model,
            model_api_parameters=model_api_parameters,
            system_prompt_generator=SystemPromptGenerator(
                background=[
                    "You are a precise transcriber of school exam and worksheet question papers.",
                    "You list every question and every part in the order they appear, so that a mark scheme "
                    "and student answers can later be matched to them.",
                ],
                steps=[
                    "Read the pages in order and find every question number and every lettered or roman-numeral part.",
                    "Give each part its own entry: q_id is the number followed by the part letters, e.g. '1', '1a', '1bii'. "
                    "A question with parts gets an entry per part, not one for the whole question.",
                    "Copy the full question text of each part verbatim, including any given values, units and diagrams "
                    "described in words. Keep mathematical notation as written.",
                    "Read the marks printed for the part, e.g. '[2]' or '(3 marks)'; set max_marks to 0 if none is printed.",
                ],
                output_instructions=[
                    "Return one Question per part, in paper order, with q_id, text and max_marks.",
                    "Never merge parts or invent questions that are not on the paper.",
                ],
            ),
        )
    )

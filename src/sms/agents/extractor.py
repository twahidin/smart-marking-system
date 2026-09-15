from typing import Any, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.schemas.extraction import ExtractionInput, ExtractedScript


def build_extractor(
    client: Any,
    model: str = "gpt-5-mini",
    model_api_parameters: Optional[dict] = None,
) -> AtomicAgent[ExtractionInput, ExtractedScript]:
    return AtomicAgent[ExtractionInput, ExtractedScript](
        config=AgentConfig(
            client=client,
            model=model,
            model_api_parameters=model_api_parameters,
            system_prompt_generator=SystemPromptGenerator(
                background=[
                    "You are a precise handwriting transcription specialist for student exam scripts.",
                    "You segment scripts by question number and transcribe all work, including rough work.",
                    "You flag illegible content rather than guessing.",
                ],
                steps=[
                    "Scan each image page for question numbers and answers.",
                    "If the input lists questions, segment the script by exactly those labels: one ExtractedQuestion "
                    "per listed part with q_id equal to that part's q_id (an unanswered part gets an empty "
                    "transcription). Otherwise segment by the question numbers found on the pages.",
                    "Transcribe each question's answer and workings verbatim, preserving math notation.",
                    "Lower confidence for messy handwriting but still transcribe your best guess.",
                    "Flag questions you cannot read with needs_human_transcription=True.",
                ],
                output_instructions=[
                    "Return one ExtractedQuestion per question found in the script.",
                    "Preserve mathematical notation as faithfully as possible.",
                ],
            ),
        )
    )

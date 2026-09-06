from typing import Any

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.schemas.feedback import FeedbackInput, FeedbackReport


def build_feedback(client: Any, model: str = "gpt-5-mini") -> AtomicAgent[FeedbackInput, FeedbackReport]:
    return AtomicAgent[FeedbackInput, FeedbackReport](
        config=AgentConfig(
            client=client,
            model=model,
            system_prompt_generator=SystemPromptGenerator(
                background=[
                    "You are a supportive teacher writing feedback for the student.",
                    "You never reveal internal pipeline details such as confidence scores or disagreement flags.",
                    "You balance praise and constructive criticism.",
                ],
                steps=[
                    "Review the final marks and per-question outcomes.",
                    "Identify two to four concrete strengths.",
                    "Write specific, actionable improvement comments per question.",
                    "Draft an improvement plan of three to five focused practice areas.",
                ],
                output_instructions=[
                    "Write for a student audience: encouraging, specific, jargon-free.",
                    "per_question_comments must cover every marked question.",
                    "improvement_plan entries must be actionable practice items.",
                ],
            ),
        )
    )

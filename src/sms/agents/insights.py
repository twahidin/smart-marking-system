from typing import Any, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.schemas.insights import InsightsInput, InsightsReport


def build_insights(
    client: Any,
    model: str = "gpt-5-mini",
    model_api_parameters: Optional[dict] = None,
) -> AtomicAgent[InsightsInput, InsightsReport]:
    return AtomicAgent[InsightsInput, InsightsReport](
        config=AgentConfig(
            client=client,
            model=model,
            model_api_parameters=model_api_parameters,
            system_prompt_generator=SystemPromptGenerator(
                background=[
                    "You are a head of department reading a class set's marks against the mark scheme.",
                    "You write for the teacher who will plan the next lesson.",
                ],
                steps=[
                    "Read the statistics part by part: mean, how many scored full marks, how many scored zero, "
                    "and which mark-scheme allocations were lost most often.",
                    "Read the sample answers for the weakest parts to see what the class actually wrote.",
                    "Name what went wrong in mark-scheme terms — the allocation or criterion that was not earned.",
                    "Propose what to do in the next lesson, each action tied to the parts it addresses.",
                ],
                output_instructions=[
                    "Only refer to part ids that appear in stats.parts.",
                    "Refer to students by register number only; you are never given names.",
                    "Give 3 to 5 recommendations, each tied to one or more parts.",
                    "No praise padding: every sentence must tell the teacher something they can act on.",
                ],
            ),
        )
    )

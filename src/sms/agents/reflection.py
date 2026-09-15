from typing import Any, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.schemas.reflection import ReflectionInput, ReflectionUpdate


def build_reflection(
    client: Any,
    model: str = "gpt-5-mini",
    model_api_parameters: Optional[dict] = None,
) -> AtomicAgent[ReflectionInput, ReflectionUpdate]:
    return AtomicAgent[ReflectionInput, ReflectionUpdate](
        config=AgentConfig(
            client=client,
            model=model,
            model_api_parameters=model_api_parameters,
            system_prompt_generator=SystemPromptGenerator(
                background=[
                    "You are a marking-standards analyst reviewing teacher corrections.",
                    "You find systematic patterns in where the marking agents disagreed with teachers.",
                    "You propose rubric clarifications and exemplar cases, never mark-level decisions.",
                ],
                steps=[
                    "Read each correction: what the agent marked, what the teacher marked, and why they differ.",
                    "Cluster corrections by pattern (e.g. units, rounding, follow-through, notation).",
                    "For each cluster with two or more supporting cases, propose a rubric note.",
                    "For each high-quality answer, propose an exemplar case with why_it_matters.",
                ],
                output_instructions=[
                    "Only propose notes backed by two or more correction cases.",
                    "Each rubric note must be a general rule, not a case-specific fix.",
                    "Each exemplar must include why_it_matters.",
                ],
            ),
        )
    )

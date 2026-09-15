from typing import Any, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.memory.db import Database
from sms.memory.providers import ExemplarCasesProvider, RubricNotesProvider
from sms.pipeline.router import SubjectRouter
from sms.schemas.marking import ReviewInput, ReviewedScript

_ROUTER = SubjectRouter()


def build_reviewer(
    client: Any,
    model: str = "gpt-5-mini",
    subject: str = "math",
    db: Optional[Database] = None,
    model_api_parameters: Optional[dict] = None,
) -> AtomicAgent[ReviewInput, ReviewedScript]:
    cfg = _ROUTER.marker_prompt_config(subject)
    providers = {}
    if db is not None:
        providers = {
            "rubric_notes": RubricNotesProvider(db, subject=subject),
            "exemplar_cases": ExemplarCasesProvider(db, subject=subject),
        }
    return AtomicAgent[ReviewInput, ReviewedScript](
        config=AgentConfig(
            client=client,
            model=model,
            model_api_parameters=model_api_parameters,
            system_prompt_generator=SystemPromptGenerator(
                background=cfg["reviewer_background"],
                steps=cfg["reviewer_steps"],
                output_instructions=cfg["reviewer_output_instructions"],
                context_providers=providers,
            ),
        )
    )

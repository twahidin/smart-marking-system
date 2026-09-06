from typing import Any, Dict, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import BaseDynamicContextProvider, SystemPromptGenerator

from sms.memory.db import Database
from sms.memory.providers import ExemplarCasesProvider, RubricNotesProvider
from sms.pipeline.router import SubjectRouter
from sms.schemas.marking import MarkingInput, MarkedScript

_ROUTER = SubjectRouter()


def _build_providers(db: Optional[Database], subject: str) -> Dict[str, BaseDynamicContextProvider]:
    if db is None:
        return {}
    return {
        "rubric_notes": RubricNotesProvider(db, subject=subject),
        "exemplar_cases": ExemplarCasesProvider(db, subject=subject),
    }


def build_marker(
    client: Any,
    model: str = "gpt-5-mini",
    subject: str = "math",
    db: Optional[Database] = None,
) -> AtomicAgent[MarkingInput, MarkedScript]:
    cfg = _ROUTER.marker_prompt_config(subject)
    return AtomicAgent[MarkingInput, MarkedScript](
        config=AgentConfig(
            client=client,
            model=model,
            system_prompt_generator=SystemPromptGenerator(
                background=cfg["background"],
                steps=cfg["steps"],
                output_instructions=cfg["output_instructions"],
                context_providers=_build_providers(db, _ROUTER.resolve(subject)),
            ),
        )
    )

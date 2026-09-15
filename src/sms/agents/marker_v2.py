from typing import Any, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.agents.marker import _build_providers
from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.schemas.marking_v2 import MarkedScriptV2, MarkingInputV2

_ROUTER = SubjectRouter()


def build_marker_v2(
    client: Any,
    model: str = "gpt-5-mini",
    kind: str = "mark_scheme",
    subject: str = "math",
    db: Optional[Database] = None,
    model_api_parameters: Optional[dict] = None,
) -> AtomicAgent[MarkingInputV2, MarkedScriptV2]:
    """Per-part marker: prompts by scheme kind ('mark_scheme' / 'rubric'); the subject only selects the
    learned rubric-notes / exemplar context providers (when a db is given)."""
    cfg = _ROUTER.scheme_prompt_config(kind)
    subject = _ROUTER.resolve(subject)
    return AtomicAgent[MarkingInputV2, MarkedScriptV2](
        config=AgentConfig(
            client=client,
            model=model,
            model_api_parameters=model_api_parameters,
            system_prompt_generator=SystemPromptGenerator(
                background=cfg["background"],
                steps=cfg["steps"],
                output_instructions=cfg["output_instructions"],
                context_providers=_build_providers(db, subject),
            ),
        )
    )

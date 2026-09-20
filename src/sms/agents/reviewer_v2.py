from typing import Any, Optional

from atomic_agents import AgentConfig, AtomicAgent
from atomic_agents.context import SystemPromptGenerator

from sms.agents.marker import _build_providers
from sms.agents.marker_v2 import _subject_note
from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.schemas.marking_v2 import ReviewInputV2, ReviewedScriptV2

_ROUTER = SubjectRouter()


def build_reviewer_v2(
    client: Any,
    model: str = "gpt-5-mini",
    kind: str = "mark_scheme",
    subject: str = "math",
    db: Optional[Database] = None,
    model_api_parameters: Optional[dict] = None,
) -> AtomicAgent[ReviewInputV2, ReviewedScriptV2]:
    """Per-part reviewer: blind second marking with APPROVE / ADJUST / ESCALATE per part or criterion.
    Like the marker, MT / Computing get an extra background sentence from the subject's prompt module."""
    cfg = _ROUTER.scheme_prompt_config(kind)
    subject = _ROUTER.resolve(subject)
    note = _subject_note(subject)
    background = cfg["reviewer_background"] + [note] if note else cfg["reviewer_background"]
    return AtomicAgent[ReviewInputV2, ReviewedScriptV2](
        config=AgentConfig(
            client=client,
            model=model,
            model_api_parameters=model_api_parameters,
            system_prompt_generator=SystemPromptGenerator(
                background=background,
                steps=cfg["reviewer_steps"],
                output_instructions=cfg["reviewer_output_instructions"],
                context_providers=_build_providers(db, subject),
            ),
        )
    )

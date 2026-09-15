from typing import Any, List, Optional, Type

from atomic_agents import AgentConfig, AtomicAgent, BaseIOSchema
from atomic_agents.context import BaseDynamicContextProvider, SystemPromptGenerator

from sms.schemas.scheme import Question, RubricExtract, SchemeExtract, SchemeExtractInput, q_label

SCHEME_KINDS = ("mark_scheme", "rubric")


class QuestionListProvider(BaseDynamicContextProvider):
    """Puts the paper's question list into the system prompt so scheme rows align by q_id."""

    def __init__(self, questions: List[Question]):
        super().__init__(title="Questions on the paper")
        self.questions = questions

    def get_info(self) -> str:
        return "\n".join(f"- q_id '{q.q_id}' ({q_label(q.q_id)}), {q.max_marks} marks: {q.text}".rstrip(": ")
                         for q in self.questions)


_MARK_SCHEME = {
    "background": [
        "You are a precise transcriber of school mark schemes for maths and science papers.",
        "You turn the scheme into one row per question part, keeping the examiner's mark allocations exactly.",
    ],
    "steps": [
        "Read the scheme pages in order and find the row for each question part.",
        "Use the q_id of the matching question from the paper's question list when one is given; otherwise use the "
        "number and part letters as printed, e.g. '1a', '2bii'.",
        "Copy the expected answer or method into `answer`.",
        "List the mark allocations in scheme order with the labels the scheme uses (M1, A1, B1, M1dep, ...) and the "
        "marks each is worth. If the scheme only gives a total, use one allocation labelled 'B<n>' for that total.",
        "Put accept / reject notes, alternative methods, follow-through (ECF) and special cases into `notes`.",
    ],
    "output_instructions": [
        "Return one MarkSchemeEntry per question part, in scheme order.",
        "Preserve allocation labels such as M1, A1 and B1 exactly; never invent allocations or change their marks.",
    ],
}

_RUBRIC = {
    "background": [
        "You are a precise transcriber of assessment rubrics for essays and open-response work.",
        "You turn the rubric into criteria, each with its bands (levels) and the marks and descriptor of every band.",
    ],
    "steps": [
        "Read the rubric pages and find every criterion (e.g. Content, Organisation, Language).",
        "For each criterion list its bands from best to worst with the band name as printed, the marks (or the top "
        "mark of a range) and the full descriptor text.",
    ],
    "output_instructions": [
        "Return one RubricCriterionBands per criterion with all of its bands.",
        "Keep band names and descriptors as written; never invent bands.",
    ],
}


def build_scheme_extractor(
    client: Any,
    model: str = "gpt-5-mini",
    kind: str = "mark_scheme",
    questions: Optional[List[Question]] = None,
    model_api_parameters: Optional[dict] = None,
) -> AtomicAgent:
    """Reads mark scheme (kind 'mark_scheme') or rubric (kind 'rubric') pages into scheme rows."""
    if kind not in SCHEME_KINDS:
        raise ValueError(f"scheme extractor kind must be one of {SCHEME_KINDS}, got {kind!r}")
    cfg = _MARK_SCHEME if kind == "mark_scheme" else _RUBRIC
    output: Type[BaseIOSchema] = SchemeExtract if kind == "mark_scheme" else RubricExtract
    providers = {"questions": QuestionListProvider(list(questions))} if questions else {}
    return AtomicAgent[SchemeExtractInput, output](  # type: ignore[valid-type]
        config=AgentConfig(
            client=client,
            model=model,
            model_api_parameters=model_api_parameters,
            system_prompt_generator=SystemPromptGenerator(
                background=cfg["background"],
                steps=cfg["steps"],
                output_instructions=cfg["output_instructions"],
                context_providers=providers,
            ),
        )
    )

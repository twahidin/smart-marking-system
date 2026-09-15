"""Canonical shapes of an assignment's question list and its mark scheme / rubric — the JSON stored
in assignment_templates.questions_json and scheme_json and the models the extraction agents fill in."""
import re
from typing import Any, Iterable, List, Union

from pydantic import BaseModel, Field


class Question(BaseModel):
    q_id: str = Field(min_length=1, description="Question or part id in the short form '1a', '2bii', '3' (number, then "
                                                "letter, then roman numerals; no 'Q', spaces or brackets)")
    text: str = Field(default="", description="The full question text for this part")
    max_marks: int = Field(ge=0, description="Marks shown on the paper for this part (0 if absent)")


class MarkPoint(BaseModel):
    label: str = Field(description="Allocation label as in the scheme, e.g. 'M1', 'A1', 'B1'")
    marks: int = Field(ge=0, description="Marks this allocation is worth")


class MarkSchemeEntry(BaseModel):
    q_id: str = Field(min_length=1, description="Question or part id this row marks, matching the paper's q_id")
    answer: str = Field(default="", description="The expected answer or method")
    marks: List[MarkPoint] = Field(default_factory=list, description="Mark allocations in scheme order")
    notes: str = Field(default="", description="Accept / reject notes, alternatives, ECF")


class Band(BaseModel):
    band: str = Field(description="Band name, e.g. 'A' or '4'")
    marks: int = Field(ge=0, description="Marks awarded for this band")
    descriptor: str = Field(default="", description="What an answer in this band looks like")


class RubricCriterionBands(BaseModel):
    criterion: str = Field(min_length=1, description="Criterion name, e.g. 'Organisation'")
    bands: List[Band] = Field(default_factory=list, description="Bands from best to worst")


_Q_ID = re.compile(r"^(q)?(\d+)([a-z])?([ivx]+)?$", re.IGNORECASE)
_ROMAN = re.compile(r"^[ivx]+$")
_QID_NOISE = re.compile(r"[\s().]+")


def norm_qid(q_id: Any) -> str:
    """Matching key for a question id, so the extractor's "Q1(a)" / "1 (a)" and the scheme's "1a" meet:
    lowercase, a leading "q" before a digit dropped, spaces, parentheses and dots removed. Every place that
    looks an extracted question up by a scheme row's q_id compares these keys, never the raw strings."""
    key = _QID_NOISE.sub("", str(q_id or "")).lower()
    if len(key) > 1 and key[0] == "q" and key[1].isdigit():
        key = key[1:]
    return key


def q_label(q_id: str) -> str:
    """Teacher-facing label for a question id: "1a" -> "1(a)", "2bii" -> "2(b)(ii)", "4iii" -> "4(iii)",
    "q1" -> "Q1". Anything else (already formatted, free text) is returned unchanged."""
    raw = (q_id or "").strip()
    m = _Q_ID.match(raw)
    if not m:
        return raw
    prefix, number, letter, roman = m.groups()
    suffix = (letter or "") + (roman or "")
    if len(suffix) > 1 and _ROMAN.match(suffix.lower()):
        # "4iii": the whole suffix is one roman part, not the letter "i" plus "ii".
        parts = [suffix.lower()]
    else:
        parts = [p.lower() for p in (letter, roman) if p]
    return ("Q" if prefix else "") + number + "".join(f"({p})" for p in parts)


def _get(item: Any, key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def scheme_total(kind: str, questions: Iterable[Union[Question, dict]], scheme: Iterable[Any]) -> int:
    """Total marks an assignment is out of. mark_scheme: the allocation total of each question's
    scheme row, falling back to the question's max_marks when it has no row (scheme rows alone when
    there are no questions). rubric: the best band of every criterion. criteria: the questions' marks."""
    questions = list(questions)
    scheme = list(scheme)
    if kind == "rubric":
        return sum(max((int(_get(b, "marks", 0)) for b in _get(c, "bands", []) or []), default=0) for c in scheme)
    if kind == "mark_scheme":
        row_totals = {_get(s, "q_id"): sum(int(_get(m, "marks", 0)) for m in _get(s, "marks", []) or []) for s in scheme}
        if not questions:
            return sum(row_totals.values())
        return sum(row_totals.get(_get(q, "q_id"), int(_get(q, "max_marks", 0))) for q in questions)
    return sum(int(_get(q, "max_marks", 0)) for q in questions)


# --- extraction agent IO ----------------------------------------------------------------------

import instructor  # noqa: E402
from atomic_agents import BaseIOSchema  # noqa: E402


class PaperExtractInput(BaseIOSchema):
    """Input to the paper extractor: the question paper's pages and a short hint about the paper."""

    images: List[instructor.Image] = Field(..., description="Question paper pages as images, in order")
    hint: str = Field(default="", description="Assignment title / subject, e.g. 'Sec 4 Maths — Quadratics'")


class PaperExtract(BaseIOSchema):
    """Paper extractor output: every question and part on the paper, in order."""

    questions: List[Question] = Field(default_factory=list, description="Questions and parts in paper order")


class SchemeExtractInput(BaseIOSchema):
    """Input to the scheme extractor: the mark scheme / rubric pages and the paper's question list."""

    images: List[instructor.Image] = Field(..., description="Mark scheme or rubric pages as images, in order")
    questions: List[Question] = Field(default_factory=list, description="The paper's questions, so rows align by q_id")


class SchemeExtract(BaseIOSchema):
    """Scheme extractor output for a mark scheme: one row per question part."""

    items: List[MarkSchemeEntry] = Field(default_factory=list, description="Mark scheme rows in scheme order")


class RubricExtract(BaseIOSchema):
    """Scheme extractor output for a rubric: one entry per criterion with its bands."""

    items: List[RubricCriterionBands] = Field(default_factory=list, description="Criteria with their bands")

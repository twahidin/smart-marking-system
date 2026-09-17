"""What the insights agent is shown and what it writes back.

The input carries the class statistics and a handful of sample answers from the weakest parts.
Neither side ever carries a student's name or id: a student is a register number throughout, so
the narrative can name who needs help without a name reaching the model."""
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema


class Sample(BaseModel):
    part: str = Field(..., description="Part id the answer belongs to, as in stats.parts")
    reg_no: int = Field(..., description="The student's register number in the class")
    extracted: str = Field(..., description="The student's answer as transcribed")
    awarded: int = Field(..., description="Marks awarded for this part")
    max: int = Field(..., description="Marks available for this part")
    justification: str = Field(default="", description="Why the marker awarded what it did")


class Gap(BaseModel):
    part_ids: List[str] = Field(..., description="Parts this gap shows up in")
    title: str = Field(..., description="Short name for the gap, in mark-scheme terms")
    what_went_wrong: str = Field(..., description="What the class actually did instead")
    students_affected: int = Field(..., ge=0, description="How many marked scripts show it")


class Recommendation(BaseModel):
    title: str = Field(..., description="What to do in the next lesson")
    detail: str = Field(..., description="How to do it, concretely")
    part_ids: List[str] = Field(..., description="Parts this addresses")


class Support(BaseModel):
    reg_nos: List[int] = Field(..., description="Register numbers who need help")
    focus: str = Field(..., description="What to work on with them")


class InsightsInput(BaseIOSchema):
    """Input for the Insights agent: one assignment's class statistics and sample answers."""

    assignment_title: str = Field(..., description="Title of the assignment")
    subject: str = Field(..., description="Subject, e.g. 'math'")
    scheme_kind: str = Field(..., description="mark_scheme, rubric or criteria")
    stats: Dict[str, Any] = Field(..., description="Class statistics; students carry reg_no, never a name")
    samples: List[Sample] = Field(default_factory=list, description="Answers from the weakest parts")


class InsightsReport(BaseIOSchema):
    """The teacher-facing narrative over one assignment's marks."""

    summary: str = Field(..., description="How the class did, in a short paragraph")
    strengths: List[str] = Field(default_factory=list, description="What the class can already do")
    gaps: List[Gap] = Field(default_factory=list, description="Where the marks were lost and why")
    recommendations: List[Recommendation] = Field(default_factory=list, description="Next-lesson actions")
    students_to_support: List[Support] = Field(default_factory=list, description="Who to follow up, by register number")

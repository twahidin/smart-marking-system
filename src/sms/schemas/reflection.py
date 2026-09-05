from typing import List

from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema


class RubricNote(BaseModel):
    subject: str = Field(..., description="Subject this note applies to")
    note: str = Field(..., description="General rule distilled from corrections")
    source_run_ids: List[str] = Field(default_factory=list, description="Runs that motivated this note")


class ExemplarCase(BaseModel):
    subject: str = Field(..., description="Subject")
    topic: str = Field(..., description="Topic, e.g. 'quadratic equations'")
    q_id: str = Field(..., description="Question identifier")
    answer_text: str = Field(..., description="The student answer that scored well")
    awarded: int = Field(..., ge=0, description="Marks awarded")
    max_score: int = Field(..., ge=0, description="Maximum marks for the question")
    why_it_matters: str = Field(..., description="What makes this answer worth copying")


class CorrectionRow(BaseModel):
    run_id: str = Field(..., description="Marking run id")
    q_id: str = Field(..., description="Question identifier")
    subject: str = Field(..., description="Subject")
    rubric_json: str = Field(..., description="Rubric at time of marking, as JSON")
    extracted_answer: str = Field(..., description="Transcribed student answer")
    agent_mark: int = Field(..., description="What the agent awarded")
    teacher_mark: int = Field(..., description="What the teacher awarded")
    reason: str = Field(default="", description="Teacher's reason for the correction")


class ReflectionInput(BaseIOSchema):
    """Input for the Reflection agent: recent teacher corrections."""

    corrections: List[CorrectionRow] = Field(..., description="Recent corrections where agent != teacher")


class ReflectionUpdate(BaseIOSchema):
    """Nightly reflection output: distilled rubric notes and exemplar cases."""

    rubric_notes: List[RubricNote] = Field(..., description="Clarifications to add to rubric context")
    exemplar_cases: List[ExemplarCase] = Field(..., description="Good marked-answer examples per topic")
    prompt_tweaks: List[str] = Field(default_factory=list, description="Suggested prompt adjustments")

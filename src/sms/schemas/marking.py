from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema

from sms.schemas.extraction import ExtractedScript


class RubricCriterion(BaseModel):
    id: str = Field(..., description="Criterion identifier, e.g. 'c1'")
    description: str = Field(..., description="What the criterion assesses")
    max_score: int = Field(..., ge=0, description="Maximum marks for this criterion")


class Rubric(BaseModel):
    criterion_defs: List[RubricCriterion] = Field(..., description="Criteria for one assignment")


class MarkingInput(BaseIOSchema):
    """Input to the Marker agent: extraction plus rubric."""

    extracted: ExtractedScript = Field(..., description="Extractor output")
    rubric: Rubric = Field(..., description="Marking criteria for the assignment")
    assignment_context: str = Field(..., description="Subject/level context")


class MarkedQuestion(BaseModel):
    q_id: str = Field(..., description="Question identifier")
    criterion_scores: List[int] = Field(..., description="Score per rubric criterion, same length as rubric")
    total: int = Field(..., description="Sum of criterion scores")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Marking confidence 0-1")
    rationale: str = Field(..., description="Why these marks were awarded")
    evidence: str = Field(default="", description="Quoted student text supporting the mark")


class MarkedScript(BaseIOSchema):
    """Marker output: marks per question with rationale and confidence."""

    marks: List[MarkedQuestion] = Field(..., description="Marks per question")


class ReviewInput(BaseIOSchema):
    """Input to the Reviewer agent: extraction + marks + rubric (marker rationale stripped)."""

    extracted: ExtractedScript = Field(..., description="Extractor output")
    marks: MarkedScript = Field(..., description="Marker output with rationale hidden")
    rubric: Rubric = Field(..., description="Marking criteria")
    assignment_context: str = Field(..., description="Subject/level context")


class ReviewVerdict(str, Enum):
    APPROVE = "APPROVE"
    ADJUST = "ADJUST"
    ESCALATE = "ESCALATE"


class ReviewVerdictItem(BaseModel):
    q_id: str = Field(..., description="Question identifier")
    verdict: ReviewVerdict = Field(..., description="APPROVE, ADJUST, or ESCALATE")
    adjusted_criterion_scores: Optional[List[int]] = Field(default=None, description="New scores if ADJUST")
    adjusted_total: Optional[int] = Field(default=None, description="New total if ADJUST")
    reviewer_note: str = Field(default="", description="Reviewer's reasoning")


class ReviewedScript(BaseIOSchema):
    """Reviewer output: per-question verdicts and final marks."""

    verdicts: List[ReviewVerdictItem] = Field(..., description="Per-question verdicts")
    final_marks: List[MarkedQuestion] = Field(..., description="Merged final marks")
    disagreement_flags: List[str] = Field(default_factory=list, description="q_ids with disagreements")

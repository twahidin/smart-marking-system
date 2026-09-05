from typing import List, Optional

from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema

from sms.schemas.marking import MarkedScript, ReviewedScript


class FeedbackInput(BaseIOSchema):
    """Input to the Feedback agent: reviewed script plus final marks."""

    reviewed: ReviewedScript = Field(..., description="Reviewer output")
    final_marks: MarkedScript = Field(..., description="Merged final marks")
    final_result_set: bool = Field(..., description="True if marks are final (no escalation pending)")
    student_context: Optional[str] = Field(default=None, description="Student name/context if known")


class PerQuestionComment(BaseModel):
    q_id: str = Field(..., description="Question identifier")
    comment: str = Field(..., description="Feedback for this question")
    suggested_action: str = Field(..., description="What the student should practise next")


class FeedbackReport(BaseIOSchema):
    """Student-facing feedback report."""

    summary: str = Field(..., description="Two or three sentence overview")
    strengths: List[str] = Field(..., description="Concrete strengths demonstrated")
    per_question_comments: List[PerQuestionComment] = Field(..., description="Comment per question")
    improvement_plan: List[str] = Field(..., description="3-5 actionable practice areas")
    next_steps: List[str] = Field(..., description="Concrete next actions for the student")

from typing import List

import instructor
from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema

from sms.schemas.scheme import Question


class ExtractionInput(BaseIOSchema):
    """Input for the Extractor agent: script images, assignment context and (optionally) the paper's
    question list to segment by."""

    assignment_context: str = Field(..., description="Subject, level, question count of the assignment")
    images: List[instructor.Image] = Field(..., description="Script pages as images")
    questions: List[Question] = Field(
        default_factory=list,
        description="When given, the paper's question parts: return exactly one ExtractedQuestion per part, "
                    "q_id equal to the part's q_id. When empty, segment by the question numbers on the pages.",
    )


class ExtractedQuestion(BaseModel):
    q_id: str = Field(..., description="Question or part id in the short form '1a', '2bii', '3' (number, then letter, then "
                                       "roman numerals; no 'Q', spaces or brackets) — exactly the q_id of the matching "
                                       "question when a question list is given")
    transcribed_answer: str = Field(..., description="Student's transcribed answer")
    workings: str = Field(default="", description="Transcribed working steps, if any")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Transcription confidence 0-1")
    needs_human_transcription: bool = Field(default=False, description="True if illegible")


class ExtractedScript(BaseIOSchema):
    """Extractor output: per-question transcription of a student script."""

    questions: List[ExtractedQuestion] = Field(..., description="Transcribed questions")

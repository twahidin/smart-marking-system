from typing import List

import instructor
from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema


class ExtractionInput(BaseIOSchema):
    """Input for the Extractor agent: script images and assignment context."""

    assignment_context: str = Field(..., description="Subject, level, question count of the assignment")
    images: List[instructor.Image] = Field(..., description="Script pages as images")


class ExtractedQuestion(BaseModel):
    q_id: str = Field(..., description="Question identifier, e.g. 'q1'")
    transcribed_answer: str = Field(..., description="Student's transcribed answer")
    workings: str = Field(default="", description="Transcribed working steps, if any")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Transcription confidence 0-1")
    needs_human_transcription: bool = Field(default=False, description="True if illegible")


class ExtractedScript(BaseIOSchema):
    """Extractor output: per-question transcription of a student script."""

    questions: List[ExtractedQuestion] = Field(..., description="Transcribed questions")

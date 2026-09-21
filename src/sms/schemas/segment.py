"""Input shape of the text segmenter: the rendered text of everything a student handed in — program
source, Scratch pseudo-code, spreadsheet cells, and the transcription of any photographed pages —
plus the paper's parts to map it onto. The segmenter's output is an `ExtractedScript`, the same shape
the vision extractor produces, so the marker and reviewer downstream cannot tell the two apart."""
from typing import List

from pydantic import BaseModel, Field

from atomic_agents import BaseIOSchema

from sms.schemas.scheme import Question


class TextSource(BaseModel):
    name: str = Field(..., description="File name, or 'handwritten pages' for the transcription of photographed pages")
    text: str = Field(..., description="The rendered content: numbered source lines, Scratch pseudo-code, or cells")


class TextSegmentInput(BaseIOSchema):
    """Input for the text segmenter: rendered files (and any page transcription) plus the paper's parts."""

    assignment_context: str = Field(..., description="Subject, level, task summary")
    questions: List[Question] = Field(default_factory=list,
                                      description="The paper's parts: return exactly one ExtractedQuestion per part")
    sources: List[TextSource] = Field(..., description="Every source the student handed in")

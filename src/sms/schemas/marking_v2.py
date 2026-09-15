"""Per-part marking (version 2): a script is marked question part by question part against the
assignment's mark scheme, or criterion by criterion against its rubric. These are the marker and
reviewer IO models and the shape stored in marking_runs.final_marks_json with "version": 2."""
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

from atomic_agents import BaseIOSchema

from sms.schemas.extraction import ExtractedScript
from sms.schemas.marking import ReviewVerdict
from sms.schemas.scheme import MarkSchemeEntry, Question, RubricCriterionBands

SchemeKind = Literal["mark_scheme", "rubric"]
SCHEME_KINDS = ("mark_scheme", "rubric")


class AllocationMark(BaseModel):
    label: str = Field(description="Allocation label exactly as in the scheme row, e.g. 'M1', 'A1', 'B1'")
    marks: int = Field(ge=0, description="Marks this allocation is worth, copied from the scheme row")
    got: bool = Field(description="True if the student earned this allocation")
    why: str = Field(default="", description="One line on why it was earned or lost, quoting the work")


class PartMark(BaseModel):
    q_id: str = Field(min_length=1, description="The question part's q_id, matching the paper and scheme")
    awarded: List[AllocationMark] = Field(default_factory=list,
                                          description="Every allocation of the scheme row, in scheme order, with got true/false")
    total: int = Field(ge=0, description="Marks awarded for this part = sum of the allocations marked got")
    justification: str = Field(default="", description="Why these marks, referencing the allocations (M1 for ..., A1 lost because ...)")
    in_scheme: bool = Field(default=True, description="False when the answer is not covered by the scheme row "
                                                      "(a different method, partly legible) so a teacher must decide")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Marking confidence 0-1")

    @model_validator(mode="after")
    def _total_matches_allocations(self) -> "PartMark":
        # On PartMark (not the script) so a reviewer's `adjusted` part is checked too. Skipped when no
        # allocation is listed: an in_scheme=False part may carry only a proposed total.
        if self.awarded and self.total != sum(a.marks for a in self.awarded if a.got):
            raise ValueError(f"part {self.q_id}: total must equal the sum of the allocations marked got")
        return self


class RubricMark(BaseModel):
    criterion: str = Field(min_length=1, description="Criterion name exactly as in the rubric")
    band: str = Field(description="Band name exactly as in the rubric, e.g. 'A' or '4'")
    marks: int = Field(ge=0, description="Marks for that band as given in the rubric")
    descriptor_met: str = Field(default="", description="The band descriptor text the response meets")
    justification: str = Field(default="", description="Why this band, quoting the response")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Marking confidence 0-1")


class MarkedScriptV2(BaseIOSchema):
    """Marker output (v2): one PartMark per question part for a mark scheme, or one RubricMark per
    criterion for a rubric."""

    kind: SchemeKind = Field(description="'mark_scheme' (fill parts) or 'rubric' (fill rubric)")
    parts: List[PartMark] = Field(default_factory=list, description="Per-part marks; empty for a rubric")
    rubric: List[RubricMark] = Field(default_factory=list, description="Per-criterion marks; empty for a mark scheme")


class MarkingInputV2(BaseIOSchema):
    """Input to the v2 Marker: the transcription plus the assignment's questions, scheme/rubric and notes."""

    kind: SchemeKind = Field(description="'mark_scheme' or 'rubric'")
    extracted: ExtractedScript = Field(description="Extractor output, one entry per question part")
    questions: List[Question] = Field(default_factory=list, description="The paper's questions and parts")
    scheme: Union[List[MarkSchemeEntry], List[RubricCriterionBands]] = Field(
        default_factory=list, description="Mark scheme rows (by q_id) or rubric criteria with bands")
    notes: str = Field(default="", description="Teacher's notes: accept/reject rules, ECF, penalties")


class ReviewInputV2(BaseIOSchema):
    """Input to the v2 Reviewer: the same as the marker's input plus the marks with justifications removed."""

    kind: SchemeKind = Field(description="'mark_scheme' or 'rubric'")
    extracted: ExtractedScript = Field(description="Extractor output, one entry per question part")
    questions: List[Question] = Field(default_factory=list, description="The paper's questions and parts")
    scheme: Union[List[MarkSchemeEntry], List[RubricCriterionBands]] = Field(
        default_factory=list, description="Mark scheme rows (by q_id) or rubric criteria with bands")
    notes: str = Field(default="", description="Teacher's notes: accept/reject rules, ECF, penalties")
    marks: MarkedScriptV2 = Field(description="The marker's marks with justifications stripped")


class ReviewVerdictV2(BaseModel):
    q_id: str = Field(min_length=1, description="The part's q_id, or the criterion name for a rubric")
    verdict: ReviewVerdict = Field(description="APPROVE, ADJUST or ESCALATE")
    adjusted: Optional[Union[PartMark, RubricMark]] = Field(
        default=None, description="Your corrected PartMark / RubricMark when the verdict is ADJUST")
    reviewer_note: str = Field(default="", description="Reviewer's reasoning")


class ReviewedScriptV2(BaseIOSchema):
    """Reviewer output (v2): one verdict per marked part or criterion."""

    verdicts: List[ReviewVerdictV2] = Field(default_factory=list, description="One verdict per part / criterion")

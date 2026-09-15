"""Pure builder: the submission detail (as the API serialises it) + its assignment -> a Record.
Nothing here touches the database or renders a file."""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sms.schemas.scheme import q_label

TEACHER_TO_REVIEW = "Teacher to review"
ANSWER_LIMIT = 600
ELLIPSIS = "…"

# Queue reasons (marking_pipeline_v2 and the v1 pipeline) -> what the teacher reads in the record.
REASON_TEXT: Dict[str, str] = {
    "illegible": "Unclear handwriting",
    "not in scheme": "Answer not in the scheme — different method",
    "reviewer escalated": "Marker and reviewer disagreed",
    "marker/reviewer disagree": "Marker and reviewer disagreed",
    "low confidence": "Low confidence",
    # v1 wording (marking_pipeline)
    "low marker confidence": "Low confidence",
    "illegible transcription": "Unclear handwriting",
}

# Characters neither Word XML nor openpyxl accept; \n and \t are kept.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitise(text: Any) -> str:
    """LLM text as a str with control characters removed (verbatim otherwise)."""
    if text is None:
        return ""
    return _CONTROL.sub("", str(text))


@dataclass
class RecordRow:
    key: str                     # q_id or criterion
    label: str                   # "1(a)", "Q1", "Content"
    scheme_answer: str
    student_answer: str
    justification: str
    awarded: str                 # "2 / 2", "3 / 3 (teacher)" or "Teacher to review"
    teacher: str                 # always empty: the teacher's own column
    to_review: bool
    awarded_marks: Optional[int]  # numeric awarded mark for the markbook; None while to review
    max_marks: int


@dataclass
class Record:
    title: str
    student: str
    marked_at: str
    model: str
    rows: List[RecordRow]
    total_awarded: int
    total_upper: int
    total_max: int
    to_review_count: int
    rubric_page: Optional[List[Dict[str, Any]]]  # rubric assignments: [{criterion, bands, awarded_band}]
    submission_id: int
    kind: str                                    # mark_scheme | rubric | criteria (v1)

    @property
    def total_text(self) -> str:
        """"4" when settled, "4–6" while parts are still to review."""
        return str(self.total_awarded) if self.total_upper == self.total_awarded else f"{self.total_awarded}–{self.total_upper}"


def reason_text(reason: Optional[str]) -> str:
    """The teacher-facing reason for an escalated part; unknown reasons read "Teacher to review"."""
    if not reason:
        return TEACHER_TO_REVIEW
    return REASON_TEXT.get(reason.strip().lower(), TEACHER_TO_REVIEW)


def truncate(text: str, limit: int = ANSWER_LIMIT) -> str:
    text = sanitise(text).strip()
    return text if len(text) <= limit else text[:limit] + ELLIPSIS


def student_answer(extracted: str, workings: str, illegible: bool) -> str:
    if illegible:
        return "(illegible)"
    text = (extracted or "").strip()
    workings = (workings or "").strip()
    if workings:
        text = f"{text}\nWorkings: {workings}" if text else f"Workings: {workings}"
    return truncate(text)


def _awarded(total: int, mx: int, escalated: bool, teacher_total: Optional[int]):
    """(awarded text, numeric awarded or None, to_review)."""
    if teacher_total is not None:
        return f"{teacher_total} / {mx} (teacher)", teacher_total, False
    if escalated:
        return TEACHER_TO_REVIEW, None, True
    return f"{total} / {mx}", total, False


def _scheme_text_v2(kind: str, part: dict) -> str:
    scheme = part.get("scheme") or {}
    if kind == "rubric":
        lines = [part.get("label") or part.get("q_id") or ""]
        lines += [f"{b.get('band', '')} ({b.get('marks', 0)}): {b.get('descriptor', '')}".rstrip(": ") for b in scheme.get("bands") or []]
        return "\n".join(lines)
    if not scheme:
        return "(no scheme row)"
    labels = " ".join(m.get("label", "") for m in scheme.get("marks") or [])
    text = (scheme.get("answer") or "").strip()
    if labels:
        text = f"{text}  [{labels}]" if text else f"[{labels}]"
    notes = (scheme.get("notes") or "").strip()
    return f"{text}\n{notes}" if notes else text


def _row_v2(kind: str, part: dict) -> RecordRow:
    teacher = part.get("teacher") or None
    teacher_total = int(teacher["total"]) if teacher and "total" in teacher else None
    escalated = bool(part.get("escalated"))
    mx = int(part.get("max") or 0)
    total = int(part.get("total") or 0)
    if escalated and teacher_total is None:
        justification = reason_text(part.get("reason"))
    elif kind == "rubric":
        band = part.get("band") or ""
        j = (part.get("justification") or "").strip()
        justification = f"Band {band}: {j}".rstrip(": ") if band else j
    else:
        justification = (part.get("justification") or "").strip()
    awarded, marks, to_review = _awarded(total, mx, escalated, teacher_total)
    return _clean(RecordRow(
        key=part.get("q_id") or "", label=part.get("label") or q_label(part.get("q_id") or ""),
        scheme_answer=_scheme_text_v2(kind, part),
        student_answer=student_answer(part.get("extracted", ""), part.get("workings", ""), bool(part.get("illegible"))),
        justification=justification, awarded=awarded, teacher="", to_review=to_review, awarded_marks=marks, max_marks=mx,
    ))


def _clean(row: RecordRow) -> RecordRow:
    for name in ("key", "label", "scheme_answer", "student_answer", "justification", "awarded", "teacher"):
        setattr(row, name, sanitise(getattr(row, name)))
    return row


def _clean_page(page: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The rubric page with every string (criterion, band, descriptor, awarded band, ...) sanitised;
    numbers and None pass through."""
    def value(v: Any) -> Any:
        if isinstance(v, str):
            return sanitise(v)
        if isinstance(v, dict):
            return {k: value(x) for k, x in v.items()}
        if isinstance(v, list):
            return [value(x) for x in v]
        return v
    return [value(item) for item in page]


def _row_v1(mark: dict, criteria: List[dict]) -> RecordRow:
    scores = list(mark.get("criterion_scores") or [])
    teacher_scores = mark.get("teacher_scores")
    shown = list(teacher_scores) if teacher_scores is not None else scores
    summary = " · ".join(f"{c.get('id', '')} {int(s)}/{int(c.get('max_score', 0))}" for c, s in zip(criteria, shown))
    rationale = (mark.get("rationale") or "").strip()
    escalated = bool(mark.get("escalated"))
    teacher_total = int(sum(teacher_scores)) if teacher_scores is not None else None
    mx = int(mark.get("max") or sum(int(c.get("max_score", 0)) for c in criteria))
    if escalated and teacher_total is None:
        justification = reason_text(mark.get("reason"))
    else:
        justification = f"{rationale}\n{summary}".strip() if summary else rationale
    awarded, marks, to_review = _awarded(int(mark.get("total") or 0), mx, escalated, teacher_total)
    return _clean(RecordRow(
        key=mark.get("q_id") or "", label=q_label(mark.get("q_id") or ""),
        scheme_answer=" · ".join(f"{c.get('id', '')} {c.get('description', '')} ({int(c.get('max_score', 0))})".strip() for c in criteria),
        student_answer=student_answer(mark.get("evidence", ""), "", False),
        justification=justification, awarded=awarded, teacher="", to_review=to_review, awarded_marks=marks, max_marks=mx,
    ))


def build_record(submission_detail: dict, template: Optional[dict] = None, *, model: str = "") -> Record:
    """Build the record from the detail dict `get_submission` returns and the assignment dict
    `get_template` returns (None when the script has no assignment). `model` is the provider/model
    line for the header. Every text field is sanitised (control characters removed)."""
    d = submission_detail
    title = sanitise(d.get("assignment_title") or (template or {}).get("title") or (d.get("context") or "").strip()
                     or f"Script {d.get('id')}")
    # marked_at = the marking run's created_at (the detail's `marked_at`), not the latest job of any kind
    marked_at = d.get("marked_at") or d.get("created_at") or ""
    kind = d.get("scheme_kind") or "criteria"
    rubric_page = None
    if d.get("marks_version") == 2:
        parts = d.get("parts") or []
        rows = [_row_v2(kind, p) for p in parts]
        if kind == "rubric":
            rubric_page = _clean_page([
                {"criterion": p.get("q_id"), "bands": (p.get("scheme") or {}).get("bands") or [],
                 "awarded_band": (p.get("teacher") or {}).get("band") if p.get("teacher")
                 else (None if p.get("escalated") else (p.get("band") or None))}
                for p in parts])
    else:
        criteria = (d.get("rubric") or {}).get("criterion_defs") or []
        rows = [_row_v1(m, criteria) for m in d.get("marks") or []]
    totals = d.get("totals") or {}
    return Record(
        title=title, student=sanitise(d.get("label")), marked_at=sanitise(marked_at), model=sanitise(model), rows=rows,
        total_awarded=int(totals.get("total") or 0), total_upper=int(totals.get("total_upper") or 0),
        total_max=int(totals.get("total_max") or 0), to_review_count=sum(1 for r in rows if r.to_review),
        rubric_page=rubric_page, submission_id=int(d.get("id") or 0), kind=kind,
    )

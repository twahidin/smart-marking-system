"""Render records as markbook.xlsx: one markbook sheet per assignment (one row per student, one column
per part of that assignment; "Quick mark" for scripts with no assignment) and sheet Rows (every record
row flattened, with the student label and the assignment)."""
import io
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from sms.records.builder import Record, SEE_TRANSCRIPTION, truncate

REVIEW = "Review"
QUICK_MARK = "Quick mark"
ROW_HEADERS = ["Student", "Assignment", "Question & part", "Marking scheme answer", "Student's answer (extracted)",
               "Justification", "Awarded mark", "Teacher's mark"]
SHEET_NAME_MAX = 31
_SHEET_FORBIDDEN = re.compile(r"[\[\]:*?/\\']")


def sheet_name(title: str, used: Set[str]) -> str:
    """An Excel-safe, unique sheet name for an assignment title: forbidden characters become spaces, at
    most 31 characters, " (2)", " (3)" ... appended while another sheet already has the name."""
    base = " ".join(_SHEET_FORBIDDEN.sub(" ", title or "").split()) or "Sheet"
    name = base[:SHEET_NAME_MAX].rstrip()
    n = 2
    while name.lower() in used:
        suffix = f" ({n})"
        name = base[:SHEET_NAME_MAX - len(suffix)].rstrip() + suffix
        n += 1
    used.add(name.lower())
    return name


def _groups(records: List[Record]) -> List[Tuple[str, List[Record]]]:
    """Records grouped by assignment in first-seen order, each group titled by its assignment."""
    by_key: Dict[Optional[int], List[Record]] = {}
    for r in records:
        by_key.setdefault(r.assignment_id, []).append(r)
    return [(QUICK_MARK if key is None else group[0].title, group) for key, group in by_key.items()]


def _assignment_of(record: Record) -> str:
    return QUICK_MARK if record.assignment_id is None else record.title


def _student_answer(record: Record, row) -> str:
    """The Rows sheet has no transcription page, so a rubric row keeps the truncated transcription."""
    if record.transcription is not None and row.student_answer == SEE_TRANSCRIPTION:
        return truncate(record.transcription)
    return row.student_answer
HEADER_FILL = PatternFill("solid", fgColor="D9E2F3")
REVIEW_FILL = PatternFill("solid", fgColor="FFE8B3")


def _part_labels(records: List[Record]) -> List[str]:
    labels: List[str] = []
    for r in records:
        for row in r.rows:
            if row.label not in labels:
                labels.append(row.label)
    return labels


def _append_text_row(ws, values: list) -> None:
    """Append a row with every str stored as text, never as a formula: a transcription like "= 3.5" or
    a hostile "=cmd|..." must round-trip verbatim (no quote prefix), so the type is forced instead."""
    ws.append(values)
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


def _header(ws, headers: List[str]) -> None:
    _append_text_row(ws, headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
    ws.freeze_panes = "B2"


def _markbook(ws, records: List[Record]) -> None:
    labels = _part_labels(records)
    _header(ws, ["Student"] + labels + ["Total", "Max"])
    for r in records:
        by_label = {row.label: row for row in r.rows}
        cells = [r.student]
        for label in labels:
            row = by_label.get(label)
            cells.append(None if row is None else (REVIEW if row.to_review else row.awarded_marks))
        total = r.total_awarded if r.total_upper == r.total_awarded else r.total_text
        cells += [total, r.total_max]
        _append_text_row(ws, cells)
        for cell in ws[ws.max_row]:
            if cell.value == REVIEW:
                cell.fill = REVIEW_FILL
    for i in range(1, len(labels) + 4):
        ws.column_dimensions[get_column_letter(i)].width = 22 if i == 1 else 10


def render_xlsx(records: Iterable[Record]) -> bytes:
    records = list(records)
    wb = Workbook()
    used: Set[str] = {"rows"}
    first = True
    for title, group in _groups(records) or [(QUICK_MARK, [])]:
        ws = wb.active if first else wb.create_sheet()
        ws.title = sheet_name(title, used)
        first = False
        _markbook(ws, group)

    rs = wb.create_sheet("Rows")
    _header(rs, ROW_HEADERS)
    for r in records:
        for row in r.rows:
            _append_text_row(rs, [r.student, _assignment_of(r), row.label, row.scheme_answer, _student_answer(r, row),
                                  row.justification, row.awarded, row.teacher or None])
            if row.to_review:
                rs.cell(row=rs.max_row, column=7).fill = REVIEW_FILL
    for i, width in enumerate([22, 24, 14, 40, 40, 40, 16, 14], start=1):
        rs.column_dimensions[get_column_letter(i)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

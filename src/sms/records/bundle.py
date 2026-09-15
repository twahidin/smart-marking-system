"""Bundle records as a .zip: one <label>-marking-record.docx per student plus markbook.xlsx."""
import io
import re
import unicodedata
import zipfile
from typing import Iterable, List, Optional, Set

from sms.records.builder import Record
from sms.records.docx import render_docx
from sms.records.xlsx import render_xlsx

MARKBOOK = "markbook.xlsx"
SUFFIX = "-marking-record.docx"


def slugify(label: str, submission_id: Optional[int] = None) -> str:
    """ASCII slug of a label; a label with no ASCII letters or digits (e.g. 陈伟) becomes
    "script-<submission id>" so different students never share a filename."""
    text = unicodedata.normalize("NFKD", label or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if text:
        return text
    return f"script-{submission_id}" if submission_id is not None else "script"


def record_filename(label: str, submission_id: Optional[int] = None) -> str:
    return slugify(label, submission_id) + SUFFIX


def bundle_zip(records: Iterable[Record]) -> bytes:
    records: List[Record] = list(records)
    buf = io.BytesIO()
    used: Set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in records:
            name = record_filename(r.student, r.submission_id)
            if name in used:  # two scripts with the same label: the submission id keeps them apart
                name = f"{slugify(r.student, r.submission_id)}-{r.submission_id}{SUFFIX}"
            used.add(name)
            z.writestr(name, render_docx(r))
        z.writestr(MARKBOOK, render_xlsx(records))
    return buf.getvalue()

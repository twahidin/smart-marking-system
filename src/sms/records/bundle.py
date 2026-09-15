"""Bundle records as a .zip: one <label>-marking-record.docx per student plus markbook.xlsx."""
import io
import re
import unicodedata
import zipfile
from typing import Iterable, List, Set

from sms.records.builder import Record
from sms.records.docx import render_docx
from sms.records.xlsx import render_xlsx

MARKBOOK = "markbook.xlsx"
SUFFIX = "-marking-record.docx"


def slugify(label: str) -> str:
    text = unicodedata.normalize("NFKD", label or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "script"


def record_filename(label: str) -> str:
    return slugify(label) + SUFFIX


def bundle_zip(records: Iterable[Record]) -> bytes:
    records: List[Record] = list(records)
    buf = io.BytesIO()
    used: Set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in records:
            name = record_filename(r.student)
            if name in used:  # two scripts with the same label: the submission id keeps them apart
                name = f"{slugify(r.student)}-{r.submission_id}{SUFFIX}"
            used.add(name)
            z.writestr(name, render_docx(r))
        z.writestr(MARKBOOK, render_xlsx(records))
    return buf.getvalue()

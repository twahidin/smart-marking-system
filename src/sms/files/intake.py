"""Sorting an upload into pages and program files before anything is stored.

A submission may now be photos/PDFs (pages), Python/Scratch/Excel files, or both. This module is
the only place that decides which is which: it splits the upload, expands a `.zip` one level (the
usual shape of "my whole folder"), drops the junk a Mac or Windows zip carries, and enforces the
limits. The renderers in `sms.files.render` are deliberately cap-free — every cap lives here, so
nothing oversized ever reaches storage or a model.
"""
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from sms.files.render import KIND_BY_EXT
from sms.storage import IMAGE_EXTS, PDF_EXTS

MAX_FILES = 12
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ZIP_DECOMPRESSED = 20 * 1024 * 1024
PAGE_EXTS = set(IMAGE_EXTS) | set(PDF_EXTS)
FILE_EXTS = set(KIND_BY_EXT)
BAD_FILE_MESSAGE = "unsupported file type (use PDF, JPG, PNG, HEIC, .py, .sb3, .xlsx or a .zip of those)"


class IntakeError(ValueError):
    """A rejected upload: `code` is the API error code, `name` the file that caused it."""

    def __init__(self, code: str, name: str, message: str):
        super().__init__(message)
        self.code = code
        self.name = name
        self.message = message


@dataclass
class Intake:
    pages: List[Tuple[str, bytes]] = field(default_factory=list)
    files: List[Tuple[str, bytes]] = field(default_factory=list)
    ignored: List[str] = field(default_factory=list)


def _junk(name: str) -> bool:
    """Zip entries no student meant to hand in: directories, `__MACOSX` forks, dotfiles."""
    parts = Path(name).parts
    return name.endswith("/") or any(p.startswith("__MACOSX") or p.startswith(".") for p in parts)


def _add_file(name: str, data: bytes, into: Intake, max_files: int, max_file_bytes: int) -> None:
    if len(data) > max_file_bytes:
        raise IntakeError("too_large", name, f"{name} is over {max_file_bytes // (1024 * 1024)} MB")
    if len(into.files) >= max_files:
        raise IntakeError("too_many_files", name, f"too many files; the limit is {max_files} per submission")
    into.files.append((name, data))


def _expand_zip(name: str, data: bytes, into: Intake, max_files: int, max_file_bytes: int) -> None:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise IntakeError("bad_file", name, f"{name} is not a zip file")
    with z:
        # Trust the central directory only for the cheap bomb check; the per-entry size cap in
        # _add_file still measures the bytes actually read, so a lying header cannot get past it.
        if sum(i.file_size for i in z.infolist()) > MAX_ZIP_DECOMPRESSED:
            raise IntakeError("zip_bomb", name, f"{name} expands past {MAX_ZIP_DECOMPRESSED // (1024 * 1024)} MB")
        usable = 0
        for info in z.infolist():
            if info.is_dir() or _junk(info.filename):
                continue
            # Folders inside the zip are flattened: only the leaf name is kept.
            inner = Path(info.filename).name
            ext = Path(inner).suffix.lower()
            if ext in PAGE_EXTS:
                into.pages.append((inner, z.read(info)))
                usable += 1
            elif ext in FILE_EXTS:
                _add_file(inner, z.read(info), into, max_files, max_file_bytes)
                usable += 1
            else:
                into.ignored.append(inner)
        if usable == 0:
            raise IntakeError("zip_nothing_usable", name, f"{name} contains no pages or program files")


def classify_uploads(files: List[Tuple[str, bytes]], *, max_files: int = MAX_FILES,
                     max_file_bytes: int = MAX_FILE_BYTES) -> Intake:
    """Split an upload into pages (images/PDFs) and program files, expanding zips. Order is kept."""
    it = Intake()
    for name, data in files:
        ext = Path(name).suffix.lower()
        if ext == ".zip":
            _expand_zip(name, data, it, max_files, max_file_bytes)
        elif ext in PAGE_EXTS:
            it.pages.append((name, data))
        elif ext in FILE_EXTS:
            _add_file(name, data, it, max_files, max_file_bytes)
        else:
            raise IntakeError("bad_file", name, f"{name}: {BAD_FILE_MESSAGE}")
    return it


def input_kind(it: Intake) -> str:
    """`pages`, `files` or `mixed` — what `submissions.input_kind` records. An empty upload reads
    as `pages`; the caller rejects it before it gets that far."""
    if it.files and it.pages:
        return "mixed"
    return "files" if it.files else "pages"

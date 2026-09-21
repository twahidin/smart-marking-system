"""Sorting an upload into pages and program files before anything is stored.

A submission may now be photos/PDFs (pages), Python/Scratch/Excel files, or both. This module is
the only place that decides which is which: it splits the upload, expands a `.zip` one level (the
usual shape of "my whole folder"), drops the junk a Mac or Windows zip carries, and enforces the
limits. The renderers in `sms.files.render` are deliberately cap-free — every cap lives here, so
nothing oversized ever reaches storage or a model.

Four caps, all checked before a byte is written: 12 program files per submission, 2 MB per program
file, 20 MB decompressed per zip, and `MAX_UPLOAD_BYTES` (50 MB) over the whole upload once
unpacked — the last one because everything extracted from a zip is held in memory until
`process_uploads` runs, and a handful of individually legal zips could otherwise add up to far more
than the 50 MB body cap let through. Pages are deliberately not subject to the 2 MB per-file cap,
zipped or loose: a phone scan or a PDF is routinely bigger, and `process_uploads` applies the page
limits that do belong to them.
"""
import io
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import List, Set, Tuple

from sms.files.render import KIND_BY_EXT
from sms.storage import IMAGE_EXTS, MAX_UPLOAD_BYTES, PDF_EXTS

MAX_FILES = 12
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ZIP_DECOMPRESSED = 20 * 1024 * 1024
PAGE_EXTS = set(IMAGE_EXTS) | set(PDF_EXTS)
FILE_EXTS = set(KIND_BY_EXT)
BAD_FILE_MESSAGE = "unsupported file type (use PDF, JPG, PNG, HEIC, .py, .sb3, .xlsx or a .zip of those)"
UNPACK_FAILED = "could not be unpacked (password-protected or damaged zip)"


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
    total_bytes: int = 0


# --- names -------------------------------------------------------------------------------------

def _norm(name: str) -> str:
    """A zip written on Windows stores `folder\\file.py`; fold the separators so the rest of this
    module can treat every entry name as a POSIX path."""
    return name.replace("\\", "/")


def _basename(name: str) -> str:
    """The leaf name: folders inside a zip (and any path a browser sends) are flattened away."""
    return PurePosixPath(_norm(name)).name


def _junk(name: str) -> bool:
    """Zip entries no student meant to hand in: directories, `__MACOSX` forks, dotfiles.
    This is tidying, NOT the path-traversal guard — `_traversal` is, and it runs first."""
    parts = PurePosixPath(_norm(name)).parts
    return name.endswith("/") or any(p.startswith("__MACOSX") or p.startswith(".") for p in parts)


def _traversal(name: str) -> bool:
    """An entry that tries to escape the archive: absolute, or with a `..` path segment. We only
    ever keep the basename and store by content hash, so this cannot reach the filesystem — it is
    refused anyway, and listed, so a zip built to escape is visible rather than silently tidied."""
    norm = _norm(name)
    return norm.startswith("/") or ".." in PurePosixPath(norm).parts


def _unique(name: str, into: "Intake") -> str:
    """`prog.py` from two folders of the same zip would collide on the submission, so the second
    becomes `prog (2).py`, the third `prog (3).py`."""
    taken: Set[str] = {n for n, _ in into.pages} | {n for n, _ in into.files}
    if name not in taken:
        return name
    p = PurePosixPath(name)
    stem, suffix = p.stem, p.suffix
    i = 2
    while f"{stem} ({i}){suffix}" in taken:
        i += 1
    return f"{stem} ({i}){suffix}"


# --- limits ------------------------------------------------------------------------------------

def _charge(name: str, size: int, into: Intake, max_total_bytes: int) -> None:
    """Add an entry's bytes to the running total for the whole upload and stop at the budget.

    The message says "that upload", not the entry's name: the entry that tipped the total over is
    rarely the one to remove, and the two `too_large` cases (this one and a single program file over
    2 MB in `_add_file`) must read differently — the student route shows the intake message as-is."""
    into.total_bytes += size
    if into.total_bytes > max_total_bytes:
        raise IntakeError("too_large", name, f"That upload is over {max_total_bytes // (1024 * 1024)} MB in total")


def _add_page(name: str, data: bytes, into: Intake, max_total_bytes: int) -> None:
    """A page — zipped or loose, the same rules either way. The 2 MB per-entry cap is for program
    files only: a phone scan or a PDF is routinely bigger than that and must not be refused for it.
    Pages are bounded by the per-archive 20 MB decompressed cap, the running total here, and
    `process_uploads`' page-count and 50 MB limits afterwards."""
    _charge(name, len(data), into, max_total_bytes)
    into.pages.append((_unique(name, into), data))


def _add_file(name: str, data: bytes, into: Intake, max_files: int, max_file_bytes: int,
              max_total_bytes: int) -> None:
    # Count first: an oversized 13th file is "too many files", which is the thing to fix.
    if len(into.files) >= max_files:
        raise IntakeError("too_many_files", name, f"{name}: too many files — the limit is {max_files} per submission")
    if len(data) > max_file_bytes:
        raise IntakeError("too_large", name, f"{name} is over {max_file_bytes // (1024 * 1024)} MB")
    _charge(name, len(data), into, max_total_bytes)
    into.files.append((_unique(name, into), data))


# --- zips --------------------------------------------------------------------------------------

def _read_entry(z: zipfile.ZipFile, zip_name: str, info: zipfile.ZipInfo) -> bytes:
    """One entry's bytes. An encrypted entry raises RuntimeError, an unsupported compression
    method NotImplementedError, a damaged stream EOFError / BadZipFile / zlib.error — all of them
    are a bad upload to tell the teacher about, never a 500."""
    try:
        return z.read(info)
    except (RuntimeError, NotImplementedError, zipfile.BadZipFile, EOFError, zlib.error) as e:
        raise IntakeError("bad_file", zip_name, f"{zip_name}: {UNPACK_FAILED}") from e


def _expand_zip(name: str, data: bytes, into: Intake, max_files: int, max_file_bytes: int,
                max_total_bytes: int, max_zip_bytes: int) -> None:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise IntakeError("bad_file", name, f"{name} is not a zip file")
    with z:
        # Trust the central directory only for the cheap bomb check; the per-entry size cap and the
        # running total below measure the bytes actually read, so a lying header gains nothing.
        if sum(i.file_size for i in z.infolist()) > max_zip_bytes:
            raise IntakeError("zip_bomb", name, f"{name} expands past {max_zip_bytes // (1024 * 1024)} MB")
        usable = 0
        for info in z.infolist():
            if info.is_dir():
                continue
            if _traversal(info.filename):
                into.ignored.append(info.filename)
                continue
            if _junk(info.filename):
                continue
            inner = _basename(info.filename)
            ext = PurePosixPath(inner).suffix.lower()
            if ext not in PAGE_EXTS and ext not in FILE_EXTS:
                into.ignored.append(inner)
                continue
            entry = _read_entry(z, name, info)
            if ext in PAGE_EXTS:
                _add_page(inner, entry, into, max_total_bytes)
            else:
                _add_file(inner, entry, into, max_files, max_file_bytes, max_total_bytes)
            usable += 1
        if usable == 0:
            raise IntakeError("zip_nothing_usable", name, f"{name} contains no pages or program files")


# --- entry point -------------------------------------------------------------------------------

def classify_uploads(files: List[Tuple[str, bytes]], *, max_files: int = MAX_FILES,
                     max_file_bytes: int = MAX_FILE_BYTES,
                     max_total_bytes: int = MAX_UPLOAD_BYTES,
                     max_zip_bytes: int = MAX_ZIP_DECOMPRESSED) -> Intake:
    """Split an upload into pages (images/PDFs) and program files, expanding zips. Order is kept.

    `max_zip_bytes` is the per-archive decompressed cap. It defaults to the 20 MB one submission's
    zip gets; the bulk class upload raises it, because one zip legitimately carries a whole class's
    photos (see `class_assignments._validate_bulk_zip`)."""
    it = Intake()
    for raw_name, data in files:
        name = _basename(raw_name) or raw_name
        ext = PurePosixPath(name).suffix.lower()
        if ext == ".zip":
            _charge(name, len(data), it, max_total_bytes)
            _expand_zip(name, data, it, max_files, max_file_bytes, max_total_bytes, max_zip_bytes)
        elif ext in PAGE_EXTS:
            _add_page(name, data, it, max_total_bytes)
        elif ext in FILE_EXTS:
            _add_file(name, data, it, max_files, max_file_bytes, max_total_bytes)
        else:
            raise IntakeError("bad_file", name, f"{name}: {BAD_FILE_MESSAGE}")
    return it


def input_kind(it: Intake) -> str:
    """`pages`, `files` or `mixed` — what `submissions.input_kind` records. An empty upload reads
    as `pages`; the caller rejects it before it gets that far."""
    if it.files and it.pages:
        return "mixed"
    return "files" if it.files else "pages"

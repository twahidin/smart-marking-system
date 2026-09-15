import json
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.schemas.marking import Rubric
from sms.storage import PageStorage, UploadError, process_uploads
from sms.timeutil import iso_utc
from sms.web.errors import ApiError
from sms.web.services.rubric import parse_rubric

SCHEME_KINDS = ("criteria", "mark_scheme", "rubric")


# --- shapes of questions_json / scheme_json ---------------------------------------------------

class Question(BaseModel):
    q_id: str = Field(min_length=1)
    text: str = ""
    max_marks: int = Field(ge=0)


class MarkPoint(BaseModel):
    label: str
    marks: int = Field(ge=0)


class MarkSchemeEntry(BaseModel):
    q_id: str = Field(min_length=1)
    answer: str = ""
    marks: List[MarkPoint] = Field(default_factory=list)
    notes: str = ""


class Band(BaseModel):
    band: str
    marks: int = Field(ge=0)
    descriptor: str = ""


class RubricCriterionBands(BaseModel):
    criterion: str = Field(min_length=1)
    bands: List[Band] = Field(default_factory=list)


class _Questions(BaseModel):
    items: List[Question]


class _MarkScheme(BaseModel):
    items: List[MarkSchemeEntry]


class _RubricScheme(BaseModel):
    items: List[RubricCriterionBands]


def _first_msg(e: ValidationError) -> str:
    err = e.errors()[0]
    loc = ".".join(str(p) for p in err["loc"] if p != "items")
    return f"{loc}: {err['msg']}" if loc else err["msg"]


def _validate_questions(questions: Any) -> List[dict]:
    if questions is None:
        return []
    if not isinstance(questions, list):
        raise ApiError(400, "bad_questions", "questions must be a list of {q_id, text, max_marks}")
    try:
        return [q.model_dump() for q in _Questions(items=questions).items]
    except ValidationError as e:
        raise ApiError(400, "bad_questions", f"questions: {_first_msg(e)}")


def _validate_scheme(scheme_kind: str, scheme: Any) -> List[dict]:
    if scheme_kind not in SCHEME_KINDS:
        raise ApiError(400, "bad_scheme_kind", "scheme_kind must be criteria, mark_scheme or rubric")
    if scheme is None or scheme == []:
        return []
    if scheme_kind == "criteria":
        raise ApiError(400, "bad_scheme", "A criteria template has no per-question scheme — use mark_scheme or rubric")
    if not isinstance(scheme, list):
        raise ApiError(400, "bad_scheme", "scheme must be a list")
    model = _MarkScheme if scheme_kind == "mark_scheme" else _RubricScheme
    try:
        return [s.model_dump() for s in model(items=scheme).items]
    except ValidationError as e:
        raise ApiError(400, "bad_scheme", f"scheme ({scheme_kind}): {_first_msg(e)}")


def _validate_paper_page_ids(ids: Any) -> List[int]:
    if ids is None:
        return []
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ApiError(400, "bad_paper", "paper_page_ids must be a list of page ids")
    return list(ids)


def _validate(title: str, subject: str, context: str, rubric_json: str, scheme_kind: str, questions: Any,
              scheme: Any, paper_page_ids: Any) -> Dict[str, Any]:
    title = title.strip()
    if not title:
        raise ApiError(400, "bad_title", "Give the assignment a title")
    try:
        subject = SubjectRouter().resolve(subject)
    except KeyError:
        raise ApiError(400, "bad_subject", "Subject must be math, language or science")
    rubric = parse_rubric(rubric_json)
    qs = _validate_questions(questions)
    sc = _validate_scheme(scheme_kind, scheme)
    pages = _validate_paper_page_ids(paper_page_ids)
    return {
        "title": title, "subject": subject, "context": context.strip(), "rubric": rubric.model_dump_json(),
        "scheme_kind": scheme_kind, "questions": json.dumps(qs) if qs else None,
        "scheme": json.dumps(sc) if sc else None, "paper": json.dumps(pages) if pages else None,
    }


def _row_to_dict(r: dict) -> Dict[str, Any]:
    rubric = Rubric.model_validate_json(r["rubric_json"])
    return {
        "id": r["id"], "title": r["title"], "subject": r["subject"], "context": r["context"],
        "rubric": rubric.model_dump(),
        "criteria_count": len(rubric.criterion_defs),
        "total_marks": sum(c.max_score for c in rubric.criterion_defs),
        "scheme_kind": r["scheme_kind"],
        "questions": json.loads(r["questions_json"]) if r["questions_json"] else [],
        "scheme": json.loads(r["scheme_json"]) if r["scheme_json"] else [],
        "paper_page_ids": json.loads(r["paper_page_ids_json"]) if r["paper_page_ids_json"] else [],
        "times_used": int(r["times_used"]),
        "created_at": iso_utc(r["created_at"]), "updated_at": iso_utc(r["updated_at"]),
    }


_INSERT = ("INSERT INTO assignment_templates (title, subject, context, rubric_json, scheme_kind, questions_json, "
           "scheme_json, paper_page_ids_json) VALUES (:title, :subject, :context, :rubric, :scheme_kind, :questions, "
           ":scheme, :paper) RETURNING id")


def list_templates(db: Database) -> List[Dict[str, Any]]:
    rows = db.query("SELECT * FROM assignment_templates ORDER BY times_used DESC, updated_at DESC, id DESC")
    return [_row_to_dict(r) for r in rows]


def get_template(db: Database, template_id: int) -> Optional[Dict[str, Any]]:
    rows = db.query("SELECT * FROM assignment_templates WHERE id = :id", {"id": template_id})
    return _row_to_dict(rows[0]) if rows else None


def create_template(db: Database, *, title: str, subject: str, context: str, rubric_json: str,
                    scheme_kind: str = "criteria", questions: Any = None, scheme: Any = None,
                    paper_page_ids: Any = None) -> Dict[str, Any]:
    fields = _validate(title, subject, context, rubric_json, scheme_kind, questions, scheme, paper_page_ids)
    tid = db.insert(_INSERT, fields)
    return get_template(db, tid)  # type: ignore[return-value]


def update_template(db: Database, template_id: int, *, title: str, subject: str, context: str, rubric_json: str,
                    scheme_kind: str = "criteria", questions: Any = None, scheme: Any = None,
                    paper_page_ids: Any = None) -> Dict[str, Any]:
    if get_template(db, template_id) is None:
        raise ApiError(404, "not_found", "No such assignment")
    fields = _validate(title, subject, context, rubric_json, scheme_kind, questions, scheme, paper_page_ids)
    fields["id"] = template_id
    db.execute(
        "UPDATE assignment_templates SET title = :title, subject = :subject, context = :context, "
        "rubric_json = :rubric, scheme_kind = :scheme_kind, questions_json = :questions, scheme_json = :scheme, "
        "paper_page_ids_json = :paper, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
        fields,
    )
    return get_template(db, template_id)  # type: ignore[return-value]


def delete_template(db: Database, template_id: int) -> None:
    with db.transaction() as tx:
        if tx.execute("DELETE FROM assignment_templates WHERE id = :id", {"id": template_id}) == 0:
            raise ApiError(404, "not_found", "No such assignment")
        tx.execute("DELETE FROM pages WHERE template_id = :id", {"id": template_id})


def mark_template_used(db: Database, template_id: int) -> None:
    db.execute("UPDATE assignment_templates SET times_used = times_used + 1, updated_at = CURRENT_TIMESTAMP "
               "WHERE id = :id", {"id": template_id})


def attach_paper(db: Database, storage: PageStorage, template_id: int,
                 files: List[Tuple[str, bytes]]) -> List[Dict[str, Any]]:
    """Store the uploaded question paper as pages owned by the template, replacing any previous
    paper. Page image files are content-addressed and shared, so only the rows are replaced."""
    if get_template(db, template_id) is None:
        raise ApiError(404, "not_found", "No such assignment")
    if not files:
        raise ApiError(400, "no_files", "Add at least one page")
    try:
        pages = process_uploads(files, storage)
    except UploadError as e:
        raise ApiError(400, "bad_upload", str(e))
    with db.transaction() as tx:
        tx.execute("DELETE FROM pages WHERE template_id = :t", {"t": template_id})
        page_rows = []
        for i, p in enumerate(pages):
            pid = tx.insert(
                "INSERT INTO pages (template_id, page_index, sha256, storage_path, source_filename, width, height) "
                "VALUES (:t, :i, :h, :p, :f, :w, :ht) RETURNING id",
                {"t": template_id, "i": i, "h": p.sha256, "p": p.storage_path, "f": p.source_filename,
                 "w": p.width, "ht": p.height},
            )
            page_rows.append({"id": pid, "page_index": i, "width": p.width, "height": p.height})
        tx.execute("UPDATE assignment_templates SET paper_page_ids_json = :ids, updated_at = CURRENT_TIMESTAMP "
                   "WHERE id = :t", {"ids": json.dumps([r["id"] for r in page_rows]), "t": template_id})
    return page_rows


_EXPORT_FIELDS = ("title", "subject", "context", "rubric", "scheme_kind", "questions", "scheme")


def export_templates(db: Database) -> Dict[str, Any]:
    return {"version": 1, "assignments": [{k: t[k] for k in _EXPORT_FIELDS} for t in list_templates(db)]}


def import_templates(db: Database, payload: Any) -> int:
    """Create every assignment in an export payload that is not already present (same title and
    subject). Everything is validated before anything is written, so a bad entry imports nothing.
    Paper pages are not part of an export."""
    if not isinstance(payload, dict) or not isinstance(payload.get("assignments"), list):
        raise ApiError(400, "bad_import", 'Expected {"version": 1, "assignments": [...]}')
    validated = []
    for i, item in enumerate(payload["assignments"]):
        if not isinstance(item, dict) or not all(k in item for k in ("title", "subject", "rubric")):
            raise ApiError(400, "bad_import", f"Assignment {i + 1} needs title, subject and rubric")
        if not isinstance(item["rubric"], dict):
            raise ApiError(400, "bad_rubric", f"Assignment {i + 1}: rubric must be an object")
        validated.append(_validate(str(item["title"]), str(item["subject"]), str(item.get("context") or ""),
                                   json.dumps(item["rubric"]), str(item.get("scheme_kind") or "criteria"),
                                   item.get("questions"), item.get("scheme"), None))
    existing = {(t["title"], t["subject"]) for t in list_templates(db)}
    created = 0
    with db.transaction() as tx:
        for fields in validated:
            key = (fields["title"], fields["subject"])
            if key in existing:
                continue
            tx.insert(_INSERT, fields)
            existing.add(key)
            created += 1
    return created

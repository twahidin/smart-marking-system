import json
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ValidationError

from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.providers.registry import DEFAULT_PROVIDER, get_provider
from sms.providers.settings import SettingsStore
from sms.schemas.marking import Rubric
# Canonical models live in sms.schemas.scheme; re-exported here for existing importers.
from sms.schemas.scheme import Band, MarkPoint, MarkSchemeEntry, Question, RubricCriterionBands  # noqa: F401
from sms.storage import PageStorage, UploadError, process_uploads
from sms.timeutil import iso_utc
from sms.web.errors import ApiError
from sms.web.services.rubric import parse_rubric
from sms.worker.extract_jobs import PAPER_KIND, SCHEME_KIND, dedupe_key
from sms.worker.jobs import JobStore

SCHEME_KINDS = ("criteria", "mark_scheme", "rubric")


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


def _validate(title: str, subject: str, context: str, rubric_json: str, scheme_kind: str, questions: Any,
              scheme: Any, delete_pages_after_marking: Optional[bool] = None, provider: Optional[str] = None,
              model: Optional[str] = None, extractor_model: Optional[str] = None,
              language: Optional[str] = None, *,
              db: Optional[Database] = None) -> Dict[str, Any]:
    title = title.strip()
    if not title:
        raise ApiError(400, "bad_title", "Give the assignment a title")
    try:
        subject = SubjectRouter().resolve(subject)
    except KeyError:
        raise ApiError(400, "bad_subject", "Subject must be math, language, science, mt or computing")
    if subject == "mt":
        language = (language or "").strip() or None
        if language not in ("zh", "ms", "ta"):
            raise ApiError(400, "bad_language", "Choose the Mother Tongue language (zh, ms or ta)")
    else:
        language = None
    rubric = parse_rubric(rubric_json)
    qs = _validate_questions(questions)
    sc = _validate_scheme(scheme_kind, scheme)
    # A blank provider means Auto: the assignment follows whatever Settings says, so its model and
    # extractor model go with it. A chosen one must be known and already have a key saved.
    provider = (provider or "").strip() or None
    if provider:
        try:
            spec = get_provider(provider)
        except KeyError:
            raise ApiError(400, "bad_provider", f"Unknown provider {provider!r}")
        if db is not None and SettingsStore.has_key_for(db, provider) is False:
            raise ApiError(400, "no_key_for_provider", f"Save a {spec.label} key under Settings before choosing it here")
        model = (model or "").strip() or spec.default_model
        extractor_model = (extractor_model or "").strip() or None
    else:
        model = extractor_model = None
    return {
        "title": title, "subject": subject, "context": context.strip(), "rubric": rubric.model_dump_json(),
        "scheme_kind": scheme_kind, "questions": json.dumps(qs) if qs else None,
        "scheme": json.dumps(sc) if sc else None,
        "delete_pages": None if delete_pages_after_marking is None else bool(delete_pages_after_marking),
        "provider": provider, "model": model, "extractor_model": extractor_model, "language": language,
    }


def _global_model(db: Database) -> Dict[str, Optional[str]]:
    """The Settings provider/model an assignment falls back to when it does not pick its own."""
    rows = db.query("SELECT provider, model, extractor_model FROM settings WHERE id = 1")
    if not rows:
        spec = get_provider(DEFAULT_PROVIDER)
        return {"provider": spec.id, "model": spec.default_model, "extractor_model": None}
    r = rows[0]
    return {"provider": r["provider"], "model": r["model"], "extractor_model": r["extractor_model"] or None}


def _effective_models_by_subject(db: Database) -> Dict[str, Dict[str, Any]]:
    """Per known subject, the model a template in it falls back to when it does not pin one of its
    own: that subject's saved default when one is saved and its provider still has a key, else the
    global Settings model. Computed once per listing — there are only a handful of subjects."""
    settings_default = {**_global_model(db), "source": "settings"}
    out: Dict[str, Dict[str, Any]] = {s: settings_default for s in SubjectRouter.KNOWN_SUBJECTS}
    for r in db.query("SELECT subject, provider, model, extractor_model FROM subject_models"):
        if r["subject"] in out and SettingsStore.has_key_for(db, r["provider"]):
            out[r["subject"]] = {"provider": r["provider"], "model": r["model"],
                                 "extractor_model": r["extractor_model"] or None, "source": "subject"}
    return out


def global_delete_pages_default(db: Database) -> bool:
    """The Settings default for deleting a script's pages once it is done (True until saved otherwise)."""
    rows = db.query("SELECT delete_pages_after_marking FROM settings WHERE id = 1")
    return bool(rows[0]["delete_pages_after_marking"]) if rows else True


TEMPLATE_PAGE_KINDS = ("paper", "scheme")


def _template_pages(db: Database, template_ids: List[int]) -> Dict[int, Dict[str, List[int]]]:
    """Page ids per template and kind ('paper' / 'scheme'), from the pages table — the source of
    truth for a template's question paper and mark scheme."""
    out: Dict[int, Dict[str, List[int]]] = {tid: {k: [] for k in TEMPLATE_PAGE_KINDS} for tid in template_ids}
    if not template_ids:
        return out
    placeholders = ", ".join(f":t{i}" for i in range(len(template_ids)))
    params = {f"t{i}": tid for i, tid in enumerate(template_ids)}
    for p in db.query(f"SELECT id, template_id, kind FROM pages WHERE template_id IN ({placeholders}) "
                      "ORDER BY template_id, page_index", params):
        if p["kind"] in TEMPLATE_PAGE_KINDS:
            out[p["template_id"]][p["kind"]].append(p["id"])
    return out


def _row_to_dict(r: dict, pages: Dict[str, List[int]], delete_default: bool,
                 effective_models: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    rubric = Rubric.model_validate_json(r["rubric_json"])
    flag = r["delete_pages_after_marking"]
    flag = None if flag is None else bool(flag)
    provider = r["provider"] or None
    effective = ({"provider": provider, "model": r["model"] or None, "extractor_model": r["extractor_model"] or None,
                  "source": "assignment"}
                 if provider else dict(effective_models[r["subject"]]))
    return {
        "id": r["id"], "title": r["title"], "subject": r["subject"], "context": r["context"],
        "language": r["language"],
        "rubric": rubric.model_dump(),
        "criteria_count": len(rubric.criterion_defs),
        "total_marks": sum(c.max_score for c in rubric.criterion_defs),
        "scheme_kind": r["scheme_kind"],
        "questions": json.loads(r["questions_json"]) if r["questions_json"] else [],
        "scheme": json.loads(r["scheme_json"]) if r["scheme_json"] else [],
        "paper_page_ids": pages["paper"],
        "scheme_page_ids": pages["scheme"],
        "delete_pages_after_marking": flag,
        "effective_delete_pages": delete_default if flag is None else flag,
        "provider": provider,
        "model": r["model"] or None,
        "extractor_model": r["extractor_model"] or None,
        "effective_model": effective,
        "times_used": int(r["times_used"]),
        "submission_count": int(r.get("submission_count") or 0),
        "pending_count": int(r.get("pending_count") or 0),
        "class_assignment_count": int(r.get("class_assignment_count") or 0),
        "created_at": iso_utc(r["created_at"]), "updated_at": iso_utc(r["updated_at"]),
    }


# Scripts uploaded against the template, how many of them have not been marked yet (those would fail
# with "assignment deleted" if the template went away), and the classes it is set in — see the delete guard.
_COUNTS = ("(SELECT COUNT(*) FROM submissions s WHERE s.assignment_id = t.id) AS submission_count, "
           "(SELECT COUNT(*) FROM submissions s WHERE s.assignment_id = t.id AND s.run_id IS NULL) AS pending_count, "
           "(SELECT COUNT(*) FROM class_assignments c WHERE c.template_id = t.id) AS class_assignment_count")

_INSERT = ("INSERT INTO assignment_templates (title, subject, context, rubric_json, scheme_kind, questions_json, "
           "scheme_json, delete_pages_after_marking, provider, model, extractor_model, language) VALUES (:title, :subject, "
           ":context, :rubric, :scheme_kind, :questions, :scheme, :delete_pages, :provider, :model, :extractor_model, :language) "
           "RETURNING id")


def list_templates(db: Database) -> List[Dict[str, Any]]:
    rows = db.query(f"SELECT t.*, {_COUNTS} FROM assignment_templates t ORDER BY times_used DESC, updated_at DESC, id DESC")
    pages = _template_pages(db, [r["id"] for r in rows])
    default = global_delete_pages_default(db)
    em = _effective_models_by_subject(db)
    return [_row_to_dict(r, pages[r["id"]], default, em) for r in rows]


def get_template(db: Database, template_id: int) -> Optional[Dict[str, Any]]:
    rows = db.query(f"SELECT t.*, {_COUNTS} FROM assignment_templates t WHERE t.id = :id", {"id": template_id})
    if not rows:
        return None
    return _row_to_dict(rows[0], _template_pages(db, [template_id])[template_id],
                        global_delete_pages_default(db), _effective_models_by_subject(db))


def create_template(db: Database, *, title: str, subject: str, context: str, rubric_json: str,
                    scheme_kind: str = "criteria", questions: Any = None, scheme: Any = None,
                    delete_pages_after_marking: Optional[bool] = None, provider: Optional[str] = None,
                    model: Optional[str] = None, extractor_model: Optional[str] = None,
                    language: Optional[str] = None) -> Dict[str, Any]:
    fields = _validate(title, subject, context, rubric_json, scheme_kind, questions, scheme, delete_pages_after_marking,
                       provider, model, extractor_model, language, db=db)
    tid = db.insert(_INSERT, fields)
    return get_template(db, tid)  # type: ignore[return-value]


def update_template(db: Database, template_id: int, *, title: str, subject: str, context: str, rubric_json: str,
                    scheme_kind: str = "criteria", questions: Any = None, scheme: Any = None,
                    delete_pages_after_marking: Optional[bool] = None, provider: Optional[str] = None,
                    model: Optional[str] = None, extractor_model: Optional[str] = None,
                    language: Optional[str] = None) -> Dict[str, Any]:
    """Update the template's fields. The paper (pages with this template_id) is owned by
    attach_paper and is never touched here."""
    if get_template(db, template_id) is None:
        raise ApiError(404, "not_found", "No such assignment")
    fields = _validate(title, subject, context, rubric_json, scheme_kind, questions, scheme, delete_pages_after_marking,
                       provider, model, extractor_model, language, db=db)
    fields["id"] = template_id
    db.execute(
        "UPDATE assignment_templates SET title = :title, subject = :subject, context = :context, "
        "rubric_json = :rubric, scheme_kind = :scheme_kind, questions_json = :questions, scheme_json = :scheme, "
        "delete_pages_after_marking = :delete_pages, provider = :provider, model = :model, "
        "extractor_model = :extractor_model, language = :language, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
        fields,
    )
    return get_template(db, template_id)  # type: ignore[return-value]


def duplicate_template(db: Database, template_id: int) -> Dict[str, Any]:
    """Copy a template as "<title> (copy)", including its paper: page rows are re-created for
    the new template pointing at the same content-addressed image files."""
    src = db.query("SELECT * FROM assignment_templates WHERE id = :id", {"id": template_id})
    if not src:
        raise ApiError(404, "not_found", "No such assignment")
    r = src[0]
    with db.transaction() as tx:
        new_id = tx.insert(_INSERT, {
            "title": f"{r['title']} (copy)", "subject": r["subject"], "context": r["context"], "rubric": r["rubric_json"],
            "scheme_kind": r["scheme_kind"], "questions": r["questions_json"], "scheme": r["scheme_json"],
            "delete_pages": r["delete_pages_after_marking"], "provider": r["provider"], "model": r["model"],
            "extractor_model": r["extractor_model"], "language": r["language"],
        })
        tx.execute(
            "INSERT INTO pages (template_id, kind, page_index, sha256, storage_path, source_filename, width, height) "
            "SELECT :new_id, kind, page_index, sha256, storage_path, source_filename, width, height FROM pages "
            "WHERE template_id = :src ORDER BY kind, page_index",
            {"new_id": new_id, "src": template_id},
        )
    return get_template(db, new_id)  # type: ignore[return-value]


def delete_template(db: Database, template_id: int, *, force: bool = False) -> None:
    """Delete a template. Refused (409 `in_use`) while scripts reference it or a class has it set, unless
    `force` — marked scripts keep their marks and records (the run stores its own scheme snapshot), but
    unmarked ones will fail with "assignment deleted" and have to be uploaded again, and the class
    assignments stay with `template_deleted` so later hand-ins are refused."""
    with db.transaction() as tx:
        t = get_template(tx, template_id)
        if t is None:
            raise ApiError(404, "not_found", "No such assignment")
        if (t["submission_count"] or t["class_assignment_count"]) and not force:
            n, pending, classes = t["submission_count"], t["pending_count"], t["class_assignment_count"]
            parts = []
            if n:
                msg = f"{n} script{'s' if n != 1 else ''} reference this assignment"
                if pending:
                    msg += f" and {pending} of them {'have' if pending != 1 else 'has'} not been marked yet"
                parts.append(msg)
            if classes:
                parts.append(f"set in {classes} class{'es' if classes != 1 else ''}")
            raise ApiError(409, "in_use", " and ".join(parts) + " — delete anyway to remove it from the bank")
        tx.execute("DELETE FROM assignment_templates WHERE id = :id", {"id": template_id})
        tx.execute("DELETE FROM pages WHERE template_id = :id", {"id": template_id})


def mark_template_used(db: Database, template_id: int) -> None:
    db.execute("UPDATE assignment_templates SET times_used = times_used + 1, updated_at = CURRENT_TIMESTAMP "
               "WHERE id = :id", {"id": template_id})


def _attach_pages(db: Database, storage: PageStorage, template_id: int, kind: str,
                  files: List[Tuple[str, bytes]]) -> List[Dict[str, Any]]:
    if get_template(db, template_id) is None:
        raise ApiError(404, "not_found", "No such assignment")
    if not files:
        raise ApiError(400, "no_files", "Add at least one page")
    try:
        pages = process_uploads(files, storage)
    except UploadError as e:
        raise ApiError(400, "bad_upload", str(e))
    with db.transaction() as tx:
        tx.execute("DELETE FROM pages WHERE template_id = :t AND kind = :k", {"t": template_id, "k": kind})
        page_rows = []
        for i, p in enumerate(pages):
            pid = tx.insert(
                "INSERT INTO pages (template_id, kind, page_index, sha256, storage_path, source_filename, width, height) "
                "VALUES (:t, :k, :i, :h, :p, :f, :w, :ht) RETURNING id",
                {"t": template_id, "k": kind, "i": i, "h": p.sha256, "p": p.storage_path, "f": p.source_filename,
                 "w": p.width, "ht": p.height},
            )
            page_rows.append({"id": pid, "page_index": i, "width": p.width, "height": p.height})
        tx.execute("UPDATE assignment_templates SET updated_at = CURRENT_TIMESTAMP WHERE id = :t", {"t": template_id})
    return page_rows


def attach_paper(db: Database, storage: PageStorage, template_id: int,
                 files: List[Tuple[str, bytes]]) -> List[Dict[str, Any]]:
    """Store the uploaded question paper as pages (kind 'paper') owned by the template, replacing any
    previous paper. Page image files are content-addressed and shared, so only the rows are replaced."""
    return _attach_pages(db, storage, template_id, "paper", files)


def attach_scheme(db: Database, storage: PageStorage, template_id: int,
                  files: List[Tuple[str, bytes]]) -> List[Dict[str, Any]]:
    """Store the uploaded mark scheme / rubric as pages (kind 'scheme'), replacing any previous one.
    The question paper is left alone."""
    return _attach_pages(db, storage, template_id, "scheme", files)


# --- extraction jobs ---------------------------------------------------------------------------

EXTRACT_WHAT = {"paper": PAPER_KIND, "scheme": SCHEME_KIND}


def enqueue_extract(db: Database, jobs: JobStore, template_id: int, what: str) -> int:
    """Queue a paper_extract / scheme_extract job for the template. 400 when the pages it would read
    are missing (or the assignment has no scheme type), 409 when one is already queued or running."""
    tpl = get_template(db, template_id)
    if tpl is None:
        raise ApiError(404, "not_found", "No such assignment")
    if what == "paper":
        if not tpl["paper_page_ids"]:
            raise ApiError(400, "no_paper", "Upload the question paper first")
    else:
        if tpl["scheme_kind"] not in ("mark_scheme", "rubric"):
            raise ApiError(400, "bad_scheme_kind", "Choose the assignment type (mark scheme or rubric) first")
        if not tpl["scheme_page_ids"]:
            raise ApiError(400, "no_scheme", "Upload the mark scheme or rubric first")
    job_id = jobs.enqueue_unique(EXTRACT_WHAT[what], {"template_id": template_id}, dedupe_key=dedupe_key(what, template_id))
    if job_id is None:
        raise ApiError(409, "already_running", f"The {what} is already being read")
    return job_id


def extract_status(db: Database, template_id: int) -> Dict[str, Dict[str, Any]]:
    """Latest paper/scheme extraction job per template: {status, error, job_id} (all None when never run)."""
    if get_template(db, template_id) is None:
        raise ApiError(404, "not_found", "No such assignment")
    out: Dict[str, Dict[str, Any]] = {}
    for what in EXTRACT_WHAT:
        rows = db.query("SELECT id, status, error FROM jobs WHERE dedupe_key = :d ORDER BY id DESC LIMIT 1",
                        {"d": dedupe_key(what, template_id)})
        r = rows[0] if rows else None
        out[what] = {"status": r["status"] if r else None, "error": r["error"] if r else None,
                     "job_id": r["id"] if r else None}
    return out


_EXPORT_FIELDS = ("title", "subject", "context", "rubric", "scheme_kind", "questions", "scheme")


def export_templates(db: Database) -> Dict[str, Any]:
    return {"version": 1, "assignments": [{k: t[k] for k in _EXPORT_FIELDS} for t in list_templates(db)]}


def _optional_bool(value: Any, index: int) -> Optional[bool]:
    if value is None or isinstance(value, bool):
        return value
    raise ApiError(400, "bad_import", f"Assignment {index + 1}: delete_pages_after_marking must be true, false or null")


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
                                   item.get("questions"), item.get("scheme"),
                                   _optional_bool(item.get("delete_pages_after_marking"), i), db=db))
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

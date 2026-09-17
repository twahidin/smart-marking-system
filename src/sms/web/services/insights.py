"""Per-assignment insights: statistics computed from stored marks, and the stored AI narrative."""
import json
import statistics
from typing import Any, Dict, List, Optional, Tuple

from sms.memory.db import Database
from sms.schemas.scheme import q_label
from sms.timeutil import iso_utc
from sms.web.services.assignments import get_template
from sms.web.services.class_assignments import roster
from sms.web.services.submissions import get_submission, row_key, row_max
from sms.worker.jobs import JobStore

BUCKETS = 5             # score bands in the spread
MOST_LOST = 8           # allocations listed in most_lost
SAMPLE_CHARS = 300      # a sample answer is trimmed to this
WEAK_PART = 0.5         # a student's part below this fraction of its marks is a weak part
FULL_CLASS = 5          # from this many marked scripts the min-attempts rule below applies
MIN_ATTEMPTS = 5        # ...and a part needs this many settled marks before it can rank as weakest
# A hand-in whose marks are not final yet: still queued, being marked, or waiting in the review queue.
PENDING_STATUSES = ("handed_in", "marking", "needs_you")

# One marked script: its roster row, its marks by part (see _part_marks) and its submission detail.
MarkedScript = Tuple[dict, Dict[str, dict], dict]


def _part_rows(template: Optional[dict], marked: List[MarkedScript]) -> List[dict]:
    """The parts statistics are grouped by: [{q_id, label, max, allocations: [label]}] in scheme order.

    A mark scheme / rubric template has one part per scheme row. A criteria template has no
    per-question scheme, so — as the marks CSV does — its parts are the questions the marked scripts
    answered, in first-seen order, each worth the rubric's total (the sum of its criterion maxima).
    Keying those by the scripts' own q_ids is what lets `_part_marks` find them."""
    if not template:
        return []
    kind = template["scheme_kind"]
    if kind == "mark_scheme":
        rows = [{"q_id": row_key(kind, r), "label": q_label(row_key(kind, r)), "max": row_max(kind, r),
                 "allocations": [m["label"] for m in r.get("marks") or []]} for r in template["scheme"]]
    elif kind == "rubric":
        rows = [{"q_id": row_key(kind, r), "label": row_key(kind, r), "max": row_max(kind, r),
                 "allocations": [b["band"] for b in r.get("bands") or []]} for r in template["scheme"]]
    else:
        per_q_max = sum(int(c["max_score"]) for c in template["rubric"]["criterion_defs"])
        rows = [{"q_id": q, "label": q_label(q), "max": per_q_max, "allocations": []}
                for q in dict.fromkeys(q for _, pm, _ in marked for q in pm)]
    seen: Dict[str, dict] = {}
    for row in rows:  # a scheme with the same q_id twice shows as one part, as the marks CSV does
        seen.setdefault(row["q_id"], row)
    return list(seen.values())


def _lost_allocations(part: dict) -> List[str]:
    """Mark-scheme allocations the script did not earn; the teacher's ticks win over the marker's."""
    teacher = part.get("teacher") or {}
    awarded = teacher["allocations"] if "allocations" in teacher else (part.get("awarded") or [])
    return [a["label"] for a in awarded if not a.get("got")]


def _lost_band(part: dict) -> List[str]:
    """A rubric criterion "loses" its band unless the script reached the scheme row's top band."""
    teacher = part.get("teacher") or {}
    band = teacher.get("band") or part.get("band") or ""
    bands = (part.get("scheme") or {}).get("bands") or []
    top = bands[0].get("band") if bands else None
    return [] if not band or band == top else [band]


def _part_marks(detail: dict) -> Dict[str, dict]:
    """One script's marks by part: q_id -> {total, max, pending, lost, extracted, justification,
    in_scheme, illegible}. `pending` is a part still in the review queue; the teacher's correction
    wins over the marker wherever there is one."""
    out: Dict[str, dict] = {}
    if detail.get("marks_version") == 2:
        rubric = detail.get("scheme_kind") == "rubric"
        for p in detail.get("parts") or []:
            teacher = p.get("teacher")
            out[p["q_id"]] = {
                "total": teacher["total"] if teacher else p["total"], "max": p["max"], "pending": bool(p["escalated"]),
                "lost": _lost_band(p) if rubric else _lost_allocations(p),
                "extracted": p.get("extracted") or "", "justification": p.get("justification") or "",
                "in_scheme": bool(p.get("in_scheme", True)), "illegible": bool(p.get("illegible", False)),
            }
    else:
        for m in detail.get("marks") or []:
            out[m["q_id"]] = {
                "total": sum(m["teacher_scores"]) if m.get("teacher_scores") else m["total"], "max": m["max"],
                "pending": bool(m["escalated"]), "lost": [], "extracted": m.get("evidence") or "",
                "justification": m.get("rationale") or "", "in_scheme": True, "illegible": False,
            }
    return out


def _marked_scripts(db: Database, jobs: JobStore, rows: List[dict]) -> List[MarkedScript]:
    """(roster row, marks by part, submission detail) per marked script, in register order."""
    out = []
    for r in rows:
        if r["submission_id"] is None:
            continue
        detail = get_submission(db, jobs, r["submission_id"])
        if detail and detail.get("run_id"):
            out.append((r, _part_marks(detail), detail))
    return out


def _buckets(totals: List[int], max_total: int, n: int = BUCKETS) -> List[dict]:
    """`n` score bands spanning 0..max_total, so full marks land in the last one. Band i starts at
    ceil(i * max_total / n) and runs to the mark before the next band; the last band ends at max_total."""
    edges = [-(-i * max_total // n) for i in range(n + 1)]
    counts = [0] * n
    for t in totals:
        clamped = min(max(int(t), 0), max_total)
        counts[min(n - 1, clamped * n // max_total) if max_total else 0] += 1
    return [{"from": edges[i], "to": max_total if i == n - 1 else max(edges[i], edges[i + 1] - 1), "n": counts[i]}
            for i in range(n)]


def compute_stats(db: Database, jobs: JobStore, ca: dict) -> Dict[str, Any]:
    """Class-level statistics for one assignment, from the marks already stored: how far the class has
    got, a row per scheme part (mean, full and zero scores, which allocations were lost), a row per
    marked student, the weakest parts and the spread of totals.

    A part's `attempted` counts the scripts with a settled (non-pending) mark for it, so it is also
    the `of` in every `most_lost` row — a part still waiting in the review queue counts under
    `pending` instead and stays out of the averages until it is resolved."""
    rows = roster(db, ca)["rows"]
    # The scripts come first: a criteria template's parts are only knowable from the marks themselves.
    marked = _marked_scripts(db, jobs, rows)
    parts = _part_rows(get_template(db, ca["template_id"]), marked)
    order = {p["q_id"]: i for i, p in enumerate(parts)}
    per_part = []
    for p in parts:
        seen = [pm[p["q_id"]] for _, pm, _ in marked if p["q_id"] in pm]
        scored = [x for x in seen if not x["pending"]]
        pct = [100.0 * x["total"] / p["max"] for x in scored] if p["max"] else []
        lost = {a: 0 for a in p["allocations"]}
        for x in scored:
            for label in x["lost"]:
                if label in lost:
                    lost[label] += 1
        per_part.append({
            "q_id": p["q_id"], "label": p["label"], "max": p["max"], "attempted": len(scored),
            "mean_pct": round(sum(pct) / len(pct), 1) if pct else None,
            "full": sum(1 for x in scored if p["max"] and x["total"] >= p["max"]),
            "zero": sum(1 for x in scored if x["total"] == 0),
            "allocations": [{"label": a, "lost": n} for a, n in lost.items()],
            "not_in_scheme": sum(1 for x in seen if not x["in_scheme"]),
            "illegible": sum(1 for x in seen if x["illegible"]),
            "pending": sum(1 for x in seen if x["pending"]),
        })
    max_total = sum(p["max"] for p in parts)
    students, totals = [], []
    for r, pm, detail in marked:
        total = detail["totals"]["total"] if detail.get("totals") else 0
        totals.append(total)
        weak = [p["q_id"] for p in parts
                if p["q_id"] in pm and not pm[p["q_id"]]["pending"] and p["max"]
                and pm[p["q_id"]]["total"] / p["max"] < WEAK_PART]
        students.append({"student_id": r["student_id"], "reg_no": r["reg_no"], "name": r["name"],
                         "total": total, "max": max_total, "weak_parts": weak})
    # Weakest first by mean, ties in scheme order. In a class-sized set a part only a handful of
    # scripts reached is too thin to call the class's weakest; below that every marked part ranks.
    min_attempts = MIN_ATTEMPTS if len(marked) >= FULL_CLASS else 1
    ranked = [p for p in per_part if p["mean_pct"] is not None and p["attempted"] >= min_attempts]
    weakest = [p["q_id"] for p in sorted(ranked, key=lambda p: (p["mean_pct"], order[p["q_id"]]))]
    most_lost = sorted(({"q_id": p["q_id"], "label": a["label"], "lost": a["lost"], "of": p["attempted"]}
                        for p in per_part for a in p["allocations"] if a["lost"]),
                       key=lambda a: -a["lost"])[:MOST_LOST]
    return {
        "n_students": len(rows), "n_marked": len(marked),
        "n_pending": sum(1 for r in rows if r["submission_id"] is not None and r["status"] in PENDING_STATUSES),
        "totals": {"mean": round(statistics.mean(totals), 1) if totals else None,
                   "median": statistics.median(totals) if totals else None,
                   "max": max_total, "buckets": _buckets(totals, max_total)},
        "parts": per_part, "weakest": weakest, "most_lost": most_lost, "students": students,
    }


def select_samples(db: Database, jobs: JobStore, ca: dict, stats: dict, per_part: int = 10,
                   max_parts: int = 4) -> List[Dict[str, Any]]:
    """Answers from the weakest parts for the narrative model to read: weakest part first, lowest score
    first inside a part (ties in register order), at most `per_part` per part over `max_parts` parts.
    Anonymous by construction — a row carries the register number, never the student's name or id."""
    marked = _marked_scripts(db, jobs, roster(db, ca)["rows"])
    out: List[Dict[str, Any]] = []
    for q_id in (stats.get("weakest") or [])[:max_parts]:
        found = []
        for r, pm, _ in marked:
            m = pm.get(q_id)
            if m is None or m["pending"]:
                continue
            found.append((m["total"] / m["max"] if m["max"] else 0.0,
                          {"part": q_id, "reg_no": r["reg_no"], "extracted": m["extracted"][:SAMPLE_CHARS],
                           "awarded": m["total"], "max": m["max"], "justification": m["justification"]}))
        found.sort(key=lambda f: f[0])
        out.extend(row for _, row in found[:per_part])
    return out


# --- the stored report ------------------------------------------------------------------------

def dedupe_key(caid: int) -> str:
    """Dedupe key of the generate-insights job for an assignment (one at a time per assignment)."""
    return f"insights:{caid}"


def load_insights(db: Database, caid: int) -> Optional[Dict[str, Any]]:
    """The stored insights for an assignment, or None when none have been generated yet."""
    rows = db.query("SELECT stats_json, report_json, n_marked, provider, model, generated_at, error "
                    "FROM assignment_insights WHERE class_assignment_id = :a", {"a": caid})
    if not rows:
        return None
    r = rows[0]
    return {"stats": json.loads(r["stats_json"]) if r["stats_json"] else None,
            "report": json.loads(r["report_json"]) if r["report_json"] else None,
            "n_marked": int(r["n_marked"] or 0), "provider": r["provider"], "model": r["model"],
            "generated_at": iso_utc(r["generated_at"]), "error": r["error"]}


def upsert_insights(db: Database, caid: int, *, stats: dict, report: Optional[dict], n_marked: int,
                    provider: Optional[str], model: Optional[str], error: Optional[str] = None) -> None:
    """Replace an assignment's insights — one row per assignment, re-stamped with the time it was
    generated. UPDATE first, then INSERT when there was no row, so it works on SQLite and Postgres."""
    params = {"a": caid, "s": json.dumps(stats), "r": json.dumps(report) if report is not None else None,
              "n": int(n_marked), "p": provider, "m": model, "e": error}
    if not db.execute("UPDATE assignment_insights SET stats_json = :s, report_json = :r, n_marked = :n, "
                      "provider = :p, model = :m, error = :e, generated_at = CURRENT_TIMESTAMP "
                      "WHERE class_assignment_id = :a", params):
        db.execute("INSERT INTO assignment_insights (class_assignment_id, stats_json, report_json, n_marked, "
                   "provider, model, error) VALUES (:a, :s, :r, :n, :p, :m, :e)", params)


def insights_payload(db: Database, jobs: JobStore, ca: dict) -> Dict[str, Any]:
    """What the insights endpoint returns: the stored insights when there are any, otherwise statistics
    computed live with no narrative yet, plus the generate job while one is queued or running."""
    saved = load_insights(db, ca["id"])
    if saved is None:
        stats = compute_stats(db, jobs, ca)
        saved = {"stats": stats, "report": None, "n_marked": stats["n_marked"], "provider": None,
                 "model": None, "generated_at": None, "error": None}
    job = jobs.active_by_dedupe(dedupe_key(ca["id"]))
    return {**saved, "job": {"status": job["status"]} if job else None}

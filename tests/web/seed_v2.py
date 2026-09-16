"""Seed helpers for version-2 (per-part) marking runs, shared by the web API tests."""
import json
from typing import Dict, Iterable, Optional, Tuple

QUESTIONS = [{"q_id": "1a", "text": "Solve 3x = 9", "max_marks": 2},
             {"q_id": "1b", "text": "Hence find x^2", "max_marks": 1},
             {"q_id": "2", "text": "Expand (x+1)^2", "max_marks": 3}]
SCHEME = [
    {"q_id": "1a", "answer": "x = 3", "marks": [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 1}], "notes": ""},
    {"q_id": "1b", "answer": "9", "marks": [{"label": "B1", "marks": 1}], "notes": "ECF from 1a"},
    {"q_id": "2", "answer": "x^2 + 2x + 1", "marks": [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 2}],
     "notes": "accept unsimplified"},
]
RUBRIC_QUESTIONS = [{"q_id": "1", "text": "Write about a memorable day.", "max_marks": 10}]
RUBRIC = [
    {"criterion": "Content", "bands": [{"band": "A", "marks": 5, "descriptor": "Rich, relevant detail"},
                                        {"band": "B", "marks": 3, "descriptor": "Some relevant detail"}]},
    {"criterion": "Language", "bands": [{"band": "A", "marks": 5, "descriptor": "Accurate and varied"},
                                         {"band": "B", "marks": 2, "descriptor": "Mostly accurate"}]},
]


def _alloc(label, marks, got, why=""):
    return {"label": label, "marks": marks, "got": got, "why": why}


def part(q_id, awarded, total, justification="", in_scheme=True, confidence=0.9):
    return {"q_id": q_id, "awarded": awarded, "total": total, "justification": justification,
            "in_scheme": in_scheme, "confidence": confidence}


DEFAULT_PARTS = [
    part("1a", [_alloc("M1", 1, True, "3x=9 seen"), _alloc("A1", 1, True, "x=3")], 2, "M1 for the division; A1 for x = 3"),
    part("1b", [_alloc("B1", 1, False, "wrote 6")], 0, "B1 lost: 6 not 9"),
    part("2", [_alloc("M1", 1, True), _alloc("A1", 2, False)], 1, "Different method", in_scheme=False, confidence=0.6),
]
DEFAULT_EXTRACTED = {"questions": [
    {"q_id": "1a", "transcribed_answer": "x = 3", "workings": "3x = 9, x = 9/3", "confidence": 0.9, "needs_human_transcription": False},
    {"q_id": "1b", "transcribed_answer": "6", "workings": "", "confidence": 0.8, "needs_human_transcription": False},
    {"q_id": "2", "transcribed_answer": "x^2 + 2x + 1", "workings": "(x+1)(x+1)", "confidence": 0.9, "needs_human_transcription": False},
]}
DEFAULT_QUEUE = {"2": "not in scheme"}


def seed_v2(app, *, kind="mark_scheme", parts=None, rubric=None, extracted=None, queue: Optional[Dict[str, str]] = None,
            label="Tan", run_id="r2", status=None, questions=None, scheme=None, notes="ECF applies",
            assignment_id=None, subject="math", provider="openai", model="gpt-5-mini") -> Tuple[int, Dict[str, int]]:
    """Insert a submission with a v2 run. Returns (submission_id, {q_id: queue_item_id})."""
    db = app.state.db
    if kind == "mark_scheme":
        questions = QUESTIONS if questions is None else questions
        scheme = SCHEME if scheme is None else scheme
        parts = DEFAULT_PARTS if parts is None else parts
        rubric = []
    else:
        questions = RUBRIC_QUESTIONS if questions is None else questions
        scheme = RUBRIC if scheme is None else scheme
        parts = []
        rubric = [{"criterion": "Content", "band": "A", "marks": 5, "descriptor_met": "Rich, relevant detail",
                   "justification": "Vivid detail throughout", "confidence": 0.9},
                  {"criterion": "Language", "band": "B", "marks": 2, "descriptor_met": "Mostly accurate",
                   "justification": "Some tense slips", "confidence": 0.5}] if rubric is None else rubric
    extracted = DEFAULT_EXTRACTED if extracted is None else extracted
    queue = (DEFAULT_QUEUE if kind == "mark_scheme" else {"Language": "low confidence"}) if queue is None else queue
    status = status or ("needs_you" if queue else "done")
    rubric_json = {"scheme_kind": kind, "questions": questions, "scheme": scheme, "notes": notes}
    final = {"version": 2, "kind": kind, "parts": parts, "rubric": rubric}
    reviewed = {"verdicts": [{"q_id": k, "verdict": "ESCALATE", "adjusted": None, "reviewer_note": f"unsure about {k}"}
                             for k in queue]}
    feedback = {"summary": "Good effort.", "strengths": ["method"], "per_question_comments": [],
                "improvement_plan": [], "next_steps": []}
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status, run_id, marks_version, assignment_id) "
                    "VALUES (:l, :subj, '', '{\"criterion_defs\": [{\"id\": \"c1\", \"description\": \"d\", \"max_score\": 1}]}', "
                    ":st, :r, 2, :aid) RETURNING id",
                    {"l": label, "subj": subject, "st": status, "r": run_id, "aid": assignment_id})
    db.execute("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height) "
               "VALUES (:s, 0, :h, :p, 1, 1)", {"s": sid, "h": f"h{sid}", "p": f"pages/h{sid}.jpg"})
    db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, marks_json, reviewed_json, "
               "feedback_json, final_marks_json, submission_id, final_status, provider, model) "
               "VALUES (:r, 'complete', :subj, :rubric, :ex, :marks, :rev, :fb, :final, :s, :fs, :p, :m)",
               {"r": run_id, "subj": subject, "rubric": json.dumps(rubric_json), "ex": json.dumps(extracted),
                "marks": json.dumps(final), "rev": json.dumps(reviewed), "fb": json.dumps(feedback),
                "final": json.dumps(final), "s": sid, "fs": "escalated" if queue else "complete", "p": provider, "m": model})
    qids = {}
    for key, reason in queue.items():
        qids[key] = db.insert("INSERT INTO teacher_queue (run_id, q_id, reason, status, submission_id) "
                              "VALUES (:r, :q, :reason, 'pending', :s) RETURNING id",
                              {"r": run_id, "q": key, "reason": reason, "s": sid})
    return sid, qids

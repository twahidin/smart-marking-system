import argparse
import json
import os
import sys
from pathlib import Path

import instructor
import openai

from sms.agents.extractor import build_extractor
from sms.agents.feedback import build_feedback
from sms.agents.marker import build_marker
from sms.agents.reflection import build_reflection
from sms.agents.reviewer import build_reviewer
from sms.learning.reflection_job import run_reflection
from sms.memory.db import Database
from sms.memory.metrics import MetricsSummary
from sms.pipeline.marking_pipeline import MarkingPipeline
from sms.schemas.marking import Rubric


def _client():
    return instructor.from_openai(openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "missing")))


def _mark(args) -> int:
    db = Database(path=args.db)
    rubric = Rubric.model_validate_json(Path(args.rubric).read_text())
    images = [Path(p).read_bytes() for p in args.images]
    pipeline = MarkingPipeline(
        db=db,
        extractor=build_extractor(client=_client(), model=args.model),
        marker=build_marker(client=_client(), model=args.model, subject=args.subject, db=db),
        reviewer=build_reviewer(client=_client(), model=args.model, subject=args.subject, db=db),
        feedback=build_feedback(client=_client(), model=args.model),
        subject=args.subject,
    )
    result = pipeline.run(images=images, assignment_context=args.context, rubric=rubric)
    print(json.dumps({
        "run_id": result.run_id,
        "escalations": result.escalations,
        "marks": [m.model_dump() for m in result.final_marks.marks],
        "feedback": result.feedback.model_dump() if result.feedback else None,
    }, indent=2))
    return 0


def _reflect(args) -> int:
    db = Database(path=args.db)
    agent = build_reflection(client=_client(), model=args.model)
    proposed = run_reflection(db=db, agent=agent, subject=args.subject, lookback_days=args.lookback)
    print(f"Proposed {proposed} rubric note(s) as draft. Review with: sms notes list --db {args.db}")
    return 0


def _evaluate(args) -> int:
    db = Database(path=args.db)
    rows = db.query("SELECT agent_mark, teacher_mark FROM teacher_corrections")
    if not rows:
        print("No corrections recorded yet.")
        return 0
    agree = sum(1 for r in rows if r["agent_mark"] == r["teacher_mark"])
    total = len(rows)
    print(f"Agreement: {agree}/{total} ({100 * agree / total:.1f}%)")
    return 0


def _stats(args) -> int:
    db = Database(path=args.db)
    for role in ("extractor", "marker", "reviewer", "feedback", "reflection"):
        s = MetricsSummary(db).summarize(agent_role=role)
        if s["count"]:
            print(f"{role}: {s['count']} runs, mean {s['mean_latency_ms']:.0f}ms, "
                  f"{s['total_tokens_in']} in / {s['total_tokens_out']} out tokens")
    return 0


def _queue_list(args) -> int:
    db = Database(path=args.db)
    rows = db.query("SELECT * FROM teacher_queue WHERE status = 'pending'")
    if not rows:
        print("Queue empty.")
        return 0
    for r in rows:
        print(f"[{r['id']}] run={r['run_id']} q={r['q_id']} reason={r['reason']}")
    return 0


def _queue_resolve(args) -> int:
    db = Database(path=args.db)
    row = db.query("SELECT run_id, q_id FROM teacher_queue WHERE id = ?", (args.queue_id,))[0]
    db.execute("UPDATE teacher_queue SET status = 'resolved' WHERE id = ?", (args.queue_id,))
    db.execute(
        "INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason) "
        "VALUES (?, ?, NULL, ?, ?)",
        (row["run_id"], row["q_id"], args.teacher_mark, args.reason or ""),
    )
    print(f"Resolved #{args.queue_id}.")
    return 0


def _notes_list(args) -> int:
    db = Database(path=args.db)
    for r in db.query("SELECT id, subject, note, status FROM rubric_notes"):
        print(f"[{r['id']}] ({r['status']}) {r['subject']}: {r['note']}")
    return 0


def _notes_approve(args) -> int:
    db = Database(path=args.db)
    db.execute("UPDATE rubric_notes SET status = 'active' WHERE id = ?", (args.note_id,))
    print(f"Activated note #{args.note_id}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sms", description="Smart Marking System")

    sub = parser.add_subparsers(dest="command", required=True)

    p_mark = sub.add_parser("mark", help="Mark a script from images")
    p_mark.add_argument("images", nargs="+")
    p_mark.add_argument("--subject", default="math")
    p_mark.add_argument("--rubric", required=True)
    p_mark.add_argument("--context", default="Student exam script")
    p_mark.add_argument("--db", default="sms.db")
    p_mark.add_argument("--model", default="gpt-5-mini")
    p_mark.set_defaults(func=_mark)

    p_reflect = sub.add_parser("reflect", help="Run nightly reflection")
    p_reflect.add_argument("--subject", default="math")
    p_reflect.add_argument("--lookback", type=int, default=7)
    p_reflect.add_argument("--db", default="sms.db")
    p_reflect.add_argument("--model", default="gpt-5-mini")
    p_reflect.set_defaults(func=_reflect)

    sub_eval = sub.add_parser("evaluate", help="Show agent-teacher agreement")
    sub_eval.add_argument("--db", default="sms.db")
    sub_eval.set_defaults(func=_evaluate)

    sub_stats = sub.add_parser("stats", help="Show agent metrics")
    sub_stats.add_argument("--db", default="sms.db")
    sub_stats.set_defaults(func=_stats)

    p_queue = sub.add_parser("queue", help="Teacher queue")
    q_sub = p_queue.add_subparsers(dest="queue_command", required=True)
    q_list = q_sub.add_parser("list")
    q_list.add_argument("--db", default="sms.db")
    q_list.set_defaults(func=_queue_list)
    q_resolve = q_sub.add_parser("resolve")
    q_resolve.add_argument("queue_id", type=int)
    q_resolve.add_argument("--teacher-mark", type=int, required=True)
    q_resolve.add_argument("--reason", default="")
    q_resolve.add_argument("--db", default="sms.db")
    q_resolve.set_defaults(func=_queue_resolve)

    p_notes = sub.add_parser("notes", help="Rubric notes")
    n_sub = p_notes.add_subparsers(dest="notes_command", required=True)
    n_list = n_sub.add_parser("list")
    n_list.add_argument("--db", default="sms.db")
    n_list.set_defaults(func=_notes_list)
    n_approve = n_sub.add_parser("approve")
    n_approve.add_argument("note_id", type=int)
    n_approve.add_argument("--db", default="sms.db")
    n_approve.set_defaults(func=_notes_approve)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

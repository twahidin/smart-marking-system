import { ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import type { StudentAssignmentDetail, StudentFeedback } from "../api/types";
import { fmtDate } from "../lib/format";
import { studentApi as api } from "./api";

const UNREACHABLE = "Can't reach Smart Marking — check your signal and try again.";

/** `max` squares with `total` of them filled — decorative; the numbers beside it carry the meaning. */
function Blocks({ total, max }: { total: number; max: number }) {
  const n = Math.max(0, Math.round(max));
  const on = Math.min(n, Math.max(0, Math.round(total)));
  if (n === 0) return null;
  return (
    <div className="blocks" aria-hidden>
      {Array.from({ length: n }, (_, i) => <i key={i} className={i < on ? "on" : undefined} />)}
    </div>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section>
      <h2>{title}</h2>
      <ul className="student-points">{items.map((s, i) => <li key={i}>{s}</li>)}</ul>
    </section>
  );
}

function Feedback({ fb }: { fb: StudentFeedback }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <>
      <div className="student-total">
        <span className="big">{fb.total ?? "—"}</span>
        <span className="muted">{`/ ${fb.max ?? "—"}`}</span>
      </div>
      {fb.total !== null && fb.max !== null && <Blocks total={fb.total} max={fb.max} />}
      {fb.summary && <p className="student-summary">{fb.summary}</p>}
      <List title="What you did well" items={fb.strengths} />
      <section>
        <h2>Question by question</h2>
        {fb.questions.length === 0 && <p className="muted">No questions were marked.</p>}
        {fb.questions.map((q, i) => {
          const isOpen = open === i;
          return (
            <div className="qrow" key={i} style={{ display: "block" }}>
              <button type="button" aria-expanded={isOpen} aria-label={`${q.label} · ${q.mark} / ${q.max}`} onClick={() => setOpen(isOpen ? null : i)}>
                <strong>{q.label}</strong>
                <span className="student-qmark">{`${q.mark} / ${q.max}`}{isOpen ? <ChevronUp size={20} aria-hidden /> : <ChevronDown size={20} aria-hidden />}</span>
              </button>
              {isOpen && (
                <div className="qrow-body">
                  <p className="student-comment">{q.comment || "No comment for this question."}</p>
                  {q.try_next && <p className="callout">{`Try next: ${q.try_next}`}</p>}
                  {q.transcription && (
                    <div className="callout">
                      <span className="label-caps">What we read from your page</span>
                      <div className="student-read">{q.transcription}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {fb.pages.length > 0 && (
          <div className="student-feedback-pages">
            {fb.pages.map((id, i) => <img key={id} className="student-feedback-page" src={`/api/student/pages/${id}`} alt={`Your page ${i + 1}`} loading="lazy" />)}
          </div>
        )}
      </section>
      <List title="Work on next" items={fb.improvement_plan} />
      <List title="Next steps" items={fb.next_steps} />
    </>
  );
}

export function AssignmentView() {
  const { caid } = useParams();
  const [detail, setDetail] = useState<StudentAssignmentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    setError(null);
    api.get<StudentAssignmentDetail>(`/api/student/assignments/${caid}`).then(
      setDetail,
      (e) => setError(e instanceof ApiError ? e.message : UNREACHABLE),
    );
  };
  useEffect(load, [caid]);

  if (error) {
    return (
      <>
        <p role="alert" className="notice notice-error">{error}</p>
        <button type="button" className="btn btn-secondary btn-lg" onClick={load}>Try again</button>
      </>
    );
  }
  if (!detail) return <p className="muted">Loading…</p>;
  if (detail.status === "to_hand_in") return <Navigate to={`/s/a/${caid}/hand-in`} replace />;

  const back = <Link className="btn btn-secondary btn-lg" to="/s">Back to assignments</Link>;
  if (detail.status === "handed_in") {
    return (
      <>
        <h1>{detail.title}</h1>
        <p className="notice notice-ok student-done">{`Handed in ${fmtDate(detail.handed_in_at)}.`}</p>
        <p className="help">Marking usually takes a day. We'll show your feedback here.</p>
        {back}
      </>
    );
  }
  if (detail.status === "checking" || !detail.feedback) {
    return (
      <>
        <h1>{detail.title}</h1>
        <p className="notice notice-ok student-done">Marked — your teacher is checking.</p>
        <p className="help">Come back when your teacher releases the feedback.</p>
        {back}
      </>
    );
  }
  return (
    <>
      <Link className="student-back" to="/s">Back to assignments</Link>
      <h1>{detail.title}</h1>
      <p className="muted student-due">{`Handed in ${fmtDate(detail.handed_in_at)}`}</p>
      <Feedback fb={detail.feedback} />
    </>
  );
}

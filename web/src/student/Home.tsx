import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { ApiError } from "../api/client";
import type { StudentAssignment } from "../api/types";
import { fmtDate } from "../lib/format";
import { studentApi as api } from "./api";
import type { StudentOutletContext } from "./StudentLayout";

function StatusControl({ a }: { a: StudentAssignment }) {
  switch (a.status) {
    case "to_hand_in":
      return a.allow_student_uploads
        ? <Link className="btn btn-primary" to={`/s/a/${a.id}/hand-in`}>To hand in</Link>
        : <p className="muted student-status">Hand-ins closed</p>;
    case "handed_in":
      return <Link className="btn btn-secondary" to={`/s/a/${a.id}`}>Handed in · marking</Link>;
    case "checking":
      return <p className="muted student-status">Marked — your teacher is checking</p>;
    case "feedback_ready":
      return <Link className="btn btn-primary" to={`/s/a/${a.id}`}>Feedback ready</Link>;
  }
}

export function Home() {
  const { me } = useOutletContext<StudentOutletContext>();
  const [items, setItems] = useState<StudentAssignment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    setError(null);
    api.get<StudentAssignment[]>("/api/student/assignments").then(
      setItems,
      (e) => setError(e instanceof ApiError ? e.message : "Can't reach Smart Marking — check your signal and try again."),
    );
  };
  useEffect(load, []);
  return (
    <>
      <h1>{me.class_name}</h1>
      {error && (
        <>
          <p role="alert" className="notice notice-error">{error}</p>
          <button type="button" className="btn btn-secondary btn-lg" onClick={load}>Try again</button>
        </>
      )}
      {!error && items === null && <p className="muted">Loading…</p>}
      {items && items.length === 0 && <p className="muted student-empty">No assignments yet — check back when your teacher sets one.</p>}
      {items && items.length > 0 && (
        <ul className="student-list">
          {items.map((a) => (
            <li key={a.id} className="student-card">
              <h2>{a.title}</h2>
              <p className="muted student-due">{a.due_at ? `Due ${fmtDate(a.due_at)}` : "No due date"}</p>
              <StatusControl a={a} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

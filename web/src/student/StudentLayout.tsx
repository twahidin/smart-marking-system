import { useEffect, useState } from "react";
import { Navigate, Outlet, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import type { StudentMe } from "../api/types";
import { studentApi as api } from "./api";

type State = { kind: "loading" } | { kind: "ready"; me: StudentMe } | { kind: "anon" } | { kind: "error" };

export interface StudentOutletContext { me: StudentMe }

export function StudentLayout() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [leaving, setLeaving] = useState(false);
  const nav = useNavigate();
  const load = () => {
    setState({ kind: "loading" });
    api.get<StudentMe>("/api/student/me").then(
      (me) => setState({ kind: "ready", me }),
      (e) => setState(e instanceof ApiError && e.status === 401 ? { kind: "anon" } : { kind: "error" }),
    );
  };
  useEffect(load, []);
  const notMe = async () => {
    setLeaving(true);
    try { await api.delete("/api/student/session"); } catch { /* the cookie may already be gone — either way, start over */ }
    nav("/join", { replace: true });
  };
  if (state.kind === "loading") return <div className="student"><p className="muted">Loading…</p></div>;
  if (state.kind === "anon") return <Navigate to="/join" replace />;
  if (state.kind === "error") {
    return (
      <div className="student">
        <p role="alert" className="notice notice-error">Can't reach Smart Marking — check your signal and try again.</p>
        <button type="button" className="btn btn-secondary btn-lg" onClick={load}>Try again</button>
      </div>
    );
  }
  const { me } = state;
  return (
    <div className="student">
      <header className="student-header">
        <span className="student-brand">Smart Marking</span>
        <span className="student-who">
          <span>{`${me.student_name} · #${me.reg_no}`}</span>
          <button type="button" className="btn btn-ghost student-notme" disabled={leaving} onClick={notMe}>Not me?</button>
        </span>
      </header>
      <Outlet context={{ me } satisfies StudentOutletContext} />
    </div>
  );
}

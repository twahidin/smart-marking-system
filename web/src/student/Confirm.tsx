import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { studentApi as api } from "./api";

interface ConfirmState { code: string; reg_no: number; student_name: string; class_name: string }

function readState(state: unknown): ConfirmState | null {
  const s = state as Partial<ConfirmState> | null | undefined;
  if (!s || typeof s.code !== "string" || typeof s.reg_no !== "number" || typeof s.student_name !== "string" || typeof s.class_name !== "string") return null;
  return { code: s.code, reg_no: s.reg_no, student_name: s.student_name, class_name: s.class_name };
}

export function Confirm() {
  const loc = useLocation();
  const nav = useNavigate();
  const state = readState(loc.state);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!state) return <Navigate to="/join" replace />;
  const { code, reg_no, student_name, class_name } = state;
  const yes = async () => {
    setBusy(true); setError(null);
    try {
      await api.post("/api/student/session", { code, reg_no });
      nav("/s", { replace: true });
    } catch (err) { setError(err instanceof ApiError ? err.message : "Can't reach Smart Marking — check your signal and try again."); }
    finally { setBusy(false); }
  };
  return (
    <div className="student">
      <h1>Is this you?</h1>
      <p className="student-confirm">{`Are you ${student_name}, #${reg_no} of ${class_name}?`}</p>
      {error && <p role="alert" className="notice notice-error">{error}</p>}
      <div className="student-actions">
        <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={yes}>Yes, that's me</button>
        <button type="button" className="btn btn-secondary btn-lg" disabled={busy} onClick={() => nav(`/c/${code}`)}>Not me</button>
      </div>
    </div>
  );
}

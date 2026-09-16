import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import type { StudentMe } from "../api/types";
import { parseStudentId, studentApi as api } from "./api";

export function Enter() {
  const { code: codeParam } = useParams();
  const nav = useNavigate();
  const fixed = codeParam ? codeParam.toUpperCase() : null;
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const id = fixed ? parseStudentId(`${fixed}-${value}`) : parseStudentId(value);
    if (!id) { setError(fixed ? "Type your register number — just the number." : "Type your ID like CE4R-12."); return; }
    setBusy(true); setError(null);
    try {
      const me = await api.post<StudentMe>("/api/student/lookup", id);
      nav("/s/confirm", { state: { ...id, ...me } });
    } catch (err) { setError(err instanceof ApiError ? err.message : "Can't reach Smart Marking — check your signal and try again."); }
    finally { setBusy(false); }
  };
  return (
    <div className="student">
      <h1>Enter your number</h1>
      <form onSubmit={submit}>
        {fixed ? (
          <div className="student-id"><span className="student-id-prefix">{fixed}-</span>
            <input aria-label="Your register number" className="input" inputMode="numeric" pattern="[0-9]*" autoFocus value={value} onChange={(e) => setValue(e.target.value.replace(/\D/g, ""))} /></div>
        ) : (
          <div className="field"><label htmlFor="sid">Your student ID</label><input id="sid" className="input" autoFocus placeholder="CE4R-12" value={value} onChange={(e) => setValue(e.target.value)} /></div>
        )}
        {error && <p role="alert" className="notice notice-error">{error}</p>}
        <button className="btn btn-primary btn-lg" disabled={busy || !value.trim()}>Continue</button>
      </form>
      <p className="help">Your teacher shared a link and your register number is on the class list.</p>
    </div>
  );
}

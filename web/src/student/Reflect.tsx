import { Camera } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import type { StudentAssignmentDetail } from "../api/types";
import { downscale } from "../lib/image";
import { studentApi as api } from "./api";

const UNREACHABLE = "Can't reach Smart Marking — check your signal and try again.";
const REASONS = [["sign", "Sign slip"], ["method", "Wrong method"], ["rushed", "Rushed it"], ["misread", "Misread the question"]] as const;
const daysLeft = (n: number) => `${n} day${n === 1 ? "" : "s"} left`;

export function Reflect() {
  const { caid, qid } = useParams();
  const [detail, setDetail] = useState<StudentAssignmentDetail | null>(null);
  const [reason, setReason] = useState<string>("sign");
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);
  const camera = useRef<HTMLInputElement>(null);
  useEffect(() => {
    api.get<StudentAssignmentDetail>(`/api/student/assignments/${caid}`).then(
      setDetail,
      (e) => setError(e instanceof ApiError ? e.message : UNREACHABLE),
    );
  }, [caid]);
  const q = detail?.feedback?.questions.find((x) => x.q_id === qid);
  const part = detail?.reflection?.parts[qid ?? ""];
  const back = <Link className="student-back" to={`/s/a/${caid}`}>Back to feedback</Link>;
  if (!detail) {
    return error ? <p role="alert" className="notice notice-error">{error}</p> : <p className="muted">Loading…</p>;
  }
  if (!q) return <>{back}<p className="muted">That question isn't in this feedback.</p></>;
  const send = async () => {
    setState("sending"); setError(null);
    try {
      const form = new FormData();
      form.append("q_id", q.q_id); form.append("reason", reason); form.append("text", text);
      if (photo) form.append("photo", await downscale(photo));
      await api.postForm(`/api/student/assignments/${caid}/corrections`, form);
      setState("sent");
    } catch (e) {
      setState("idle");
      setError(e instanceof ApiError ? e.message : UNREACHABLE);
    }
  };
  return (
    <>
      {back}
      <h1>{`${q.label} · Reflect and correct`}</h1>
      {detail.reflection && (
        <div className="reflect-chips">
          <span className="pill pill-amber">{daysLeft(detail.reflection.days_left)}</span>
          <span className="pill pill-crew-marker">{part?.can_correct || state === "sent" ? "1 correction left" : "No corrections left"}</span>
        </div>
      )}
      <section className="student-card">
        <span className="label-caps">{`Your first try · ${q.mark} / ${q.max}`}</span>
        {q.crop_id !== null && <img className="reflect-crop" src={`/api/student/crops/${q.crop_id}`} alt="Your first try" />}
        {q.comment && <p className="student-comment"><strong>Marker:</strong> {q.comment}</p>}
      </section>
      {state === "sent" ? (
        <p role="status" className="notice notice-ok">Sent to the Marker. Your teacher checks it before you see the new mark.</p>
      ) : (
        <section className="student-card reflect-form">
          <h2>1 · What went wrong?</h2>
          <div className="reflect-reasons">
            {REASONS.map(([id, label]) => (
              <button key={id} type="button" aria-pressed={reason === id} className={`btn btn-sm ${reason === id ? "btn-primary" : "btn-secondary"}`} onClick={() => setReason(id)}>{label}</button>
            ))}
          </div>
          <h2>2 · Your corrected working</h2>
          <p className="help">Type it, or photograph your corrected working.</p>
          <textarea id="working" aria-label="Your corrected working" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => camera.current?.click()}><Camera size={18} aria-hidden /> Take a photo instead</button>
          <input ref={camera} type="file" accept="image/*" capture="environment" hidden aria-label="Photo of your corrected working"
            onChange={(e) => { setPhoto(e.target.files?.[0] ?? null); e.target.value = ""; }} />
          {photo && <p className="help">{photo.name}</p>}
          {error && <p role="alert" className="notice notice-error">{error}</p>}
          <p className="help">The Marker re-marks your correction against the same scheme. Your teacher checks it before you see the new mark.</p>
          <button type="button" className="btn btn-primary btn-lg" disabled={state === "sending" || !part?.can_correct || (!text.trim() && !photo)} onClick={send}>Send my correction</button>
        </section>
      )}
    </>
  );
}

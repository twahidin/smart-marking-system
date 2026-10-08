import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Crew, Thoughts } from "../api/types";

const NAME: Record<Crew, string> = { reader: "Reader", marker: "Marker", checker: "Checker" };
const ROLE: Record<Crew, string> = { reader: "finds each part on the page and reads the working", marker: "awards each mark against your scheme", checker: "re-marks independently and flags disagreements" };
const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function ThoughtPanel({ submissionId, crew, label, onClose, refreshKey = 0 }: { submissionId: number; crew: Crew; label: string; onClose: () => void; refreshKey?: number }) {
  const [loaded, setLoaded] = useState<{ id: number; thoughts: Thoughts } | null>(null);
  const [error, setError] = useState<string | null>(null);
  // refreshKey changes as the room moves on: refetch in place, without blanking the notes already shown.
  useEffect(() => {
    let alive = true;
    setError(null);
    api.get<Thoughts>(`/api/submissions/${submissionId}/thoughts`)
      .then((t) => { if (alive) setLoaded({ id: submissionId, thoughts: t }); })
      .catch((e) => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [submissionId, refreshKey]);
  const thoughts = loaded?.id === submissionId ? loaded.thoughts : null;
  const notes = thoughts?.[crew] ?? [];
  return (
    <aside className="card thought-panel" aria-label={`${NAME[crew]}'s thoughts`}>
      <div className="thought-head">
        <img src="/art/crew.jpg" alt="" className={`crew-face crew-face-${crew}`} />
        <div><div className="thought-name">{NAME[crew]}</div><div className="muted">{ROLE[crew]}</div></div>
        <span className="pill pill-neutral">Teachers only</span>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose} aria-label="Close">×</button>
      </div>
      <div className="thought-who"><strong>{label}</strong></div>
      {error && <p className="notice notice-error">{error}</p>}
      {thoughts && notes.length === 0 && <p className="muted">Nothing noted yet.</p>}
      <ol className="thought-list">
        {notes.map((t, i) => <li key={i}><span className="tabular thought-at">{fmtTime(t.at)}</span><p>{t.q_id ? <strong>{t.q_id} · </strong> : null}{t.note}</p></li>)}
      </ol>
      <div className="actions">
        <Link className="btn btn-primary" to={`/submissions/${submissionId}`}>Open script</Link>
        <Link className="btn btn-secondary" to="/review">Open Review</Link>
      </div>
    </aside>
  );
}

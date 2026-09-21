import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Exemplar, Note, ReflectionRuns, Stats, Subject } from "../api/types";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { fmtDate, SUBJECTS, subjectLabel } from "../lib/format";

export function Learning() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [ex, setEx] = useState<Exemplar[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [runs, setRuns] = useState<ReflectionRuns>({ runs: [], pending: [] });
  const [subject, setSubject] = useState<Subject>("math");
  const [queued, setQueued] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() =>
    Promise.all([api.get<Note[]>("/api/notes"), api.get<Exemplar[]>("/api/exemplars"), api.get<Stats>("/api/stats"), api.get<ReflectionRuns>("/api/reflect/runs")])
      .then(([n, e, s, r]) => { setNotes(n); setEx(e); setStats(s); setRuns(r); setError(null); })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load")), []);
  useEffect(() => { load(); }, [load]);
  // While a reflection is queued or running, poll so the notes appear without a refresh.
  useEffect(() => {
    if (runs.pending.length === 0) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [runs.pending.length, load]);

  const runReflection = async () => {
    setBusy(true); setError(null); setQueued(false);
    try { await api.post("/api/reflect", { subject, lookback_days: 7 }); setQueued(true); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not start reflection"); }
    finally { setBusy(false); }
  };
  const approveNote = async (id: number) => {
    try { await api.post(`/api/notes/${id}/approve`); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load"); }
  };
  const approveEx = async (id: number) => {
    try { await api.post(`/api/exemplars/${id}/approve`); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load"); }
  };
  const pendingHere = runs.pending.includes(subject);
  // A running job already has an open run row (finished_at null) in the list; only show the rest as queued.
  const queuedOnly = runs.pending.filter((s) => !runs.runs.some((r) => r.subject === s && r.finished_at === null));
  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Learning</h1><p className="meta">What the marker has learned from your corrections. Approve a draft to use it on the next run.</p></div>
        <div className="actions" style={{ alignItems: "center", flexWrap: "nowrap" }}>
          <select className="input" aria-label="Subject" style={{ width: "auto" }} value={subject} onChange={(e) => setSubject(e.target.value as Subject)}>
            {SUBJECTS.map((s) => <option key={s} value={s}>{subjectLabel[s]}</option>)}
          </select>
          <Button variant="primary" onClick={runReflection} disabled={busy || pendingHere}>{pendingHere ? "Reflection queued…" : busy ? "Starting…" : "Run reflection"}</Button>
        </div>
      </div>
      {error && <div style={{ marginBottom: 16 }}><Notice kind="error">{error}</Notice></div>}
      {queued && !error && <div style={{ marginBottom: 16 }}><Notice kind="ok">Reflection queued — notes appear below when it finishes.</Notice></div>}
      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", borderTop: "2px solid var(--color-divider)", borderBottom: "2px solid var(--color-divider)", marginBottom: 32 }}>
          {Object.entries(stats).map(([role, s]) => (
            <div key={role} style={{ padding: "18px 20px 16px", borderRight: "1px solid var(--color-divider)" }}>
              <div style={{ fontSize: 36, fontWeight: 800, lineHeight: 1 }}>{s.count}</div>
              <div className="muted">{role} runs · {s.count ? `${Math.round(s.mean_latency_ms / 1000)} s avg` : "—"}</div>
            </div>
          ))}
        </div>
      )}
      <h4>Rubric notes</h4>
      {error ? null : notes.length === 0 ? <EmptyState title="No notes yet."><p>Resolve a few questions in Review, then run reflection (or leave it to run nightly).</p></EmptyState> : (
        <table className="table"><thead><tr><th>Subject</th><th>Note</th><th>Status</th><th /></tr></thead>
          <tbody>{notes.map((n) => <tr key={n.id}><td>{n.subject}</td><td>{n.note}</td><td><span className={`pill ${n.status === "active" ? "pill-ink" : "pill-outline"}`}>{n.status === "active" ? "Active" : "Draft"}</span></td><td>{n.status !== "active" && <Button size="sm" onClick={() => approveNote(n.id)}>Approve</Button>}</td></tr>)}</tbody>
        </table>
      )}
      <h4 style={{ marginTop: 32 }}>Exemplar cases</h4>
      {error ? null : ex.length === 0 ? <p className="muted">None yet.</p> : (
        <table className="table"><thead><tr><th>Topic</th><th>Answer</th><th className="num">Marks</th><th>Why it matters</th><th>Status</th><th /></tr></thead>
          <tbody>{ex.map((e) => <tr key={e.id}><td>{e.subject} / {e.topic}</td><td>{e.answer_text}</td><td className="num">{e.awarded} / {e.max_score}</td><td className="help">{e.why_it_matters}</td><td><span className={`pill ${e.status === "active" ? "pill-ink" : "pill-outline"}`}>{e.status === "active" ? "Active" : "Draft"}</span></td><td>{e.status !== "active" && <Button size="sm" onClick={() => approveEx(e.id)}>Approve</Button>}</td></tr>)}</tbody>
        </table>
      )}
      {!error && (runs.runs.length > 0 || runs.pending.length > 0) && (
        <>
          <h4 style={{ marginTop: 32 }}>Recent runs</h4>
          <ul className="help" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {queuedOnly.map((s) => <li key={`p-${s}`} style={{ padding: "6px 0", borderBottom: "1px solid var(--color-divider)" }}><strong>{subjectLabel[s] ?? s}</strong> · queued</li>)}
            {runs.runs.map((r) => (
              <li key={r.id} style={{ padding: "6px 0", borderBottom: "1px solid var(--color-divider)" }}>
                <strong>{subjectLabel[r.subject] ?? r.subject}</strong> · {fmtDate(r.finished_at ?? r.started_at)} · {r.error ? <span style={{ color: "var(--color-accent-700)" }}>failed: {r.error}</span> : r.finished_at ? `${r.proposed_notes} note${r.proposed_notes === 1 ? "" : "s"} proposed` : "running"}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

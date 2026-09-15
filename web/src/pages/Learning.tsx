import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Exemplar, Note, Stats } from "../api/types";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";

export function Learning() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [ex, setEx] = useState<Exemplar[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const load = () => Promise.all([api.get<Note[]>("/api/notes"), api.get<Exemplar[]>("/api/exemplars"), api.get<Stats>("/api/stats")]).then(([n, e, s]) => { setNotes(n); setEx(e); setStats(s); });
  useEffect(() => { load(); }, []);
  const approveNote = async (id: number) => { await api.post(`/api/notes/${id}/approve`); load(); };
  const approveEx = async (id: number) => { await api.post(`/api/exemplars/${id}/approve`); load(); };
  return (
    <div className="page">
      <div className="page-header"><div><h1>Learning</h1><p className="meta">What the marker has learned from your corrections. Approve a draft to use it on the next run.</p></div></div>
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
      {notes.length === 0 ? <EmptyState title="No notes yet"><p>Run <code>sms reflect</code> after resolving a few questions to distil notes from your corrections.</p></EmptyState> : (
        <table className="table"><thead><tr><th>Subject</th><th>Note</th><th>Status</th><th /></tr></thead>
          <tbody>{notes.map((n) => <tr key={n.id}><td>{n.subject}</td><td>{n.note}</td><td><span className={`pill ${n.status === "active" ? "pill-ink" : "pill-outline"}`}>{n.status === "active" ? "Active" : "Draft"}</span></td><td>{n.status !== "active" && <Button size="sm" onClick={() => approveNote(n.id)}>Approve</Button>}</td></tr>)}</tbody>
        </table>
      )}
      <h4 style={{ marginTop: 32 }}>Exemplar cases</h4>
      {ex.length === 0 ? <p className="muted">None yet.</p> : (
        <table className="table"><thead><tr><th>Topic</th><th>Answer</th><th className="num">Marks</th><th>Why it matters</th><th>Status</th><th /></tr></thead>
          <tbody>{ex.map((e) => <tr key={e.id}><td>{e.subject} / {e.topic}</td><td>{e.answer_text}</td><td className="num">{e.awarded} / {e.max_score}</td><td className="help">{e.why_it_matters}</td><td><span className={`pill ${e.status === "active" ? "pill-ink" : "pill-outline"}`}>{e.status === "active" ? "Active" : "Draft"}</span></td><td>{e.status !== "active" && <Button size="sm" onClick={() => approveEx(e.id)}>Approve</Button>}</td></tr>)}</tbody>
        </table>
      )}
    </div>
  );
}

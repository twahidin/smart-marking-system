import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Exemplar, Note, ReflectionRuns, Stats, Subject } from "../api/types";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { fmtDate, SUBJECTS, subjectColor, subjectLabel } from "../lib/format";
import { ART, FILM } from "../scene/art";
import { Book, Glow, Star } from "../scene/effects";
import { Scene, type Cue, type Hotspot } from "../scene/Scene";
import { useDeviceTier } from "../scene/useDeviceTier";

export function Learning() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [ex, setEx] = useState<Exemplar[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [runs, setRuns] = useState<ReflectionRuns>({ runs: [], pending: [] });
  const [subject, setSubject] = useState<Subject>("math");
  const [queued, setQueued] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterOn, setFilterOn] = useState(false);
  const [cue, setCue] = useState<Cue | null>(null);
  const tier = useDeviceTier();
  const play = (name: string) => setCue((c) => ({ name, key: (c?.key ?? 0) + 1 }));
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
    try { await api.post(`/api/notes/${id}/approve`); await load(); play("shelve"); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load"); }
  };
  const approveEx = async (id: number) => {
    try { await api.post(`/api/exemplars/${id}/approve`); await load(); play("shelve"); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load"); }
  };
  const pendingHere = runs.pending.includes(subject);
  // A running job already has an open run row (finished_at null) in the list; only show the rest as queued.
  const queuedOnly = runs.pending.filter((s) => !runs.runs.some((r) => r.subject === s && r.finished_at === null));
  /** Shelf positions per subject, in SUBJECTS order, on the library painting. */
  const SHELF = [{ left: "34%", top: "40%" }, { left: "43%", top: "30%" }, { left: "57%", top: "30%" }, { left: "38%", top: "34%" }, { left: "52%", top: "24%" }];
  const active = notes.filter((n) => n.status === "active");
  const drafts = notes.filter((n) => n.status !== "active").length + ex.filter((e) => e.status !== "active").length;
  const marked = stats?.marker?.count ?? 0;
  const hotspots: Hotspot[] = [
    ...SUBJECTS.map((s, i) => {
      const r = active.filter((n) => n.subject === s).length; const x = ex.filter((e) => e.subject === s).length;
      return { id: `shelf-${s}`, ...SHELF[i], color: subjectColor[s], label: `${subjectLabel[s]} shelf · ${r} ruling${r === 1 ? "" : "s"}`, sub: `${x} example${x === 1 ? "" : "s"}`, onPick: () => { setSubject(s); setFilterOn(true); } };
    }),
    { id: "table", left: "47%", top: "57%", color: "var(--gold)", label: `Reading table · ${drafts} draft${drafts === 1 ? "" : "s"}`, sub: "Approve to use them on the next run", onPick: () => document.getElementById("rubric-notes")?.scrollIntoView?.({ behavior: "smooth" }) },
    { id: "board", left: "73%", top: "31%", color: "var(--mint)", label: `Notice board · ${ex.length} example${ex.length === 1 ? "" : "s"}`, sub: "Answers you marked by hand, with why they matter", onPick: () => document.getElementById("exemplars")?.scrollIntoView?.({ behavior: "smooth" }) },
    { id: "trophy", left: "50%", top: "12%", label: "Trophy", sub: `${marked} script${marked === 1 ? "" : "s"} marked so far`, onPick: () => {} },
  ];
  const effects = <>
    {drafts > 0 && <Glow left="50.5%" top="54%" size="14%" />}
    <Star left="48%" top="17%" /><Star left="52.5%" top="21%" delay={0.8} />
    <Book left="43.5%" top="38%" color={subjectColor[subject]} />
  </>;
  const shownNotes = filterOn ? notes.filter((n) => n.subject === subject) : notes;
  const shownEx = filterOn ? ex.filter((e) => e.subject === subject) : ex;
  return (
    <div className="page">
      <div className="page-header">
        <div><h1>The library</h1><p className="meta">What the Marker has learned from your corrections, shelved by subject. Drafts wait on the reading table until you approve them; the notice board keeps the worked examples.</p></div>
        <div className="actions" style={{ alignItems: "center", flexWrap: "nowrap" }}>
          <span className="pill pill-outline tabular">{active.length} active ruling{active.length === 1 ? "" : "s"} · {ex.length} example{ex.length === 1 ? "" : "s"}</span>
          <span className="pill tabular" style={{ background: "var(--butter)" }}>{drafts} draft{drafts === 1 ? "" : "s"} to approve</span>
          <select className="input" aria-label="Subject" style={{ width: "auto" }} value={subject} onChange={(e) => setSubject(e.target.value as Subject)}>
            {SUBJECTS.map((s) => <option key={s} value={s}>{subjectLabel[s]}</option>)}
          </select>
          <Button variant="primary" onClick={runReflection} disabled={busy || pendingHere}>{pendingHere ? "Reflection queued…" : busy ? "Starting…" : "Run reflection"}</Button>
        </div>
      </div>
      {error && <div style={{ marginBottom: 16 }}><Notice kind="error">{error}</Notice></div>}
      {queued && !error && <div style={{ marginBottom: 16 }}><Notice kind="ok">Reflection queued — notes appear below when it finishes.</Notice></div>}
      <Scene name="The library" art={ART.library} film={FILM.library} alt="A library nook with bookshelves, a reading table with an open book, a notice board, a beanbag and a trophy" hotspots={hotspots} effects={effects} cue={cue} tier={tier} />
      {filterOn && <div className="actions" style={{ margin: "12px 0" }}><button type="button" className="btn btn-sm btn-secondary" onClick={() => setFilterOn(false)}>{`Showing ${subjectLabel[subject]} · Show all`}</button></div>}
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
      <h4 id="rubric-notes">Rubric notes</h4>
      {error ? null : notes.length === 0 ? <EmptyState title="No notes yet."><p>Resolve a few questions in Review, then run reflection (or leave it to run nightly).</p></EmptyState> : (
        <table className="table"><thead><tr><th>Subject</th><th>Note</th><th>Status</th><th /></tr></thead>
          <tbody>{shownNotes.map((n) => <tr key={n.id}><td><i className="dot" style={{ background: subjectColor[n.subject as Subject] ?? "var(--oak)", marginRight: 6 }} aria-hidden />{n.subject}</td><td>{n.note}</td><td><span className={`pill ${n.status === "active" ? "pill-ink" : "pill-outline"}`}>{n.status === "active" ? "Active" : "Draft"}</span></td><td>{n.status !== "active" && <Button size="sm" onClick={() => approveNote(n.id)}>Approve</Button>}</td></tr>)}</tbody>
        </table>
      )}
      <h4 id="exemplars" style={{ marginTop: 32 }}>Exemplar cases</h4>
      {error ? null : ex.length === 0 ? <p className="muted">None yet.</p> : (
        <table className="table"><thead><tr><th>Topic</th><th>Answer</th><th className="num">Marks</th><th>Why it matters</th><th>Status</th><th /></tr></thead>
          <tbody>{shownEx.map((e) => <tr key={e.id}><td><i className="dot" style={{ background: subjectColor[e.subject as Subject] ?? "var(--oak)", marginRight: 6 }} aria-hidden />{e.subject} / {e.topic}</td><td>{e.answer_text}</td><td className="num">{e.awarded} / {e.max_score}</td><td className="help">{e.why_it_matters}</td><td><span className={`pill ${e.status === "active" ? "pill-ink" : "pill-outline"}`}>{e.status === "active" ? "Active" : "Draft"}</span></td><td>{e.status !== "active" && <Button size="sm" onClick={() => approveEx(e.id)}>Approve</Button>}</td></tr>)}</tbody>
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

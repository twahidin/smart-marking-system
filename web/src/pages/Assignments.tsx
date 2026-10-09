import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { AssignmentTemplate, DueClassAssignment, RoomSnapshot, Subject } from "../api/types";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { saveBlob } from "../lib/download";
import { fmtDate, providerLabel, schemeLabel, SUBJECTS, subjectColor, subjectLabel } from "../lib/format";
import { ART, FILM } from "../scene/art";
import { Glow, Paper } from "../scene/effects";
import { Scene, type Hotspot } from "../scene/Scene";
import { useDeviceTier } from "../scene/useDeviceTier";

type Pending = { kind: "rename"; t: AssignmentTemplate; title: string } | { kind: "delete"; t: AssignmentTemplate };

/** Deleting needs `?force=true` (and a "Delete anyway" confirmation) once scripts or class assignments reference the template. */
const inUse = (t: AssignmentTemplate) => (t.submission_count ?? 0) > 0 || (t.class_assignment_count ?? 0) > 0;

export function Assignments() {
  const nav = useNavigate();
  const [rows, setRows] = useState<AssignmentTemplate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState<Subject | null>(null);
  const [due, setDue] = useState<DueClassAssignment[]>([]);
  const [marking, setMarking] = useState(0);
  const tier = useDeviceTier();
  useEffect(() => {
    // Both are decoration for the scene: a failure leaves the desk quiet and the page says nothing.
    api.get<DueClassAssignment[]>("/api/class-assignments/due?days=7").then(setDue).catch(() => {});
    api.get<RoomSnapshot>("/api/room").then((s) => setMarking(s.counts.read + s.counts.mark + s.counts.check + s.counts.queued)).catch(() => {});
  }, []);

  const load = () => api.get<AssignmentTemplate[]>("/api/assignments").then((r) => { setRows(r); setError(null); }).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load"));
  useEffect(() => { load(); }, []);

  const run = async (fn: () => Promise<unknown>, done?: string) => {
    setBusy(true); setError(null); setOk(null);
    try { await fn(); await load(); if (done) setOk(done); setPending(null); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Something went wrong — try again."); }
    finally { setBusy(false); }
  };

  // The PUT is the whole template: the model fields go with it, or a rename would silently reset a chosen model to Auto.
  const body = (t: AssignmentTemplate, title: string) => ({ title, subject: t.subject, context: t.context, rubric: t.rubric, scheme_kind: t.scheme_kind, questions: t.questions, scheme: t.scheme, delete_pages_after_marking: t.delete_pages_after_marking, provider: t.provider, model: t.model, extractor_model: t.extractor_model });
  const duplicate = (t: AssignmentTemplate) => run(() => api.post(`/api/assignments/${t.id}/duplicate`));
  const rename = (t: AssignmentTemplate, title: string) => run(() => api.put(`/api/assignments/${t.id}`, body(t, title)));
  const remove = (t: AssignmentTemplate) => run(() => api.delete(`/api/assignments/${t.id}${inUse(t) ? "?force=true" : ""}`));

  const importJson = (f: File) => run(async () => {
    let payload: unknown;
    try { payload = JSON.parse(await f.text()); } catch { throw new ApiError(400, "bad_json", `${f.name} is not valid JSON.`); }
    const r = await api.post<{ created: number }>("/api/assignments/import", payload);
    setOk(`Imported ${r.created} assignment${r.created === 1 ? "" : "s"}`);
  });
  const exportJson = async () => {
    setError(null);
    try {
      const data = await api.get<unknown>("/api/assignments/export");
      saveBlob(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }), "assignments.json");
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not export"); }
  };

  /** Rack slots, left to right along the folder rack in the painting. */
  const RACK = [{ left: "57%", top: "36%" }, { left: "61%", top: "39%" }, { left: "65%", top: "42%" }, { left: "69%", top: "45%" }, { left: "73%", top: "48%" }];
  const bySubject = SUBJECTS.filter((s) => (rows ?? []).some((t) => t.subject === s));
  const hotspots: Hotspot[] = [
    ...bySubject.map((s, i) => {
      const titles = (rows ?? []).filter((t) => t.subject === s);
      return { id: `rack-${s}`, ...RACK[i], color: subjectColor[s], label: `${subjectLabel[s]} · ${titles.length} folder${titles.length === 1 ? "" : "s"}`,
        sub: titles.slice(0, 2).map((t) => t.title).join(" · "), onPick: () => setFilter((f) => (f === s ? null : s)) };
    }),
    { id: "pad", left: "46%", top: "46%", label: "Blank pad", sub: "Start a new assignment", href: "/assignments/new" },
    ...(due.length > 0
      ? [{ id: "pinboard", left: "37%", top: "22%", label: "Pinboard · due this week", sub: due.slice(0, 3).map((d) => `${d.class_name} · ${d.title} · ${fmtDate(d.due_at)}`).join(" · "), href: `/classes/${due[0].class_id}/assignments/${due[0].id}` }]
      : [{ id: "pinboard", left: "37%", top: "22%", label: "Pinboard", sub: "Nothing due this week", onPick: () => {} }]),
    { id: "lamp", left: "36%", top: "44%", label: marking > 0 ? `Marking now · ${marking} script${marking === 1 ? "" : "s"}` : "Lamp", sub: marking > 0 ? "On the desks in the Marking Room" : "Lights up while scripts are being marked", href: "/room" },
  ];
  const effects = <>
    {marking > 0 && <Glow left="37%" top="46%" size="16%" />}
    {due.length > 0 && <Paper left="36%" top="24%" />}
  </>;
  const shown = (rows ?? []).filter((t) => !filter || t.subject === filter);

  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Your desk</h1><p className="meta">Papers, mark schemes and rubrics you have saved, filed by subject. Pull a folder to edit it or set it for a class; the blank pad starts a new one.</p></div>
        <div className="actions">
          {rows && <span className="pill pill-outline tabular">{rows.length} folder{rows.length === 1 ? "" : "s"} · {rows.reduce((n, t) => n + (t.class_assignment_count ?? 0), 0)} class sets</span>}
          <Button variant="primary" onClick={() => nav("/assignments/new")}>+ New assignment</Button>
          <Button variant="secondary" onClick={() => fileRef.current?.click()} disabled={busy}>Import JSON</Button>
          <input ref={fileRef} type="file" accept=".json,application/json" hidden aria-label="Import assignments JSON" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importJson(f); }} />
          <Button variant="secondary" onClick={exportJson} disabled={busy || !rows?.length}>Export JSON</Button>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {ok && <Notice kind="ok">{ok}</Notice>}
      <Scene name="The teacher's desk" art={ART.desk} film={FILM.desk} alt="A wooden teacher's desk with a lamp, a stack of worksheets, a rack of coloured folders and a pinboard" hotspots={hotspots} effects={effects} tier={tier} />
      {filter && <div className="actions" style={{ marginTop: 12 }}><button type="button" className="btn btn-sm btn-secondary" onClick={() => setFilter(null)}>{`Showing ${subjectLabel[filter]} · Show all`}</button></div>}
      {rows && rows.length === 0 && <EmptyState title="No saved assignments yet."><p className="help">Start with + New assignment, or save one from Mark a script.</p></EmptyState>}
      {rows && rows.length > 0 && (
        <table className="table tall">
          <thead><tr><th>Title</th><th>Subject</th><th>Scheme</th><th className="num">Criteria</th><th className="num">Marks</th><th className="num">Times used</th><th>Updated</th><th /></tr></thead>
          <tbody>
            {shown.map((t) => (
              <tr key={t.id} className="row-link" onClick={() => nav(`/assignments/${t.id}`)}>
                <td style={{ borderLeft: `6px solid ${subjectColor[t.subject]}` }}><strong>{t.title}</strong>{t.context && <div className="help">{t.context}</div>}
                  {t.provider && <div className="help">{providerLabel[t.provider] ?? t.provider} · {t.model}</div>}</td>
                <td>{subjectLabel[t.subject]}</td>
                <td>{schemeLabel[t.scheme_kind] ?? t.scheme_kind}{t.paper_page_ids.length > 0 && <div className="help">Paper: {t.paper_page_ids.length} page{t.paper_page_ids.length === 1 ? "" : "s"}</div>}{t.scheme_kind !== "criteria" && t.scheme.length === 0 && <div className="warn-note">Draft — no {t.scheme_kind === "rubric" ? "rubric" : "scheme"} yet</div>}</td>
                <td className="num">{t.criteria_count}</td>
                <td className="num">{t.total_marks}</td>
                <td className="num">{t.times_used}</td>
                <td className="muted">{fmtDate(t.updated_at)}</td>
                <td>
                  <div className="actions" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }} onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" size="sm" onClick={() => setPending({ kind: "rename", t, title: t.title })}>Rename</Button>
                    <Button variant="ghost" size="sm" onClick={() => duplicate(t)} disabled={busy}>Duplicate</Button>
                    <Button variant="ghost" size="sm" onClick={() => setPending({ kind: "delete", t })}>Delete</Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {pending?.kind === "rename" && (
        <Dialog title="Rename assignment" onClose={() => setPending(null)}
          footer={<><Button variant="secondary" onClick={() => setPending(null)}>Cancel</Button><Button variant="primary" onClick={() => rename(pending.t, pending.title)} disabled={busy || !pending.title.trim()}>Save</Button></>}>
          <div className="field"><label htmlFor="rename-title">Title</label>
            <input id="rename-title" className="input" autoFocus value={pending.title} onChange={(e) => setPending({ ...pending, title: e.target.value })}
              onKeyDown={(e) => { if (e.key === "Enter" && pending.title.trim()) rename(pending.t, pending.title); }} /></div>
        </Dialog>
      )}
      {pending?.kind === "delete" && (
        <Dialog title="Delete this assignment?" onClose={() => setPending(null)}
          footer={<><Button variant="secondary" onClick={() => setPending(null)}>Cancel</Button><Button variant="primary" onClick={() => remove(pending.t)} disabled={busy}>{inUse(pending.t) ? "Delete anyway" : "Delete assignment"}</Button></>}>
          <DeleteWarning t={pending.t} />
        </Dialog>
      )}
    </div>
  );
}

function DeleteWarning({ t }: { t: AssignmentTemplate }) {
  const n = t.submission_count ?? 0;
  const pending = t.pending_count ?? 0;
  const classes = t.class_assignment_count ?? 0;
  if (!inUse(t)) return <p><strong>{t.title}</strong> will be removed from the bank.</p>;
  return (
    <>
      {n > 0 && (
        <>
          <p><strong>{t.title}</strong> is referenced by <strong>{n} script{n === 1 ? "" : "s"}</strong>.</p>
          <p>Marked scripts keep their marks and their marking records.{pending > 0 && <> <strong>{pending}</strong> {pending === 1 ? "has" : "have"} not been marked yet — {pending === 1 ? "it" : "they"} will fail with "assignment deleted" and must be uploaded again against a current assignment.</>}</p>
        </>
      )}
      {classes > 0 && (
        <p>{n === 0 && <><strong>{t.title}</strong> </>}{n === 0 ? "is" : "It is"} set in <strong>{classes} class{classes === 1 ? "" : "es"}</strong>; those class assignments will need to be set again.</p>
      )}
    </>
  );
}

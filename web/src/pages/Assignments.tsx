import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { AssignmentTemplate } from "../api/types";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { saveBlob } from "../lib/download";
import { fmtDate, schemeLabel, subjectLabel } from "../lib/format";

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

  const load = () => api.get<AssignmentTemplate[]>("/api/assignments").then((r) => { setRows(r); setError(null); }).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load"));
  useEffect(() => { load(); }, []);

  const run = async (fn: () => Promise<unknown>, done?: string) => {
    setBusy(true); setError(null); setOk(null);
    try { await fn(); await load(); if (done) setOk(done); setPending(null); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Something went wrong — try again."); }
    finally { setBusy(false); }
  };

  const body = (t: AssignmentTemplate, title: string) => ({ title, subject: t.subject, context: t.context, rubric: t.rubric, scheme_kind: t.scheme_kind, questions: t.questions, scheme: t.scheme, delete_pages_after_marking: t.delete_pages_after_marking });
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

  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Assignments</h1><p className="meta">Papers, mark schemes and rubrics you have saved. Pick one under Mark a script instead of typing it again.</p></div>
        <div className="actions">
          <Button variant="primary" onClick={() => nav("/assignments/new")}>+ New assignment</Button>
          <Button variant="secondary" onClick={() => fileRef.current?.click()} disabled={busy}>Import JSON</Button>
          <input ref={fileRef} type="file" accept=".json,application/json" hidden aria-label="Import assignments JSON" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importJson(f); }} />
          <Button variant="secondary" onClick={exportJson} disabled={busy || !rows?.length}>Export JSON</Button>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {ok && <Notice kind="ok">{ok}</Notice>}
      {rows && rows.length === 0 && <EmptyState title="No saved assignments yet."><p className="help">Start with + New assignment, or save one from Mark a script.</p></EmptyState>}
      {rows && rows.length > 0 && (
        <table className="table tall">
          <thead><tr><th>Title</th><th>Subject</th><th>Scheme</th><th className="num">Criteria</th><th className="num">Marks</th><th className="num">Times used</th><th>Updated</th><th /></tr></thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id} className="row-link" onClick={() => nav(`/assignments/${t.id}`)}>
                <td><strong>{t.title}</strong>{t.context && <div className="help">{t.context}</div>}</td>
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

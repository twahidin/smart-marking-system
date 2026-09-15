import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AssignmentTemplate } from "../api/types";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { fmtDate, schemeLabel, subjectLabel } from "../lib/format";

type Pending = { kind: "rename"; t: AssignmentTemplate; title: string } | { kind: "delete"; t: AssignmentTemplate };

export function Assignments() {
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

  const body = (t: AssignmentTemplate, title: string) => ({ title, subject: t.subject, context: t.context, rubric: t.rubric, scheme_kind: t.scheme_kind, questions: t.questions, scheme: t.scheme });
  const duplicate = (t: AssignmentTemplate) => run(() => api.post(`/api/assignments/${t.id}/duplicate`));
  const rename = (t: AssignmentTemplate, title: string) => run(() => api.put(`/api/assignments/${t.id}`, body(t, title)));
  const remove = (t: AssignmentTemplate) => run(() => api.delete(`/api/assignments/${t.id}`));

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
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a"); a.href = url; a.download = "assignments.json"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not export"); }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Assignments</h1><p className="meta">Rubrics you have saved. Pick one under Mark a script instead of typing it again.</p></div>
        <div className="actions">
          <Button variant="secondary" onClick={() => fileRef.current?.click()} disabled={busy}>Import JSON</Button>
          <input ref={fileRef} type="file" accept=".json,application/json" hidden aria-label="Import assignments JSON" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importJson(f); }} />
          <Button variant="secondary" onClick={exportJson} disabled={busy || !rows?.length}>Export JSON</Button>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {ok && <Notice kind="ok">{ok}</Notice>}
      {rows && rows.length === 0 && <EmptyState title="No saved assignments yet — save one from Mark a script." />}
      {rows && rows.length > 0 && (
        <table className="table tall">
          <thead><tr><th>Title</th><th>Subject</th><th>Scheme</th><th className="num">Criteria</th><th className="num">Marks</th><th className="num">Times used</th><th>Updated</th><th /></tr></thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id}>
                <td><strong>{t.title}</strong>{t.context && <div className="help">{t.context}</div>}</td>
                <td>{subjectLabel[t.subject]}</td>
                <td>{schemeLabel[t.scheme_kind] ?? t.scheme_kind}{t.paper_page_ids.length > 0 && <div className="help">Paper: {t.paper_page_ids.length} page{t.paper_page_ids.length === 1 ? "" : "s"}</div>}</td>
                <td className="num">{t.criteria_count}</td>
                <td className="num">{t.total_marks}</td>
                <td className="num">{t.times_used}</td>
                <td className="muted">{fmtDate(t.updated_at)}</td>
                <td>
                  <div className="actions" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
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
          footer={<><Button variant="secondary" onClick={() => setPending(null)}>Cancel</Button><Button variant="primary" onClick={() => remove(pending.t)} disabled={busy}>Delete assignment</Button></>}>
          <p><strong>{pending.t.title}</strong> will be removed from the bank. Scripts already marked with it keep their marks.</p>
        </Dialog>
      )}
    </div>
  );
}

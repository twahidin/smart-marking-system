import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { AssignmentTemplate, Settings } from "../api/types";
import { Button } from "../components/Button";
import { DropZone, PAGE_ACCEPT } from "../components/DropZone";
import { Notice } from "../components/Notice";
import { expandZips, groupScripts, uploadScripts, type Outcome, type Script } from "../lib/bulk";
import { MAX_TEACHER_PAGES, PROGRAM_ACCEPT } from "../lib/files";
import { subjectLabel } from "../lib/format";

type Progress = { done: number; total: number };

/** Many students' scripts against one saved assignment: drop files or a zip, check the labels, start them all. */
export function BulkMark() {
  const nav = useNavigate();
  const [templates, setTemplates] = useState<AssignmentTemplate[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [assignmentId, setAssignmentId] = useState<number | null>(null);
  const [scripts, setScripts] = useState<Script[]>([]);
  const [outcomes, setOutcomes] = useState<Record<number, Outcome>>({});
  const [progress, setProgress] = useState<Progress | null>(null);
  const [unpacking, setUnpacking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.get<Settings>("/api/settings").then(setSettings).catch(() => setSettings(null)); }, []);
  useEffect(() => { api.get<AssignmentTemplate[]>("/api/assignments").then(setTemplates).catch(() => setTemplates([])); }, []);

  const chosen = useMemo(() => templates.find((t) => t.id === assignmentId) ?? null, [templates, assignmentId]);
  const schemed = !!chosen && (chosen.scheme_kind === "mark_scheme" || chosen.scheme_kind === "rubric");
  const accept = `${PAGE_ACCEPT},.zip${chosen?.subject === "computing" ? `,${PROGRAM_ACCEPT}` : ""}`;
  const busy = progress !== null;
  const failed = scripts.map((_, i) => i).filter((i) => outcomes[i] && !outcomes[i].ok);
  const succeeded = Object.values(outcomes).filter((o) => o.ok).length;

  const add = async (files: File[]) => {
    setError(null); setUnpacking(true);
    try { const expanded = await expandZips(files); setScripts((prev) => groupScripts(expanded, prev)); }
    catch { setError("Could not open that zip — check it is a plain zip of PDFs or photos."); }
    finally { setUnpacking(false); }
  };
  const relabel = (i: number, label: string) => setScripts((prev) => prev.map((s, k) => (k === i ? { ...s, label } : s)));
  const remove = (i: number) => { setScripts((prev) => prev.filter((_, k) => k !== i)); setOutcomes({}); };

  const problem = useMemo(() => {
    if (!chosen) return "Choose the assignment these scripts answer.";
    if (schemed && chosen.scheme.length === 0) return `${chosen.title} has no ${chosen.scheme_kind === "rubric" ? "rubric" : "mark scheme"} yet — finish it under Assignments.`;
    if (scripts.length === 0) return "Drop the scripts first.";
    const labels = scripts.map((s) => s.label.trim().toLowerCase());
    if (labels.some((l) => !l)) return "Every script needs a label.";
    if (new Set(labels).size !== labels.length) return "Two scripts share a label — make them different.";
    const big = scripts.find((s) => s.files.length > MAX_TEACHER_PAGES);
    if (big) return `${big.label} has ${big.files.length} pages; the most one script can carry is ${MAX_TEACHER_PAGES}.`;
    return null;
  }, [chosen, schemed, scripts]);

  const start = async (only?: number[]) => {
    if (!chosen) return;
    const indexes = only ?? scripts.map((_, i) => i);
    setError(null); setProgress({ done: 0, total: indexes.length });
    if (!only) setOutcomes({});
    const fields = { assignment_id: chosen.id, subject: chosen.subject, context: chosen.context, rubric: JSON.stringify(chosen.rubric) };
    const merged: Record<number, Outcome> = only ? { ...outcomes } : {};
    await uploadScripts(indexes.map((i) => scripts[i]), fields, (fd) => api.postForm<{ id: number }>("/api/submissions", fd),
      (k, outcome) => { merged[indexes[k]] = outcome; setOutcomes({ ...merged }); setProgress((p) => (p ? { ...p, done: p.done + 1 } : p)); });
    setProgress(null);
    if (scripts.every((_, i) => merged[i]?.ok)) nav("/submissions");
  };

  return (
    <div className="page">
      <div className="page-header"><div><h1>Mark many scripts</h1><p className="meta">A whole class against one saved assignment. One PDF per student, or photos named after the student with a page number.</p></div></div>
      {error && <Notice kind="error">{error}</Notice>}
      {settings && !settings.has_key && <Notice>Add an API key under <Link to="/settings">Settings</Link> before marking.</Notice>}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="field"><label htmlFor="bulk-assignment">Assignment</label>
          <select id="bulk-assignment" className="input" value={assignmentId ?? ""} disabled={busy} onChange={(e) => setAssignmentId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Choose…</option>
            {templates.map((t) => <option key={t.id} value={t.id}>{t.title} · {subjectLabel[t.subject] ?? t.subject}</option>)}
          </select>
          <span className="help">Every script is marked against this assignment's {chosen?.scheme_kind === "rubric" ? "rubric" : chosen?.scheme_kind === "mark_scheme" ? "mark scheme" : "criteria"}. Manage them under <Link to="/assignments">Assignments</Link>.</span>
        </div>
      </div>
      <div className="card" style={{ marginBottom: 16 }}>
        <DropZone onFiles={add} accept={accept} title={unpacking ? "Unpacking…" : "Feed the sorter — the whole class"}
          hint="PDFs, JPG, PNG or HEIC, or one zip of them. A PDF is one script; photos named “Tan Wei Ling-1.jpg”, “Tan Wei Ling-2.jpg” become one script in page order." />
      </div>
      {scripts.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <table className="table" aria-label="Scripts to mark">
            <thead><tr><th>Label</th><th>Pages</th><th>Files</th><th aria-label="Result" /></tr></thead>
            <tbody>
              {scripts.map((s, i) => {
                const o = outcomes[i];
                return (
                  <tr key={i}>
                    <td><input className="input" aria-label={`Label for script ${i + 1}`} value={s.label} disabled={busy || o?.ok === true} onChange={(e) => relabel(i, e.target.value)} /></td>
                    <td>{s.files.length}</td>
                    <td className="meta" title={s.files.map((f) => f.name).join("\n")}>{s.files.length === 1 ? s.files[0].name.slice(s.files[0].name.lastIndexOf("/") + 1) : `${s.files[0].name.slice(s.files[0].name.lastIndexOf("/") + 1)} …`}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {o?.ok === true ? <span className="pill pill-outline">Queued</span>
                        : o ? <span className="pill pill-failed" title={o.error}>Failed · {o.error}</span>
                        : !busy && <Button size="sm" variant="ghost" onClick={() => remove(i)}>Remove</Button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="actions">
        {failed.length > 0 && !busy
          ? <Button variant="primary" size="lg" onClick={() => start(failed)}>Retry {failed.length} failed</Button>
          : <Button variant="primary" size="lg" onClick={() => start()} disabled={busy || !!problem || !settings?.has_key || unpacking} title={problem ?? undefined}>
              {progress ? `Uploading ${progress.done} of ${progress.total}…` : `Start marking ${scripts.length} script${scripts.length === 1 ? "" : "s"}`}
            </Button>}
        <Button variant="ghost" size="lg" onClick={() => nav("/submissions")} disabled={busy}>{succeeded > 0 ? "Back to submissions" : "Cancel"}</Button>
        {failed.length > 0 && !busy && <span className="meta">{succeeded} queued, {failed.length} failed. Fix the label or the file and retry.</span>}
      </div>
    </div>
  );
}

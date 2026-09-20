import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { AssignmentTemplate, RubricBands, Settings, Subject } from "../api/types";
import { Button } from "../components/Button";
import { CriteriaEditor } from "../components/CriteriaTable";
import { Dialog } from "../components/Dialog";
import { DropZone, PAGE_ACCEPT } from "../components/DropZone";
import { Notice } from "../components/Notice";
import { PageCard } from "../components/PageCard";
import { canThumbnail, PROGRAM_ACCEPT, prepareUploads } from "../lib/files";
import { subjectLabel } from "../lib/format";
import { qLabel, schemeTotal } from "../lib/scheme";
import { emptyRow, jsonToRows, rowsToRubricJson, validateRows, type Row } from "../lib/rubric";

type Picked = { file: File; url: string };

/** "5 questions · 25 marks · mark scheme" / "3 criteria · 15 marks · rubric". */
export function schemeSummary(t: AssignmentTemplate): string {
  const marks = schemeTotal(t.scheme_kind, t.questions, t.scheme);
  if (t.scheme_kind === "rubric") return `${t.scheme.length} criteri${t.scheme.length === 1 ? "on" : "a"} · ${marks} marks · rubric`;
  return `${t.questions.length} question${t.questions.length === 1 ? "" : "s"} · ${marks} marks · mark scheme`;
}

export function NewSubmission() {
  const nav = useNavigate();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [label, setLabel] = useState("");
  const [subject, setSubject] = useState<Subject>("math");
  const [context, setContext] = useState("");
  const [rows, setRows] = useState<Row[]>([{ ...emptyRow(), id: "c1", description: "Correct method", max_score: 2 }, { ...emptyRow(), id: "c2", description: "Correct final answer", max_score: 3 }]);
  const [files, setFiles] = useState<Picked[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [templates, setTemplates] = useState<AssignmentTemplate[]>([]);
  const [assignmentId, setAssignmentId] = useState<number | null>(null);
  const [saveTitle, setSaveTitle] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedNotice, setSavedNotice] = useState(false);

  useEffect(() => { api.get<Settings>("/api/settings").then(setSettings).catch(() => setSettings(null)); }, []);
  useEffect(() => { api.get<AssignmentTemplate[]>("/api/assignments").then(setTemplates).catch(() => setTemplates([])); }, []);

  // Fills the assignment half of the form; the label is the student's and is left alone.
  const chosen = useMemo(() => templates.find((t) => t.id === assignmentId) ?? null, [templates, assignmentId]);
  // A mark-scheme / rubric assignment is marked part by part against its saved scheme, so the criteria editor is
  // replaced by a read-only summary; Quick mark (no assignment, or a criteria one) keeps the editor.
  const schemed = !!chosen && (chosen.scheme_kind === "mark_scheme" || chosen.scheme_kind === "rubric");
  // Program files are only marked against a Computing assignment's scheme, so the drop zone offers
  // them only once one is chosen — a quick mark has no scheme for the marker to read them against.
  const takesFiles = chosen?.subject === "computing";
  const rubricJson = () => (schemed ? JSON.stringify(chosen!.rubric) : rowsToRubricJson(rows));
  const useTemplate = (id: string) => {
    const t = templates.find((x) => String(x.id) === id);
    setAssignmentId(t ? t.id : null);
    if (!t) return;
    setSubject(t.subject); setContext(t.context); setRows(jsonToRows(JSON.stringify(t.rubric))); setError(null);
  };
  const saveAsAssignment = async () => {
    if (saveTitle === null || !saveTitle.trim()) return;
    setSaving(true); setError(null);
    try {
      const t = await api.post<AssignmentTemplate>("/api/assignments", { title: saveTitle.trim(), subject, context: context.trim(), rubric: JSON.parse(rowsToRubricJson(rows)) });
      setTemplates((cur) => [t, ...cur]); setAssignmentId(t.id); setSaveTitle(null); setSavedNotice(true);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not save the assignment."); }
    finally { setSaving(false); }
  };
  const filesRef = useRef<Picked[]>([]);
  filesRef.current = files;
  // Revoke object URLs only when the page unmounts — revoking on every change would blank the remaining thumbnails.
  useEffect(() => () => filesRef.current.forEach((f) => f.url && URL.revokeObjectURL(f.url)), []);

  // Photos are shrunk as they are dropped, so the thumbnail and the upload are the same bytes.
  const add = (picked: File[]) => { prepareUploads(picked).then((ready) => setFiles((cur) => [...cur, ...ready.map((file) => ({ file, url: canThumbnail(file) ? URL.createObjectURL(file) : "" }))])); };
  const remove = (i: number) => setFiles((cur) => { cur[i].url && URL.revokeObjectURL(cur[i].url); return cur.filter((_, j) => j !== i); });
  const move = (i: number, d: -1 | 1) => setFiles((cur) => { const c = [...cur]; const j = i + d; if (j < 0 || j >= c.length) return cur; [c[i], c[j]] = [c[j], c[i]]; return c; });
  const uploadJson = (f: File) => f.text().then((t) => { try { setRows(jsonToRows(t)); setError(null); } catch (e: any) { setError(`Rubric JSON: ${e.message}`); } });

  const problem = useMemo(() => {
    if (!label.trim()) return "Give the script a label, e.g. the student’s name.";
    if (schemed) {
      if (chosen!.scheme.length === 0) return `${chosen!.title} has no ${chosen!.scheme_kind === "rubric" ? "rubric" : "mark scheme"} yet — finish it under Assignments.`;
    } else { const v = validateRows(rows); if (v) return v; }
    if (files.length === 0) return "Add at least one page or file.";
    return null;
  }, [label, rows, files, schemed, chosen]);

  const submit = async () => {
    setBusy(true); setError(null);
    const fd = new FormData();
    fd.set("label", label.trim()); fd.set("subject", subject); fd.set("context", context.trim()); fd.set("rubric", rubricJson());
    if (assignmentId !== null) fd.set("assignment_id", String(assignmentId));
    files.forEach((f) => fd.append("files", f.file, f.file.name));
    try { const r = await api.postForm<{ id: number }>("/api/submissions", fd); nav(`/submissions/${r.id}`); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Upload failed — check your connection and try again."); setBusy(false); }
  };

  return (
    <div className="page">
      <Link to="/submissions" className="breadcrumb">← Submissions</Link>
      <div className="page-header"><div><h1>Mark a script</h1><p className="meta">One student’s pages, marked against a saved assignment or your own criteria.</p></div></div>
      {settings && !settings.has_key && <Notice>No API key yet. <Link to="/settings">Add one under Settings</Link> before marking.</Notice>}
      {savedNotice && <Notice kind="ok">Saved to Assignments</Notice>}
      <div className="grid-2" style={{ marginTop: 24 }}>
        <div>
          <div className="field"><label htmlFor="assignment">Use a saved assignment</label>
            <select id="assignment" className="input" value={assignmentId ?? ""} onChange={(e) => useTemplate(e.target.value)}>
              <option value="">— none —</option>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.title} · {subjectLabel[t.subject]}</option>)}
            </select>
            <span className="help">{schemed ? "Marked part by part against its saved scheme." : "Fills the subject, context and rubric below."} Manage them under <Link to="/assignments">Assignments</Link>.</span></div>
          <div className="field"><label htmlFor="label">Label</label><input id="label" className="input" placeholder="Tan Wei Ling · Worksheet 3" value={label} onChange={(e) => setLabel(e.target.value)} /></div>
          <div className="grid-2">
            <div className="field"><label>Subject</label>
              <div className="seg" role="radiogroup" aria-label="Subject">
                {(["math", "language", "science", "mt", "computing"] as Subject[]).map((s) => (
                  <label key={s} className={`seg-opt ${subject === s ? "on" : ""}`}><input type="radio" name="subject" checked={subject === s} onChange={() => setSubject(s)} />{subjectLabel[s]}</label>
                ))}
              </div></div>
            <div className="field"><label htmlFor="ctx">Context (optional)</label><input id="ctx" className="input" placeholder="Sec 4 · Quadratic equations · 5 questions" value={context} onChange={(e) => setContext(e.target.value)} /></div>
          </div>
          {schemed ? (
            <div className="field" aria-label="Assignment questions">
              <label>{chosen!.scheme_kind === "rubric" ? "Rubric" : "Mark scheme"}</label>
              <p className="help" style={{ marginBottom: 4 }}>{schemeSummary(chosen!)}</p>
              {chosen!.questions.length > 0 && (
                <table className="table"><tbody>
                  {chosen!.questions.map((q) => <tr key={q.q_id}><td style={{ width: 56 }}><strong>{qLabel(q.q_id)}</strong></td><td>{q.text}</td><td className="num">{q.max_marks}</td></tr>)}
                </tbody></table>
              )}
              {chosen!.scheme_kind === "rubric" && (
                <ul style={{ margin: "4px 0 0 18px" }}>{(chosen!.scheme as RubricBands[]).map((c) => <li key={c.criterion}>{c.criterion} <span className="help">· {c.bands.length} band{c.bands.length === 1 ? "" : "s"}</span></li>)}</ul>
              )}
            </div>
          ) : (
          <div className="field">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <label>Rubric <span className="help">— applied to every question</span></label>
              <div className="actions" style={{ flexWrap: "nowrap" }}>
                <Button type="button" variant="ghost" size="sm" onClick={() => { setSavedNotice(false); setSaveTitle(context.trim()); }}
                  disabled={!!validateRows(rows) || subject === "mt"}
                  title={subject === "mt" ? "A Mother Tongue assignment needs its language — create it under Assignments." : undefined}>Save as assignment</Button>
                <label className="btn btn-ghost btn-sm" style={{ cursor: "pointer" }}>Upload JSON instead<input type="file" accept=".json,application/json" hidden onChange={(e) => e.target.files?.[0] && uploadJson(e.target.files[0])} /></label>
              </div>
            </div>
            {chosen && chosen.questions.length > 0 && (
              <div style={{ marginBottom: 12 }} aria-label="Assignment questions">
                <p className="help" style={{ marginBottom: 4 }}>{chosen.questions.length} question{chosen.questions.length === 1 ? "" : "s"} · {chosen.questions.reduce((s, q) => s + q.max_marks, 0)} marks</p>
                <table className="table"><tbody>
                  {chosen.questions.map((q) => <tr key={q.q_id}><td style={{ width: 56 }}><strong>{qLabel(q.q_id)}</strong></td><td>{q.text}</td><td className="num">{q.max_marks}</td></tr>)}
                </tbody></table>
              </div>
            )}
            <CriteriaEditor rows={rows} onChange={setRows} />
          </div>
          )}
        </div>
        <div>
          <DropZone onFiles={add} title={takesFiles ? "Drop pages or files here" : undefined}
            hint={takesFiles ? "PDF, JPG, PNG or HEIC, and .py, .sb3, .xlsx or .zip — up to 50 MB" : undefined}
            accept={takesFiles ? `${PAGE_ACCEPT},${PROGRAM_ACCEPT}` : PAGE_ACCEPT} />
          {files.length > 0 && (
            <>
              <p className="help" style={{ marginTop: 12 }}>{files.length} file{files.length > 1 ? "s" : ""} · pages are read in this order. PDFs are split into pages.</p>
              <div className="pg-grid">
                {files.map((f, i) => f.url
                  ? <PageCard key={i} src={f.url} index={i} onRemove={() => remove(i)} onMoveLeft={i > 0 ? () => move(i, -1) : undefined} onMoveRight={i < files.length - 1 ? () => move(i, 1) : undefined} />
                  : <div key={i} className="pg"><div className="page-view" style={{ height: 116, padding: 12, fontSize: 13 }}>{f.file.name}</div><span className="tag-n">{i + 1}</span><div className="pg-actions"><button type="button" className="btn btn-ghost btn-sm" onClick={() => remove(i)}>Delete</button></div></div>)}
              </div>
            </>
          )}
        </div>
      </div>
      {error && <div style={{ marginTop: 16 }}><Notice kind="error">{error}</Notice></div>}
      <hr className="rule-2" style={{ marginTop: 24 }} />
      <div className="actions" style={{ marginTop: 16, alignItems: "center" }}>
        <Button variant="primary" size="lg" onClick={submit} disabled={busy || !!problem || !settings?.has_key} title={problem ?? undefined}>{busy ? "Uploading…" : "Start marking"}</Button>
        <span className="help">{problem ?? (settings?.provider === "tokenrouter" ? "Marking takes about 30 s per script on the free tier." : "Marking usually takes under a minute.")}</span>
      </div>
      {saveTitle !== null && (
        <Dialog title="Save as assignment" onClose={() => setSaveTitle(null)}
          footer={<><Button variant="secondary" onClick={() => setSaveTitle(null)}>Cancel</Button><Button variant="primary" onClick={saveAsAssignment} disabled={saving || !saveTitle.trim()}>{saving ? "Saving…" : "Save"}</Button></>}>
          <p className="help" style={{ marginBottom: 12 }}>Saves the subject, context and rubric so you can pick them again for the next script.</p>
          <div className="field"><label htmlFor="save-title">Title</label>
            <input id="save-title" className="input" autoFocus placeholder="Sec 4 · Quadratics worksheet" value={saveTitle} onChange={(e) => setSaveTitle(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") saveAsAssignment(); }} /></div>
        </Dialog>
      )}
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Settings, Subject } from "../api/types";
import { Button } from "../components/Button";
import { CriteriaEditor } from "../components/CriteriaTable";
import { DropZone } from "../components/DropZone";
import { Notice } from "../components/Notice";
import { PageCard } from "../components/PageCard";
import { canThumbnail } from "../lib/files";
import { emptyRow, jsonToRows, rowsToRubricJson, validateRows, type Row } from "../lib/rubric";

type Picked = { file: File; url: string };

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

  useEffect(() => { api.get<Settings>("/api/settings").then(setSettings).catch(() => setSettings(null)); }, []);
  const filesRef = useRef<Picked[]>([]);
  filesRef.current = files;
  // Revoke object URLs only when the page unmounts — revoking on every change would blank the remaining thumbnails.
  useEffect(() => () => filesRef.current.forEach((f) => f.url && URL.revokeObjectURL(f.url)), []);

  const add = (picked: File[]) => setFiles((cur) => [...cur, ...picked.map((file) => ({ file, url: canThumbnail(file) ? URL.createObjectURL(file) : "" }))]);
  const remove = (i: number) => setFiles((cur) => { cur[i].url && URL.revokeObjectURL(cur[i].url); return cur.filter((_, j) => j !== i); });
  const move = (i: number, d: -1 | 1) => setFiles((cur) => { const c = [...cur]; const j = i + d; if (j < 0 || j >= c.length) return cur; [c[i], c[j]] = [c[j], c[i]]; return c; });
  const uploadJson = (f: File) => f.text().then((t) => { try { setRows(jsonToRows(t)); setError(null); } catch (e: any) { setError(`Rubric JSON: ${e.message}`); } });

  const problem = useMemo(() => {
    if (!label.trim()) return "Give the script a label, e.g. the student’s name.";
    const v = validateRows(rows); if (v) return v;
    if (files.length === 0) return "Add at least one page.";
    return null;
  }, [label, rows, files]);

  const submit = async () => {
    setBusy(true); setError(null);
    const fd = new FormData();
    fd.set("label", label.trim()); fd.set("subject", subject); fd.set("context", context.trim()); fd.set("rubric", rowsToRubricJson(rows));
    files.forEach((f) => fd.append("files", f.file, f.file.name));
    try { const r = await api.postForm<{ id: number }>("/api/submissions", fd); nav(`/submissions/${r.id}`); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Upload failed — check your connection and try again."); setBusy(false); }
  };

  return (
    <div className="page">
      <Link to="/submissions" className="breadcrumb">← Submissions</Link>
      <div className="page-header"><div><h1>Mark a script</h1><p className="meta">One student’s pages, marked against your criteria.</p></div></div>
      {settings && !settings.has_key && <Notice>No API key yet. <Link to="/settings">Add one under Settings</Link> before marking.</Notice>}
      <div className="grid-2" style={{ marginTop: 24 }}>
        <div>
          <div className="field"><label htmlFor="label">Label</label><input id="label" className="input" placeholder="Tan Wei Ling · Worksheet 3" value={label} onChange={(e) => setLabel(e.target.value)} /></div>
          <div className="grid-2">
            <div className="field"><label>Subject</label>
              <div className="seg" role="radiogroup" aria-label="Subject">
                {(["math", "language", "science"] as Subject[]).map((s) => (
                  <label key={s} className={`seg-opt ${subject === s ? "on" : ""}`}><input type="radio" name="subject" checked={subject === s} onChange={() => setSubject(s)} />{{ math: "Maths", language: "English", science: "Science" }[s]}</label>
                ))}
              </div></div>
            <div className="field"><label htmlFor="ctx">Context (optional)</label><input id="ctx" className="input" placeholder="Sec 4 · Quadratic equations · 5 questions" value={context} onChange={(e) => setContext(e.target.value)} /></div>
          </div>
          <div className="field">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <label>Rubric <span className="help">— applied to every question</span></label>
              <label className="btn btn-ghost btn-sm" style={{ cursor: "pointer" }}>Upload JSON instead<input type="file" accept=".json,application/json" hidden onChange={(e) => e.target.files?.[0] && uploadJson(e.target.files[0])} /></label>
            </div>
            <CriteriaEditor rows={rows} onChange={setRows} />
          </div>
        </div>
        <div>
          <DropZone onFiles={add} />
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
    </div>
  );
}

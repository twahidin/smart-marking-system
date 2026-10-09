import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { ClassRow, Subject } from "../api/types";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { Notice } from "../components/Notice";
import { SUBJECTS, subjectLabel } from "../lib/format";
import { ART } from "../scene/art";
import { ClassTile } from "../scene/ClassTile";
import { useDeviceTier } from "../scene/useDeviceTier";
import { useFilm } from "../scene/useFilm";
import { useSceneLabels } from "../scene/useSceneLabels";

export function Classes() {
  const [rows, setRows] = useState<ClassRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState<Subject | "">("");
  const [busy, setBusy] = useState(false);
  const tier = useDeviceTier();
  const [labels, setLabels] = useSceneLabels();
  const [film, setFilm] = useFilm(tier);
  const load = useCallback(async () => {
    try { setRows(await api.get<ClassRow[]>("/api/classes")); setError(null); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Couldn't load classes."); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const create = async () => {
    setBusy(true);
    try { await api.post("/api/classes", { name: name.trim(), subject: subject || null }); setCreating(false); setName(""); setSubject(""); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Something went wrong — try again."); }
    finally { setBusy(false); }
  };
  const live = (rows ?? []).filter((c) => !c.archived_at);
  const archived = (rows ?? []).filter((c) => c.archived_at);
  const students = live.reduce((n, c) => n + c.student_count, 0);
  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Your school</h1><p className="meta">Every classroom is a class with its own hand-in code. Tap a classroom to open it; build a new one to add a class.</p></div>
        <div className="actions">
          {rows && <span className="pill pill-outline tabular">{live.length} classroom{live.length === 1 ? "" : "s"} · {students} student{students === 1 ? "" : "s"}</span>}
          <button type="button" className={`btn btn-sm ${labels ? "btn-primary" : "btn-secondary"}`} aria-pressed={labels} onClick={() => setLabels(!labels)}>Show labels</button>
          {tier === "2d" && <button type="button" className={`btn btn-sm ${film ? "btn-primary" : "btn-secondary"}`} aria-pressed={film} onClick={() => setFilm(!film)}>Film</button>}
          <Button variant="primary" onClick={() => setCreating(true)}><Plus size={16} aria-hidden /> Build a classroom</Button>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {rows && live.length === 0 && (
        <div className="campus-empty">
          <img src={ART.school} alt="An empty school with four classrooms around a courtyard and a plot marked out for a new one" />
          <p className="help" style={{ textAlign: "center", marginTop: 12 }}>Your school is empty. Build your first classroom, upload its classlist, then set an assignment from the bank.</p>
          <div className="actions" style={{ justifyContent: "center" }}><Button variant="primary" onClick={() => setCreating(true)}>Build your first classroom</Button></div>
        </div>
      )}
      {live.length > 0 && (
        <div className="campus">
          {live.map((c) => <ClassTile key={c.id} c={c} tier={tier} labels={labels} film={film} />)}
          <button type="button" className="tile-plot" onClick={() => setCreating(true)}>+ Build a classroom</button>
        </div>
      )}
      {archived.length > 0 && (
        <details className="section"><summary>Archived ({archived.length})</summary>
          <div className="cards">{archived.map((c) => <ClassCard key={c.id} c={c} />)}</div>
        </details>
      )}
      {creating && (
        <Dialog title="Build a classroom" onClose={() => setCreating(false)}
          footer={<><Button variant="secondary" onClick={() => setCreating(false)}>Cancel</Button><Button variant="primary" onClick={create} disabled={busy || !name.trim()}>Create class</Button></>}>
          <div className="field"><label htmlFor="class-name">Class name</label>
            <input id="class-name" className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="4E2 Mathematics"
              onKeyDown={(e) => { if (e.key === "Enter" && name.trim() && !busy) create(); }} /></div>
          <div className="field"><label htmlFor="class-subject">Subject</label>
            <select id="class-subject" className="input" value={subject} onChange={(e) => setSubject(e.target.value as Subject | "")}>
              <option value="">Follow the latest assignment</option>
              {SUBJECTS.map((s) => <option key={s} value={s}>{subjectLabel[s]}</option>)}
            </select>
            <p className="help">Chooses the classroom's painting. Leave it to follow whatever you set for the class.</p></div>
        </Dialog>
      )}
    </div>
  );
}

function ClassCard({ c }: { c: ClassRow }) {
  return (
    <Link to={`/classes/${c.id}`} className="card-link">
      <div className="card-title">{c.name}</div>
      <div className="meta"><span className="mono">{c.code}</span> · {c.student_count} student{c.student_count === 1 ? "" : "s"} · {c.open_assignments} open</div>
    </Link>
  );
}

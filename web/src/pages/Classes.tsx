import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { ClassRow } from "../api/types";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";

export function Classes() {
  const [rows, setRows] = useState<ClassRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setRows(await api.get<ClassRow[]>("/api/classes")); setError(null); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Couldn't load classes."); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const create = async () => {
    setBusy(true);
    try { await api.post("/api/classes", { name: name.trim() }); setCreating(false); setName(""); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Something went wrong — try again."); }
    finally { setBusy(false); }
  };
  const live = (rows ?? []).filter((c) => !c.archived_at);
  const archived = (rows ?? []).filter((c) => c.archived_at);
  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Classes</h1><p className="meta">Each class has a code students type to hand in.</p></div>
        <Button variant="primary" onClick={() => setCreating(true)}><Plus size={16} aria-hidden /> New class</Button>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {rows && rows.length === 0 && (
        <EmptyState title="No classes yet"><p className="help">Create a class, upload its classlist, then set an assignment from the bank.</p></EmptyState>
      )}
      {live.length > 0 && (
        <div className="cards">
          {live.map((c) => <ClassCard key={c.id} c={c} />)}
        </div>
      )}
      {archived.length > 0 && (
        <details className="section"><summary>Archived ({archived.length})</summary>
          <div className="cards">{archived.map((c) => <ClassCard key={c.id} c={c} />)}</div>
        </details>
      )}
      {creating && (
        <Dialog title="New class" onClose={() => setCreating(false)}
          footer={<><Button variant="secondary" onClick={() => setCreating(false)}>Cancel</Button><Button variant="primary" onClick={create} disabled={busy || !name.trim()}>Create class</Button></>}>
          <div className="field"><label htmlFor="class-name">Class name</label>
            <input id="class-name" className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="4E2 Mathematics"
              onKeyDown={(e) => { if (e.key === "Enter" && name.trim() && !busy) create(); }} /></div>
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

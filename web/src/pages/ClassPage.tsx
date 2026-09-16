import { Copy, Plus } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { AssignmentTemplate, ClassAssignment, ClassRow, Student } from "../api/types";
import { Button } from "../components/Button";
import { ClasslistImport } from "../components/ClasslistImport";
import { Dialog } from "../components/Dialog";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { fmtDate, schemeLabel } from "../lib/format";

type Tab = "students" | "assignments" | "settings";
const TABS: { id: Tab; label: string }[] = [{ id: "students", label: "Students" }, { id: "assignments", label: "Assignments" }, { id: "settings", label: "Settings" }];
const isTab = (s: string | null): s is Tab => s === "students" || s === "assignments" || s === "settings";

const msg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export function ClassPage() {
  const classId = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const tab: Tab = isTab(params.get("tab")) ? (params.get("tab") as Tab) : "students";
  const [cls, setCls] = useState<ClassRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let live = true;
    api.get<ClassRow>(`/api/classes/${classId}`).then((c) => { if (live) setCls(c); }, (e) => { if (live) setError(msg(e, "Couldn't load this class.")); });
    return () => { live = false; };
  }, [classId]);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 3000);
    return () => clearTimeout(t);
  }, [copied]);

  const copyLink = async () => {
    if (!cls) return;
    try { await navigator.clipboard.writeText(`${window.location.origin}/c/${cls.code}`); setCopied(true); }
    catch { setError("Couldn't copy — select the code and copy it yourself."); }
  };

  if (error && !cls) return <div className="page"><Link to="/classes" className="breadcrumb">← Classes</Link><Notice kind="error">{error}</Notice></div>;
  if (!cls) return <p className="page muted">Loading…</p>;

  return (
    <div className="page">
      <Link to="/classes" className="breadcrumb">← Classes</Link>
      <div className="page-header">
        <div>
          <h1>{cls.name} {cls.archived_at && <span className="pill pill-neutral" style={{ verticalAlign: "middle" }}>Archived</span>}</h1>
          <p className="meta">Class code <span className="mono">{cls.code}</span> · {cls.student_count} student{cls.student_count === 1 ? "" : "s"} · {cls.open_assignments} open</p>
        </div>
        <div className="actions" style={{ alignItems: "center" }}>
          {copied && <span className="help" role="status">Copied — Paste this into Google Classroom</span>}
          <Button variant="secondary" onClick={copyLink} icon={<Copy size={16} aria-hidden />}>Copy link</Button>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="tabs seg" role="tablist" aria-label="Class sections">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className={`seg-opt ${tab === t.id ? "on" : ""}`}
            onClick={() => setParams(t.id === "students" ? {} : { tab: t.id }, { replace: true })}>{t.label}</button>
        ))}
      </div>
      {tab === "students" && <StudentsTab cls={cls} onCount={(n) => setCls({ ...cls, student_count: n })} />}
      {tab === "assignments" && <AssignmentsTab cls={cls} onOpenCount={(n) => setCls({ ...cls, open_assignments: n })} />}
      {tab === "settings" && <SettingsTab cls={cls} onChange={setCls} />}
    </div>
  );
}

/* ---- Students ---- */
function StudentsTab({ cls, onCount }: { cls: ClassRow; onCount: (n: number) => void }) {
  const [students, setStudents] = useState<Student[] | null>(null);
  const [kept, setKept] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.get<Student[]>(`/api/classes/${cls.id}/students`).then((s) => { if (live) setStudents(s); }, (e) => { if (live) setError(msg(e, "Couldn't load the classlist.")); });
    return () => { live = false; };
  }, [cls.id]);
  return (
    <>
      {error && <Notice kind="error">{error}</Notice>}
      <ClasslistImport classId={cls.id} hasStudents={students ? students.length > 0 : cls.student_count > 0}
        onSaved={(s, k) => { setStudents(s); setKept(k); onCount(s.length); }} />
      {kept.length > 0 && (
        <div style={{ marginTop: 16 }}><Notice>{kept.length} student{kept.length === 1 ? "" : "s"} not in the file {kept.length === 1 ? "was" : "were"} kept because they have hand-ins.</Notice></div>
      )}
      {students && students.length > 0 && (
        <table className="table" style={{ marginTop: 20 }}>
          <thead><tr><th className="num">#</th><th>Name</th><th className="num">Submissions</th><th>Last seen</th></tr></thead>
          <tbody>
            {students.map((s) => (
              <tr key={s.id}><td className="num">{s.reg_no}</td><td>{s.name}</td><td className="num">{s.submissions}</td><td className="muted">{fmtDate(s.last_seen_at)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

/* ---- Assignments ---- */
const STATUS: Record<ClassAssignment["derived_status"], { label: string; pill: string }> = {
  draft: { label: "Draft", pill: "pill-neutral" }, open: { label: "Open", pill: "pill-open" },
  marking: { label: "Marking", pill: "pill-ink" }, released: { label: "Released", pill: "pill-outline" },
};

function AssignmentsTab({ cls, onOpenCount }: { cls: ClassRow; onOpenCount: (n: number) => void }) {
  const [rows, setRows] = useState<ClassAssignment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [setting, setSetting] = useState(false);
  const [deleting, setDeleting] = useState<ClassAssignment | null>(null);

  const apply = useCallback((next: ClassAssignment[]) => { setRows(next); onOpenCount(next.filter((r) => r.derived_status === "open").length); }, [onOpenCount]);
  const load = useCallback(async () => {
    try { setRows(await api.get<ClassAssignment[]>(`/api/classes/${cls.id}/assignments`)); setError(null); }
    catch (e) { setError(msg(e, "Couldn't load the assignments.")); }
  }, [cls.id]);
  useEffect(() => { load(); }, [load]);

  const setStatus = async (ca: ClassAssignment, status: "draft" | "open") => {
    setBusy(true);
    try {
      const updated = await api.put<ClassAssignment>(`/api/classes/${cls.id}/assignments/${ca.id}`, { title: ca.title, due_at: ca.due_at, allow_student_uploads: ca.allow_student_uploads, status });
      apply((rows ?? []).map((r) => (r.id === ca.id ? updated : r))); setError(null);
    } catch (e) { setError(msg(e, "Couldn't update the assignment.")); }
    finally { setBusy(false); }
  };
  const remove = async (ca: ClassAssignment) => {
    setBusy(true);
    try { await api.delete(`/api/classes/${cls.id}/assignments/${ca.id}`); apply((rows ?? []).filter((r) => r.id !== ca.id)); setError(null); }
    catch (e) { setError(e instanceof ApiError && e.code === "in_use" ? "Students have already handed in — this assignment can't be deleted." : msg(e, "Couldn't delete the assignment.")); }
    finally { setBusy(false); setDeleting(null); }
  };

  return (
    <>
      <div className="section-head">
        <h2>Assignments</h2>
        <Button variant="primary" onClick={() => setSetting(true)}><Plus size={16} aria-hidden /> Set assignment</Button>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {rows && rows.length === 0 && <EmptyState title="Nothing set yet"><p className="help">Set an assignment from the bank. Students hand in against it once it is open.</p></EmptyState>}
      {rows && rows.length > 0 && (
        <table className="table tall">
          <thead><tr><th>Title</th><th>Status</th><th>Due</th><th className="num">Hand-ins</th><th /></tr></thead>
          <tbody>
            {rows.map((ca) => (
              <tr key={ca.id}>
                <td>
                  <Link to={`/classes/${cls.id}/assignments/${ca.id}`}><strong>{ca.title}</strong></Link>
                  {ca.template_deleted && <div className="warn-note">Assignment deleted from the bank — set it again</div>}
                  {ca.scheme_kind && <div className="help">{schemeLabel[ca.scheme_kind] ?? ca.scheme_kind}</div>}
                </td>
                <td><span className={`pill ${STATUS[ca.derived_status].pill}`}>{STATUS[ca.derived_status].label}</span></td>
                <td className="muted">{fmtDate(ca.due_at)}</td>
                <td className="num">{ca.submission_count}</td>
                <td>
                  <div className="actions" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
                    {ca.status === "draft" && !ca.template_deleted && <Button variant="ghost" onClick={() => setStatus(ca, "open")} disabled={busy}>Open</Button>}
                    {ca.status === "open" && ca.submission_count === 0 && <Button variant="ghost" onClick={() => setStatus(ca, "draft")} disabled={busy}>Back to draft</Button>}
                    {ca.submission_count === 0 && <Button variant="ghost" onClick={() => setDeleting(ca)} disabled={busy}>Delete</Button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {setting && <SetAssignmentDialog classId={cls.id} onClose={() => setSetting(false)} onCreated={(ca) => { apply([...(rows ?? []), ca]); setSetting(false); }} />}
      {deleting && (
        <Dialog title="Delete this assignment?" onClose={() => setDeleting(null)}
          footer={<><Button variant="secondary" onClick={() => setDeleting(null)}>Cancel</Button><Button variant="primary" onClick={() => remove(deleting)} disabled={busy}>Delete assignment</Button></>}>
          <p>“{deleting.title}” is removed from this class. The assignment stays in the bank.</p>
        </Dialog>
      )}
    </>
  );
}

function SetAssignmentDialog({ classId, onClose, onCreated }: { classId: number; onClose: () => void; onCreated: (ca: ClassAssignment) => void }) {
  const [templates, setTemplates] = useState<AssignmentTemplate[] | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [title, setTitle] = useState("");
  const [titleTouched, setTitleTouched] = useState(false);
  const [dueAt, setDueAt] = useState("");
  const [allowUploads, setAllowUploads] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.get<AssignmentTemplate[]>("/api/assignments").then((t) => { if (live) setTemplates(t); }, (e) => { if (live) setError(msg(e, "Couldn't load the assignment bank.")); });
    return () => { live = false; };
  }, []);
  const choose = (id: string) => {
    setTemplateId(id);
    const t = templates?.find((x) => String(x.id) === id);
    if (t && !titleTouched) setTitle(t.title);
  };
  const create = async () => {
    if (!templateId) return;
    setBusy(true);
    try {
      const ca = await api.post<ClassAssignment>(`/api/classes/${classId}/assignments`, {
        template_id: Number(templateId), title: title.trim() || undefined, due_at: dueAt ? new Date(dueAt).toISOString() : null, allow_student_uploads: allowUploads,
      });
      onCreated(ca);
    } catch (e) { setError(msg(e, "Couldn't set the assignment.")); }
    finally { setBusy(false); }
  };
  return (
    <Dialog title="Set an assignment" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="primary" onClick={create} disabled={busy || !templateId}>Set for this class</Button></>}>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="field"><label htmlFor="ca-template">Assignment from the bank</label>
        <select id="ca-template" className="input" aria-label="Assignment from the bank" value={templateId} onChange={(e) => choose(e.target.value)} autoFocus>
          <option value="">{templates ? (templates.length ? "Choose an assignment…" : "The bank is empty — save one under Assignments first") : "Loading…"}</option>
          {(templates ?? []).map((t) => <option key={t.id} value={t.id}>{t.title} · {schemeLabel[t.scheme_kind] ?? t.scheme_kind} · {t.total_marks} mark{t.total_marks === 1 ? "" : "s"}</option>)}
        </select></div>
      <div className="field"><label htmlFor="ca-title">Title students see</label>
        <input id="ca-title" className="input" value={title} onChange={(e) => { setTitle(e.target.value); setTitleTouched(true); }} placeholder="Defaults to the bank title" /></div>
      <div className="field"><label htmlFor="ca-due">Due (optional)</label>
        <input id="ca-due" className="input" type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} /></div>
      <label style={{ display: "flex", gap: 10, alignItems: "center", minHeight: 44, cursor: "pointer" }}>
        <input type="checkbox" checked={allowUploads} onChange={(e) => setAllowUploads(e.target.checked)} style={{ width: 18, height: 18 }} />
        <span>Students can submit their own pages</span>
      </label>
    </Dialog>
  );
}

/* ---- Settings ---- */
function SettingsTab({ cls, onChange }: { cls: ClassRow; onChange: (c: ClassRow) => void }) {
  const [name, setName] = useState(cls.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [regen, setRegen] = useState(false);
  const run = async (label: string, fn: () => Promise<ClassRow>) => {
    setBusy(true); setError(null); setOk(null);
    try { onChange(await fn()); setOk(label); }
    catch (e) { setError(msg(e, "Something went wrong — try again.")); }
    finally { setBusy(false); }
  };
  const rename = (e: FormEvent) => { e.preventDefault(); if (name.trim() && name.trim() !== cls.name) run("Class renamed.", () => api.put<ClassRow>(`/api/classes/${cls.id}`, { name: name.trim() })); };
  const toggleArchive = () => run(cls.archived_at ? "Class unarchived." : "Class archived.", () => api.post<ClassRow>(`/api/classes/${cls.id}/${cls.archived_at ? "unarchive" : "archive"}`));
  const regenerate = async () => { setRegen(false); await run("New code issued.", () => api.post<ClassRow>(`/api/classes/${cls.id}/regenerate-code`)); };
  return (
    <>
      {error && <Notice kind="error">{error}</Notice>}
      {ok && <Notice kind="ok">{ok}</Notice>}
      <form className="section" onSubmit={rename} style={{ marginTop: 16, borderTop: 0, paddingTop: 0 }}>
        <div className="field" style={{ maxWidth: 480 }}><label htmlFor="class-name">Class name</label>
          <input id="class-name" className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <Button type="submit" variant="primary" disabled={busy || !name.trim() || name.trim() === cls.name}>Save name</Button>
      </form>
      <div className="section">
        <h2 style={{ fontSize: 20 }}>Class code</h2>
        <p className="help">Students open <span className="mono">{window.location.origin}/c/{cls.code}</span> and enter their register number. Issue a new code if the link has leaked.</p>
        <div className="actions" style={{ marginTop: 12 }}><Button variant="secondary" onClick={() => setRegen(true)} disabled={busy}>Regenerate code</Button></div>
      </div>
      <div className="section">
        <h2 style={{ fontSize: 20 }}>{cls.archived_at ? "Archived" : "Archive"}</h2>
        <p className="help">{cls.archived_at ? `Archived ${fmtDate(cls.archived_at)}. Students can't hand in until it is unarchived.` : "Hides the class from the list and stops hand-ins. Nothing is deleted — you can unarchive it later."}</p>
        <div className="actions" style={{ marginTop: 12 }}><Button variant="secondary" onClick={toggleArchive} disabled={busy}>{cls.archived_at ? "Unarchive" : "Archive class"}</Button></div>
      </div>
      {regen && (
        <Dialog title="Regenerate the class code?" onClose={() => setRegen(false)}
          footer={<><Button variant="secondary" onClick={() => setRegen(false)}>Cancel</Button><Button variant="primary" onClick={regenerate} disabled={busy}>Issue new code</Button></>}>
          <p>The old link stops working. Students who already entered their number stay signed in.</p>
        </Dialog>
      )}
    </>
  );
}

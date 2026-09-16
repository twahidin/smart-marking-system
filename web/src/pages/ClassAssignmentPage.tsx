import { ArrowRight, Download, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { ClassAssignment, ClassAssignmentDetail, ClassRow, RosterRow, RosterStatus } from "../api/types";
import { Button } from "../components/Button";
import { Dialog } from "../components/Dialog";
import { Notice } from "../components/Notice";
import { ProgressStrip, type StripBucket } from "../components/ProgressStrip";
import { downloadFile } from "../lib/download";
import { fmtDate } from "../lib/format";
import { qLabel, totalLabel } from "../lib/marks";

const POLL_MS = 10_000;
const ACCEPT = ".pdf,.jpg,.jpeg,.png,.heic,.heif,image/*,application/pdf";
const msg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

const HEADER_STATUS: Record<ClassAssignment["derived_status"], { label: string; pill: string }> = {
  draft: { label: "Draft", pill: "pill-neutral" }, open: { label: "Open", pill: "pill-open" },
  marking: { label: "Marking", pill: "pill-ink" }, released: { label: "Released", pill: "pill-outline" },
};

const ROW_STATUS: Record<RosterStatus, { label: string; pill: string }> = {
  not_handed_in: { label: "Not handed in", pill: "pill-neutral" }, handed_in: { label: "Handed in", pill: "pill-outline" },
  marking: { label: "Marking", pill: "pill-neutral" }, failed: { label: "Marking failed", pill: "pill-failed" },
  needs_you: { label: "Needs you", pill: "pill-amber" }, ready: { label: "Ready", pill: "pill-ink" }, released: { label: "Released", pill: "pill-outline" },
};
const rowLabel = (r: RosterRow) => (r.status === "needs_you" && r.needs_you_parts.length ? `Needs you · ${r.needs_you_parts.map(qLabel).join(", ")}` : ROW_STATUS[r.status].label);

/** The strip cell a row counts under — mirrors the backend: failed sits under marking, released under ready. */
const bucket = (s: RosterStatus): StripBucket => (s === "failed" ? "marking" : s === "released" ? "ready" : s);
const BUCKET_LABEL: Record<StripBucket, string> = { not_handed_in: "not handed in", handed_in: "handed in", marking: "marking", needs_you: "needing you", ready: "ready" };
const hasRecord = (r: RosterRow) => r.submission_id !== null && (r.status === "needs_you" || r.status === "ready" || r.status === "released");
const inFlight = (r: RosterRow) => r.status === "handed_in" || r.status === "marking";

export function ClassAssignmentPage() {
  const { id, caid } = useParams();
  const classId = Number(id);
  const caId = Number(caid);
  const nav = useNavigate();
  const [cls, setCls] = useState<ClassRow | null>(null);
  const [detail, setDetail] = useState<ClassAssignmentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<StripBucket | null>(null);
  const [releasing, setReleasing] = useState(false);
  const [uploading, setUploading] = useState<RosterRow | null>(null);
  const [removing, setRemoving] = useState<RosterRow | null>(null);
  const [busy, setBusy] = useState<"release" | "csv" | "records" | "remove" | null>(null);
  const live = useRef(true);

  const base = `/api/classes/${classId}/assignments/${caId}`;
  const load = useCallback(async () => {
    try { const d = await api.get<ClassAssignmentDetail>(base); if (live.current) { setDetail(d); setError(null); } }
    catch (e) { if (live.current) setError(msg(e, "Couldn't load this assignment.")); }
  }, [base]);

  useEffect(() => {
    live.current = true;
    load();
    api.get<ClassRow>(`/api/classes/${classId}`).then((c) => { if (live.current) setCls(c); }, () => { /* breadcrumb falls back to "Class" */ });
    return () => { live.current = false; };
  }, [load, classId]);

  // Poll only while a script is still queued or marking, so an idle page makes no requests.
  const polling = detail?.roster.rows.some(inFlight) ?? false;
  useEffect(() => {
    if (!polling) return;
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [polling, load]);

  if (error && !detail) return <div className="page"><Link to={`/classes/${classId}?tab=assignments`} className="breadcrumb">← {cls?.name ?? "Class"}</Link><Notice kind="error">{error}</Notice></div>;
  if (!detail) return <p className="page muted">Loading…</p>;

  const { roster } = detail;
  const rows = filter ? roster.rows.filter((r) => bucket(r.status) === filter) : roster.rows;
  const released = detail.status === "released";
  const status = released ? HEADER_STATUS.released : HEADER_STATUS[detail.derived_status];
  const markedCount = roster.rows.filter((r) => r.status === "ready" || r.status === "released").length;
  const releaseBlock = roster.counts.needs_you > 0 ? "Resolve the parts that need you before releasing."
    : detail.status !== "open" ? "Open the assignment before releasing feedback."
    : markedCount === 0 ? "Nothing has been marked yet." : undefined;
  const recordIds = roster.rows.filter(hasRecord).map((r) => r.submission_id as number);

  const run = async (kind: NonNullable<typeof busy>, fallback: string, fn: () => Promise<void>) => {
    setBusy(kind); setError(null);
    try { await fn(); } catch (e) { if (live.current) setError(msg(e, fallback)); } finally { if (live.current) setBusy(null); }
  };
  // Dialogs close in `finally` so a refusal (409 needs_you / nothing_marked / marking …) shows in the page Notice
  // rather than being hidden under the backdrop.
  const release = () => run("release", "Couldn't release feedback — try again.", async () => {
    let updated: ClassAssignment;
    try { updated = await api.post<ClassAssignment>(`${base}/release`); }
    finally { if (live.current) setReleasing(false); }
    if (!live.current) return;
    setDetail((d) => (d ? { ...d, ...updated } : d));
    // The roster's statuses flip to "released" server-side; refresh just that part so the header keeps the release result.
    try { const fresh = await api.get<ClassAssignmentDetail>(base); if (live.current) setDetail((d) => (d ? { ...d, roster: fresh.roster } : d)); }
    catch (e) { if (live.current) setError(msg(e, "Feedback was released, but the roster couldn't be refreshed — reload the page.")); }
  });
  const downloadCsv = () => run("csv", "Couldn't download the marks — try again.", () => downloadFile(`${base}/marks.csv`, "marks.csv"));
  const downloadRecords = () => run("records", "Couldn't download the records — try again.", () => downloadFile("/api/submissions/records.zip", "marking-records.zip", { ids: recordIds }));
  const remove = (r: RosterRow) => run("remove", "Couldn't remove the hand-in — try again.", async () => {
    try { await api.delete(`${base}/students/${r.student_id}/submission`); }
    finally { if (live.current) setRemoving(null); }
    if (live.current) await load();
  });

  return (
    <div className="page">
      <Link to={`/classes/${classId}?tab=assignments`} className="breadcrumb">← {cls?.name ?? "Class"}</Link>
      <div className="page-header">
        <div>
          <h1>{detail.title}</h1>
          <p className="meta">
            <span className={`pill ${status.pill}`} style={{ verticalAlign: "middle", marginRight: 10 }}>{status.label}</span>
            Due {fmtDate(detail.due_at)} · {roster.rows.length} student{roster.rows.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className="actions">
          <Button variant="secondary" icon={<Download size={16} aria-hidden />} onClick={downloadCsv} disabled={busy !== null}>{busy === "csv" ? "Preparing…" : "Download marks CSV"}</Button>
          <Button variant="secondary" icon={<Download size={16} aria-hidden />} onClick={downloadRecords} disabled={busy !== null || recordIds.length === 0}
            title={recordIds.length === 0 ? "No marked scripts to download yet." : undefined}>{busy === "records" ? "Preparing…" : "Download marking records"}</Button>
          {!released && (
            <Button variant="primary" onClick={() => setReleasing(true)} disabled={busy !== null || releaseBlock !== undefined} title={releaseBlock}>Release feedback</Button>
          )}
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {detail.template_deleted && <Notice>The assignment was deleted from the bank — new hand-ins can't be marked until it is set again.</Notice>}

      <ProgressStrip counts={roster.counts} filter={filter} onFilter={setFilter} />

      {filter && (
        <div className="section-head">
          <p className="meta" style={{ margin: 0 }}>Showing {rows.length} student{rows.length === 1 ? "" : "s"} {BUCKET_LABEL[filter]}</p>
          <Button variant="ghost" onClick={() => setFilter(null)}>Show all {roster.rows.length}</Button>
        </div>
      )}
      {roster.rows.length === 0 && <p className="help">No students yet — import a classlist under the class's Students tab.</p>}
      {roster.rows.length > 0 && (
        <table className="table tall">
          <thead><tr><th className="num">#</th><th>Name</th><th className="num">Pages</th><th>Handed in</th><th>Status</th><th className="num">Total</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => {
              const link = r.submission_id !== null ? `/submissions/${r.submission_id}` : null;
              return (
                <tr key={r.student_id} className={link ? "row-link" : undefined} onClick={link ? () => nav(link) : undefined}>
                  <td className="num">{r.reg_no}</td>
                  <td>{link ? <Link to={link} onClick={(e) => e.stopPropagation()}><strong>{r.name}</strong></Link> : <strong>{r.name}</strong>}</td>
                  <td className="num">{r.submission_id !== null ? r.pages : "—"}</td>
                  <td className="muted">
                    {r.handed_in_at === null ? "—" : <>{r.source === "teacher" ? "Uploaded by you" : fmtDate(r.handed_in_at)}{r.late && <span className="tertiary"> · late</span>}</>}
                  </td>
                  <td><span className={`pill ${ROW_STATUS[r.status].pill}`}>{rowLabel(r)}</span></td>
                  <td className="num">{totalLabel(r.total !== null && r.total_upper !== null && r.total_max !== null ? { total: r.total, total_upper: r.total_upper, total_max: r.total_max } : null)}</td>
                  <td>
                    <div className="actions" style={{ justifyContent: "flex-end", flexWrap: "nowrap", alignItems: "center" }} onClick={(e) => e.stopPropagation()}>
                      {r.status === "not_handed_in" && (
                        <Button variant="secondary" icon={<Upload size={14} aria-hidden />} onClick={() => setUploading(r)} disabled={detail.template_deleted}>Upload pages</Button>
                      )}
                      {r.submission_id !== null && <Button variant="ghost" onClick={() => setRemoving(r)} disabled={busy !== null}>Remove hand-in</Button>}
                      {link && <ArrowRight size={16} aria-hidden className="tertiary" />}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {releasing && (
        <Dialog title="Release feedback to students?" onClose={() => setReleasing(false)}
          footer={<><Button variant="secondary" onClick={() => setReleasing(false)}>Cancel</Button><Button variant="primary" onClick={release} disabled={busy !== null}>Release to students</Button></>}>
          <p>Students will see their marks and feedback. Students can no longer hand in. Pages you upload for a student later are marked and shown to them automatically.</p>
        </Dialog>
      )}
      {uploading && <UploadDialog base={base} student={uploading} onClose={() => setUploading(null)} onDone={() => { setUploading(null); load(); }} />}
      {removing && (
        <Dialog title={`Remove ${removing.name}'s hand-in?`} onClose={() => setRemoving(null)}
          footer={<><Button variant="secondary" onClick={() => setRemoving(null)}>Cancel</Button><Button variant="primary" onClick={() => remove(removing)} disabled={busy !== null}>Remove hand-in</Button></>}>
          <p>The pages and any marking are deleted. {removing.name} can hand in again.</p>
        </Dialog>
      )}
    </div>
  );
}

function UploadDialog({ base, student, onClose, onDone }: { base: string; student: RosterRow; onClose: () => void; onDone: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const add = (picked: File[]) => setFiles((cur) => [...cur, ...picked]);
  const start = async () => {
    if (!files.length) return;
    setBusy(true); setError(null);
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    try { await api.postForm(`${base}/students/${student.student_id}/upload`, fd); onDone(); }
    catch (e) { setError(e instanceof ApiError && e.code === "no_key" ? "Add an API key under Settings before marking." : msg(e, "Couldn't upload the pages — try again.")); setBusy(false); }
  };
  return (
    <Dialog title={`Upload pages for ${student.name}`} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button><Button variant="primary" onClick={start} disabled={busy || files.length === 0}>{busy ? "Uploading…" : "Start marking"}</Button></>}>
      {error && <Notice kind="error">{error}</Notice>}
      <div className={`drop ${over ? "over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); add(Array.from(e.dataTransfer.files)); }}>
        <Upload size={32} aria-hidden />
        <h3>Drop {student.name}'s pages here</h3>
        <p className="help">PDF, JPG, PNG or HEIC — up to 20 pages. The script is marked as handed in by you.</p>
        <button type="button" className="btn btn-secondary" onClick={() => input.current?.click()}>Choose files</button>
        <input ref={input} type="file" multiple accept={ACCEPT} hidden aria-label={`Choose pages for ${student.name}`}
          onChange={(e) => { add(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
      </div>
      {files.length > 0 && (
        <ul className="help" style={{ margin: "12px 0 0", paddingLeft: 20 }}>
          {files.map((f, i) => <li key={`${f.name}-${i}`}>{f.name}</li>)}
        </ul>
      )}
    </Dialog>
  );
}

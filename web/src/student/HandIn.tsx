import { ArrowDown, ArrowUp, Camera, Images, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import type { StudentAssignmentDetail } from "../api/types";
import { canThumbnail } from "../lib/files";
import { fmtDate } from "../lib/format";
import { downscale } from "../lib/image";
import { studentApi as api } from "./api";

interface Page { id: string; file: File; url: string }

const OFFLINE = "Couldn't hand in — check your signal and try again.";
const UNREACHABLE = "Can't reach Smart Marking — check your signal and try again.";

export function HandIn() {
  const { caid } = useParams();
  const [detail, setDetail] = useState<StudentAssignmentDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [doneAt, setDoneAt] = useState<string | null>(null);
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  const nextId = useRef(1);

  const load = () => {
    setLoadError(null);
    api.get<StudentAssignmentDetail>(`/api/student/assignments/${caid}`).then(
      setDetail,
      (e) => setLoadError(e instanceof ApiError ? e.message : UNREACHABLE),
    );
  };
  useEffect(load, [caid]);

  // Revoke object URLs only when the page unmounts — revoking on every change would blank the remaining thumbnails.
  const pagesRef = useRef<Page[]>([]);
  pagesRef.current = pages;
  useEffect(() => () => pagesRef.current.forEach((p) => p.url && URL.revokeObjectURL(p.url)), []);

  const add = (picked: File[]) => {
    if (picked.length === 0) return;
    setError(null);
    setPages((cur) => [...cur, ...picked.map((file) => ({ id: String(nextId.current++), file, url: canThumbnail(file) ? URL.createObjectURL(file) : "" }))]);
  };
  const remove = (i: number) => { setError(null); setPages((cur) => { cur[i].url && URL.revokeObjectURL(cur[i].url); return cur.filter((_, j) => j !== i); }); };
  const move = (i: number, d: -1 | 1) => setPages((cur) => { const c = [...cur]; const j = i + d; if (j < 0 || j >= c.length) return cur; [c[i], c[j]] = [c[j], c[i]]; return c; });

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const fd = new FormData();
      for (const p of pages) { const f = await downscale(p.file); fd.append("files", f, f.name); }
      await api.postForm(`/api/student/assignments/${caid}/hand-in`, fd);
      setDoneAt(new Date().toISOString());
    } catch (e) { setError(e instanceof ApiError ? e.message : OFFLINE); }
    finally { setBusy(false); }
  };

  if (loadError) {
    return (
      <>
        <p role="alert" className="notice notice-error">{loadError}</p>
        <button type="button" className="btn btn-secondary btn-lg" onClick={load}>Try again</button>
      </>
    );
  }
  if (!detail) return <p className="muted">Loading…</p>;
  if (doneAt) {
    return (
      <>
        <h1>{detail.title}</h1>
        <p className="notice notice-ok student-done">{`Handed in ${fmtDate(doneAt)}`}</p>
        <p className="help">Your teacher will see it shortly. You'll find your feedback here once it's ready.</p>
        <Link className="btn btn-primary btn-lg" to="/s">Back to assignments</Link>
      </>
    );
  }
  if (detail.status !== "to_hand_in") return <Navigate to={`/s/a/${caid}`} replace />;
  if (!detail.allow_student_uploads) {
    return (
      <>
        <h1>{detail.title}</h1>
        <p className="notice">Hand-ins for this assignment are closed.</p>
        <Link className="btn btn-secondary btn-lg" to="/s">Back to assignments</Link>
      </>
    );
  }

  const n = pages.length;
  return (
    <>
      <h1>{detail.title}</h1>
      <p className="muted student-due">{detail.due_at ? `Due ${fmtDate(detail.due_at)}` : "No due date"}</p>
      <div className="student-actions">
        <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={() => camera.current?.click()}><Camera size={20} aria-hidden /> Take photo</button>
        <button type="button" className="btn btn-secondary btn-lg" disabled={busy} onClick={() => gallery.current?.click()}><Images size={20} aria-hidden /> Choose from gallery</button>
        <input ref={camera} type="file" accept="image/*" capture="environment" hidden aria-label="Take photo"
          onChange={(e) => { add(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
        <input ref={gallery} type="file" accept="image/*,.pdf,.heic,.heif" multiple hidden aria-label="Choose from gallery"
          onChange={(e) => { add(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
      </div>
      <p className="help">One photo per page, in order — up to 20 pages. Photos are shrunk on your phone before they're sent.</p>
      {n > 0 && (
        <ol className="student-pages" aria-label="Pages">
          {pages.map((p, i) => (
            <li key={p.id} className="student-page">
              <span className="student-page-no" aria-hidden>{i + 1}</span>
              {p.url
                ? <img className="student-thumb" src={p.url} alt="" />
                : <span className="student-thumb student-thumb-file" aria-hidden>{p.file.name.replace(/^.*\./, "").toUpperCase()}</span>}
              <span className="help student-page-name">{p.file.name}</span>
              <span className="student-page-actions">
                <button type="button" className="btn btn-secondary" aria-label="Move up" disabled={busy || i === 0} onClick={() => move(i, -1)}><ArrowUp size={20} aria-hidden /></button>
                <button type="button" className="btn btn-secondary" aria-label="Move down" disabled={busy || i === n - 1} onClick={() => move(i, 1)}><ArrowDown size={20} aria-hidden /></button>
                <button type="button" className="btn btn-secondary" aria-label="Delete" disabled={busy} onClick={() => remove(i)}><Trash2 size={20} aria-hidden /></button>
              </span>
            </li>
          ))}
        </ol>
      )}
      {error && <p role="alert" className="notice notice-error">{error}</p>}
      {n > 0 && (error
        ? <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={submit}>{busy ? "Handing in…" : "Try again"}</button>
        : <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={submit}>{busy ? "Handing in…" : `Hand in ${n} ${n === 1 ? "page" : "pages"}`}</button>)}
    </>
  );
}

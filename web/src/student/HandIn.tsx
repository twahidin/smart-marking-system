import { ArrowDown, ArrowUp, Camera, FileCode2, Images, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import type { StudentAssignmentDetail } from "../api/types";
import { canThumbnail, capUploads, fmtSize, isProgramFile, MAX_HAND_IN_PAGES, MAX_PROGRAM_FILES, PROGRAM_ACCEPT, prepareUploads } from "../lib/files";
import { fmtDate } from "../lib/format";
import { studentApi as api } from "./api";

interface Page { id: string; file: File; url: string; kind: "photo" | "file" }

/** "Hand in 2 pages", "Hand in 1 file", "Hand in 1 page and 2 files". */
export function handInLabel(pages: Page[]): string {
  const photos = pages.filter((p) => p.kind === "photo").length, files = pages.length - photos;
  const bits: string[] = [];
  if (photos) bits.push(`${photos} ${photos === 1 ? "page" : "pages"}`);
  if (files) bits.push(`${files} ${files === 1 ? "file" : "files"}`);
  return `Hand in ${bits.join(" and ")}`;
}

const MAX_PAGES = MAX_HAND_IN_PAGES;
const PHOTOS_ONLY = "This assignment takes photos only.";
const OFFLINE = "Couldn't hand in — check your signal and try again.";
const UNREACHABLE = "Can't reach Smart Marking — check your signal and try again.";

export function HandIn() {
  const { caid } = useParams();
  const [detail, setDetail] = useState<StudentAssignmentDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [overLimit, setOverLimit] = useState(false);
  const [overFiles, setOverFiles] = useState(false);
  const [busy, setBusy] = useState(false);
  const [doneAt, setDoneAt] = useState<string | null>(null);
  // What the server dropped out of a zip (notes.txt, data.csv …). Said out loud on the done screen,
  // so a student whose folder went up half-ignored finds out now rather than when the marks come back.
  const [ignored, setIgnored] = useState<string[]>([]);
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  const programs = useRef<HTMLInputElement>(null);
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

  // Object URLs are created outside the state updater — StrictMode runs updaters twice in dev and would leak one per file.
  const add = (picked: File[]) => {
    // Program files are only marked where the marker can read them. The accept lists never offer them
    // elsewhere, but a phone's Files app can still reach one, so say no out loud rather than silently.
    const usable = detail?.accepts_files ? picked : picked.filter((f) => !isProgramFile(f));
    if (usable.length === 0) {
      if (picked.length > 0) setError(PHOTOS_ONLY);
      return;
    }
    setError(null);
    // Both caps are the server's, checked here so nobody learns about them after a long upload.
    const { kept, overItems, overFiles: tooManyFiles } = capUploads(usable, pages.map((p) => p.file), MAX_PAGES);
    setOverLimit(overItems);
    setOverFiles(tooManyFiles);
    if (kept.length === 0) return;
    const built: Page[] = kept.map((file) => ({
      id: String(nextId.current++), file, url: canThumbnail(file) ? URL.createObjectURL(file) : "",
      kind: isProgramFile(file) ? "file" : "photo",
    }));
    setPages((cur) => [...cur, ...built]);
  };
  const remove = (i: number) => {
    setError(null); setOverLimit(false); setOverFiles(false);
    const gone = pages[i];
    if (gone?.url) URL.revokeObjectURL(gone.url);
    setPages((cur) => cur.filter((p) => p !== gone));
  };
  const move = (i: number, d: -1 | 1) => setPages((cur) => { const c = [...cur]; const j = i + d; if (j < 0 || j >= c.length) return cur; [c[i], c[j]] = [c[j], c[i]]; return c; });

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const fd = new FormData();
      // Photos are shrunk on the phone; program files go up byte for byte.
      for (const f of await prepareUploads(pages.map((p) => p.file))) fd.append("files", f, f.name);
      const r = await api.postForm<{ ignored?: string[] }>(`/api/student/assignments/${caid}/hand-in`, fd);
      setIgnored(r?.ignored ?? []);
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
        {ignored.length > 0 && <p role="status" className="notice">{`Skipped: ${ignored.join(", ")}`}</p>}
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
        {detail.accepts_files && (
          <>
            <button type="button" className="btn btn-secondary btn-lg" disabled={busy} onClick={() => programs.current?.click()}><FileCode2 size={20} aria-hidden /> Add files</button>
            <input ref={programs} type="file" accept={PROGRAM_ACCEPT} multiple hidden aria-label="Add files"
              onChange={(e) => { add(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
          </>
        )}
      </div>
      <p className="help">{detail.accepts_files
        ? `Your .py, .sb3, .xlsx or .zip files, and a photo of anything you wrote on paper — up to ${MAX_PAGES} in all. Photos are shrunk on your phone before they're sent.`
        : `One photo per page, in order — up to ${MAX_PAGES} pages. Photos are shrunk on your phone before they're sent.`}</p>
      {overLimit && <p role="status" className="notice">{`You can hand in at most ${MAX_PAGES} ${detail.accepts_files ? "pages or files" : "pages"}.`}</p>}
      {overFiles && <p role="status" className="notice">{`You can hand in at most ${MAX_PROGRAM_FILES} files.`}</p>}
      {n > 0 && (
        <ol className="student-pages" aria-label={detail.accepts_files ? "Pages and files" : "Pages"}>
          {pages.map((p, i) => (
            <li key={p.id} className="student-page">
              <span className="student-page-no" aria-hidden>{i + 1}</span>
              {p.url
                ? <img className="student-thumb" src={p.url} alt="" />
                : <span className="student-thumb student-thumb-file" aria-hidden>{p.file.name.replace(/^.*\./, "").toUpperCase()}</span>}
              <span className="help student-page-name">{p.file.name}{p.kind === "file" && ` · ${fmtSize(p.file.size)}`}</span>
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
        : <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={submit}>{busy ? "Handing in…" : handInLabel(pages)}</button>)}
    </>
  );
}

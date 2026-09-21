import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { BulkMatch, BulkPreview, BulkResult } from "../api/types";
import { Button } from "./Button";
import { Dialog } from "./Dialog";
import { Notice } from "./Notice";

const msg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

/** One matched student as a teacher reads it: "#7 Amirah — 07_a.py, 7.jpg (skipped: notes.txt)",
 *  and, where the student has already handed in, what the Replace checkbox will do to them. */
const matchLine = (m: BulkMatch, replace: boolean): string => {
  let line = `#${m.reg_no} ${m.name} — ${m.files.join(", ")}`;
  if (m.ignored.length) line += ` (skipped: ${m.ignored.join(", ")})`;
  if (m.already_handed_in) line += ` · already handed in — will be ${replace ? "replaced" : "skipped"}`;
  return line;
};

/** A matched student the zip held nothing usable for — the commit would fail for them, so they are
 *  listed apart from the work that will actually go up. */
const unusableLine = (m: BulkMatch): string => `#${m.reg_no} ${m.name}${m.ignored.length ? ` (only: ${m.ignored.join(", ")})` : ""}`;

const resultLine = (r: BulkResult): string =>
  [`Created ${r.created.length}`, `Skipped ${r.skipped.length}`, ...(r.failed.length ? [`Failed ${r.failed.length}`] : []), `Not matched ${r.unmatched.length}`].join(" · ");

const SUB = { fontSize: 15, margin: "14px 0 0" } as const;
const LIST = { margin: "4px 0 0", paddingLeft: 20 } as const;

function Group({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <>
      <h3 style={SUB}>{title}</h3>
      <ul className="help" style={LIST}>
        {items.map((t) => <li key={t}>{t}</li>)}
      </ul>
    </>
  );
}

/** Hand in a whole class at once: one zip, matched to students by register number. The zip is previewed
 *  before anything is created, so the teacher sees what each student will get — and what won't match —
 *  while it can still be fixed in the folder rather than undone in the app. */
export function BulkUploadDialog({ base, onClose, onDone }: { base: string; onClose: () => void; onDone: () => void }) {
  const [preview, setPreview] = useState<BulkPreview | null>(null);
  const [result, setResult] = useState<BulkResult | null>(null);
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The picked zip is held as-is and sent twice — once to preview, once to commit — so the teacher
  // isn't asked for the same file again, and the commit reads exactly the zip that was previewed.
  const zip = useRef<File | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const form = () => { const fd = new FormData(); fd.append("zip", zip.current!, zip.current!.name); return fd; };

  const pick = async (file: File | undefined) => {
    if (!file) return;
    zip.current = file;
    setBusy(true); setError(null); setPreview(null); setResult(null);
    try { setPreview(await api.postForm<BulkPreview>(`${base}/bulk/preview`, form())); }
    catch (e) { setError(msg(e, "Couldn't read the zip — try again.")); }
    finally { setBusy(false); }
  };

  const upload = async () => {
    if (!zip.current) return;
    setBusy(true); setError(null);
    try {
      const r = await api.postForm<BulkResult>(`${base}/bulk?replace=${replace ? 1 : 0}`, form());
      setResult(r); setPreview(null);
      onDone();
    } catch (e) { setError(msg(e, "Couldn't upload the hand-ins — try again.")); }
    finally { setBusy(false); }
  };

  const matched = preview?.matched.filter((m) => m.files.length > 0) ?? [];
  const unusable = preview?.matched.filter((m) => m.files.length === 0) ?? [];
  const canReplace = matched.some((m) => m.already_handed_in);

  return (
    <Dialog title="Bulk upload" onClose={onClose}
      footer={result
        ? <Button variant="primary" onClick={onClose}>Done</Button>
        : <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
            {matched.length > 0 && <Button variant="primary" onClick={upload} disabled={busy}>{busy ? "Uploading…" : "Upload"}</Button>}
          </>}>
      {error && <Notice kind="error">{error}</Notice>}

      {result ? (
        <>
          <p role="status"><strong>{resultLine(result)}</strong></p>
          {result.failed.length > 0 && (
            <ul className="help" style={LIST}>
              {result.failed.map((f) => <li key={f.reg_no}>{`#${f.reg_no} — ${f.error}`}</li>)}
            </ul>
          )}
        </>
      ) : (
        <>
          <div className={`drop ${over ? "over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]); }}>
            <Upload size={32} aria-hidden />
            <h3>Drop the class's zip here</h3>
            <p className="help">One .zip of the whole class's work. Each student's files are matched by their register number — 07_a.py and 7.jpg both go to #7.</p>
            <button type="button" className="btn btn-secondary" onClick={() => input.current?.click()}>Choose a zip</button>
            <input ref={input} type="file" accept=".zip" hidden aria-label="Choose a zip of hand-ins"
              onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
          </div>
          {busy && !preview && <p className="help" role="status">Reading the zip…</p>}
          {preview && (
            <>
              {matched.length > 0 && (
                <>
                  <h3 style={SUB}>Matched</h3>
                  <ul className="help" style={LIST}>
                    {matched.map((m) => <li key={m.student_id}>{matchLine(m, replace)}</li>)}
                  </ul>
                </>
              )}
              {canReplace && (
                <label style={{ display: "flex", gap: 10, alignItems: "center", minHeight: 44, cursor: "pointer" }}>
                  <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} style={{ width: 18, height: 18 }} />
                  <span>Replace existing hand-ins</span>
                </label>
              )}
              <Group title="No usable files" items={unusable.map(unusableLine)} />
              <Group title="Not matched" items={preview.unmatched} />
              <Group title="More than one student" items={preview.ambiguous} />
              {matched.length === 0 && <p className="help">Nothing in the zip matched a student — check the filenames carry a register number.</p>}
            </>
          )}
        </>
      )}
    </Dialog>
  );
}

import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { BulkMatch, BulkPreview, BulkResult, PdfPreview } from "../api/types";
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

const isPdf = (f: File) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");

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

const readLine = (r: PdfPreview["booklets"][number]["read"]): string =>
  r.index_number || r.name ? [r.index_number && `#${r.index_number}`, r.name].filter(Boolean).join(" · ") : "Couldn't read the cover";

/** The booklets found in a combined PDF, each with its cover crop so the teacher can check the match by eye, and
 *  a student picker that starts on the proposed match. A student picked for two booklets is flagged. */
function BookletTable({ preview, chosen, onChoose, replace, disabled }: {
  preview: PdfPreview; chosen: Record<number, number | null>; onChoose: (booklet: number, student: number | null) => void;
  replace: boolean; disabled: boolean;
}) {
  const counts = new Map<number, number>();
  Object.values(chosen).forEach((s) => { if (s != null) counts.set(s, (counts.get(s) ?? 0) + 1); });
  const byId = new Map(preview.students.map((s) => [s.id, s]));
  return (
    <table className="table" aria-label="Booklets" style={{ marginTop: 12 }}>
      <thead><tr><th>Booklet</th><th>Cover</th><th>Student</th></tr></thead>
      <tbody>
        {preview.booklets.map((b) => {
          const sid = chosen[b.booklet] ?? null;
          const twice = sid != null && (counts.get(sid) ?? 0) > 1;
          const s = sid != null ? byId.get(sid) : undefined;
          return (
            <tr key={b.booklet}>
              <td style={{ whiteSpace: "nowrap", verticalAlign: "top" }}>
                <strong>{b.booklet}</strong>
                <div className="help">{b.start === b.end ? `page ${b.start}` : `pages ${b.start}–${b.end}`}</div>
              </td>
              <td style={{ verticalAlign: "top" }}>
                <img src={b.cover} alt={`Cover of booklet ${b.booklet}`} style={{ display: "block", width: 260, maxWidth: "100%", border: "1px solid var(--color-divider)" }} />
                <div className="help">Read: {readLine(b.read)}</div>
              </td>
              <td style={{ verticalAlign: "top", minWidth: 200 }}>
                <select className="input" aria-label={`Student for booklet ${b.booklet}`} value={sid ?? ""} disabled={disabled}
                  onChange={(e) => onChoose(b.booklet, e.target.value ? Number(e.target.value) : null)}>
                  <option value="">— don't hand in —</option>
                  {preview.students.map((st) => <option key={st.id} value={st.id}>{`#${st.reg_no} ${st.name}`}</option>)}
                </select>
                {twice && <div className="help" role="alert" style={{ color: "var(--crew-marker-ink)" }}>Picked for another booklet too</div>}
                {!twice && s?.already_handed_in && <div className="help">Already handed in — will be {replace ? "replaced" : "skipped"}</div>}
                {!twice && sid != null && b.student_id === sid && b.matched_by && <div className="help">Matched by {b.matched_by === "index" ? "index number" : "name"}</div>}
                {sid == null && <div className="help">Pick the student whose booklet this is</div>}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** Hand in a whole class at once: one zip matched to students by register number, or one combined PDF split at
 *  each booklet's cover and matched by the index number written there. Either is previewed before anything is
 *  created, so the teacher sees what each student will get while it can still be fixed. */
export function BulkUploadDialog({ base, onClose, onDone }: { base: string; onClose: () => void; onDone: () => void }) {
  const [preview, setPreview] = useState<BulkPreview | null>(null);
  const [pdfPreview, setPdfPreview] = useState<PdfPreview | null>(null);
  const [chosen, setChosen] = useState<Record<number, number | null>>({});
  const [result, setResult] = useState<BulkResult | null>(null);
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The picked file is held as-is and sent twice — once to preview, once to commit — so the teacher isn't
  // asked for the same file again, and the commit reads exactly the file that was previewed.
  const file = useRef<File | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const form = (field: string) => { const fd = new FormData(); fd.append(field, file.current!, file.current!.name); return fd; };

  const pick = async (f: File | undefined) => {
    if (!f) return;
    file.current = f;
    setBusy(true); setError(null); setPreview(null); setPdfPreview(null); setResult(null); setReplace(false);
    try {
      if (isPdf(f)) {
        const p = await api.postForm<PdfPreview>(`${base}/bulk/pdf/preview`, form("pdf"));
        setPdfPreview(p);
        setChosen(Object.fromEntries(p.booklets.map((b) => [b.booklet, b.student_id])));
      } else {
        setPreview(await api.postForm<BulkPreview>(`${base}/bulk/preview`, form("zip")));
      }
    } catch (e) { setError(msg(e, isPdf(f) ? "Couldn't read the PDF — try again." : "Couldn't read the zip — try again.")); }
    finally { setBusy(false); }
  };

  const picked = pdfPreview ? pdfPreview.booklets.filter((b) => chosen[b.booklet] != null) : [];
  const duplicates = new Set(picked.map((b) => chosen[b.booklet])).size !== picked.length;

  const upload = async () => {
    if (!file.current) return;
    setBusy(true); setError(null);
    try {
      let r: BulkResult;
      if (pdfPreview) {
        const fd = form("pdf");
        fd.append("booklets", JSON.stringify(picked.map((b) => ({ start: b.start, end: b.end, student_id: chosen[b.booklet] }))));
        r = await api.postForm<BulkResult>(`${base}/bulk/pdf?replace=${replace ? 1 : 0}`, fd);
      } else {
        r = await api.postForm<BulkResult>(`${base}/bulk?replace=${replace ? 1 : 0}`, form("zip"));
      }
      setResult(r); setPreview(null); setPdfPreview(null);
      onDone();
    } catch (e) { setError(msg(e, "Couldn't upload the hand-ins — try again.")); }
    finally { setBusy(false); }
  };

  const matched = preview?.matched.filter((m) => m.files.length > 0) ?? [];
  const unusable = preview?.matched.filter((m) => m.files.length === 0) ?? [];
  const pdfStudents = new Map((pdfPreview?.students ?? []).map((s) => [s.id, s]));
  const canReplace = pdfPreview
    ? picked.some((b) => pdfStudents.get(chosen[b.booklet]!)?.already_handed_in)
    : matched.some((m) => m.already_handed_in);
  const ready = pdfPreview ? picked.length > 0 && !duplicates : matched.length > 0;

  return (
    <Dialog title="Bulk upload" onClose={onClose}
      footer={result
        ? <Button variant="primary" onClick={onClose}>Done</Button>
        : <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
            {(preview || pdfPreview) && ready && (
              <Button variant="primary" onClick={upload} disabled={busy}>
                {busy ? "Uploading…" : pdfPreview ? `Hand in ${picked.length} booklet${picked.length === 1 ? "" : "s"}` : "Upload"}
              </Button>
            )}
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
          {/* Closed while a file is being read or uploaded: a second pick would replace the file the
              commit is about to send, and the preview on screen would no longer be of it. */}
          <div className={`drop ${over ? "over" : ""}`} aria-disabled={busy}
            onDragOver={(e) => { e.preventDefault(); if (!busy) setOver(true); }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); if (!busy) pick(e.dataTransfer.files[0]); }}>
            <Upload size={32} aria-hidden />
            <h3>Drop the class's zip or combined PDF here</h3>
            <p className="help">One .zip of the whole class's work, matched by register number — 07_a.py and 7.jpg both go to #7.
              Or one PDF of every script scanned together: it's split at each booklet's cover and matched by the index number written there.</p>
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => input.current?.click()}>Choose a zip or PDF</button>
            <input ref={input} type="file" accept=".zip,.pdf,application/pdf" hidden disabled={busy} aria-label="Choose a zip or PDF of hand-ins"
              onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
          </div>
          {busy && !preview && !pdfPreview && (
            <p className="help" role="status">{file.current && isPdf(file.current) ? "Finding each booklet and reading its cover — this can take half a minute…" : "Reading the zip…"}</p>
          )}
          {pdfPreview && (
            <>
              <h3 style={SUB}>{`${pdfPreview.booklets.length} booklet${pdfPreview.booklets.length === 1 ? "" : "s"} in ${pdfPreview.pdf_pages} pages`}</h3>
              {pdfPreview.read_error && (
                <Notice>{`Couldn't read the covers, so pick each student yourself. The reading model said: ${pdfPreview.read_error} — check this assignment's model for reading pages.`}</Notice>
              )}
              <p className="help">Check each cover against the student picked for it. Blank pages are left out, and two-page spreads are split into single pages.</p>
              <BookletTable preview={pdfPreview} chosen={chosen} replace={replace} disabled={busy}
                onChoose={(booklet, student) => setChosen((c) => ({ ...c, [booklet]: student }))} />
              {duplicates && <p className="help" role="alert">A student is picked for two booklets — choose a different student for one of them.</p>}
            </>
          )}
          {preview && matched.length > 0 && (
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
          {preview && (
            <>
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

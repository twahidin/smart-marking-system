import { Download, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { SubmissionRow } from "../api/types";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { StatusPill } from "../components/StatusPill";
import { downloadFile } from "../lib/download";
import { fmtDate, subjectLabel } from "../lib/format";
import { totalLabel } from "../lib/marks";

/** A marking record exists once a script has been marked: done, or waiting on the teacher for some parts. */
export const hasRecord = (r: Pick<SubmissionRow, "status">): boolean => r.status === "done" || r.status === "needs_you";

export function Submissions() {
  const [rows, setRows] = useState<SubmissionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [downloading, setDownloading] = useState(false);
  const [skipped, setSkipped] = useState<string | null>(null);
  const nav = useNavigate();
  useEffect(() => {
    let alive = true;
    const load = () => api.get<SubmissionRow[]>("/api/submissions").then((r) => alive && setRows(r)).catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // The download covers the ticked scripts, or every script shown when none is ticked.
  const chosen = useMemo(() => (rows ?? []).filter((r) => selected.size === 0 || selected.has(r.id)), [rows, selected]);
  const marked = useMemo(() => chosen.filter(hasRecord), [chosen]);
  const toggle = (id: number) => setSelected((cur) => { const next = new Set(cur); next.has(id) ? next.delete(id) : next.add(id); return next; });
  const toggleAll = () => setSelected((cur) => (rows && cur.size === rows.length ? new Set() : new Set((rows ?? []).map((r) => r.id))));

  const downloadRecords = async () => {
    setDownloading(true); setError(null); setSkipped(null);
    const unmarked = chosen.length - marked.length;
    try {
      await downloadFile("/api/submissions/records.zip", "marking-records.zip", { ids: marked.map((r) => r.id) });
      if (unmarked > 0) setSkipped(`${unmarked} script${unmarked === 1 ? " was" : "s were"} skipped — not marked yet.`);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not download — check your connection and try again."); }
    finally { setDownloading(false); }
  };
  const downloadLabel = selected.size > 0 ? `Download marking records (${marked.length} of ${selected.size})` : "Download marking records";

  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Submissions</h1><p className="meta">Scripts you have uploaded for marking.</p></div>
        <div className="actions">
          <Button variant="secondary" icon={<Download size={16} aria-hidden />} onClick={downloadRecords} disabled={downloading || marked.length === 0}
            title={marked.length === 0 ? "No marked scripts to download yet." : selected.size === 0 ? "Records for every script shown." : undefined}>{downloading ? "Preparing…" : downloadLabel}</Button>
          <Button variant="primary" icon={<Plus size={18} />} onClick={() => nav("/submissions/new")}>Mark a script</Button>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {skipped && <Notice>{skipped}</Notice>}
      {rows && rows.length === 0 && (
        <EmptyState title="Nothing marked yet">
          <p>Upload a script’s pages and a rubric. Marking runs in the background; questions the AI is unsure about land under <strong>Review</strong>.</p>
          <Link to="/submissions/new" className="btn btn-primary">Mark a script</Link>
        </EmptyState>
      )}
      {rows && rows.length > 0 && (
        <table className="table tall">
          <thead><tr>
            <th style={{ width: 44 }}><input type="checkbox" aria-label="Select all scripts" checked={selected.size === rows.length} onChange={toggleAll} style={{ width: 18, height: 18 }} /></th>
            <th>Script</th><th>Subject</th><th className="num">Pages</th><th>Status</th><th className="num">Total</th><th>Uploaded</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="row-link" onClick={() => nav(`/submissions/${r.id}`)}>
                <td onClick={(e) => e.stopPropagation()}><label style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 40, cursor: "pointer" }}><input type="checkbox" aria-label={`Select ${r.label}`} checked={selected.has(r.id)} onChange={() => toggle(r.id)} style={{ width: 18, height: 18 }} /></label></td>
                <td><strong>{r.label}</strong>{r.assignment_title && <div className="help">{r.assignment_title}</div>}</td>
                <td>{subjectLabel[r.subject]}</td>
                <td className="num">{r.page_count}</td>
                <td><StatusPill status={r.status} needsYou={r.needs_you_qids} /></td>
                <td className="num">{r.total === null ? "—" : totalLabel({ total: r.total, total_upper: r.total_upper!, total_max: r.total_max! })}</td>
                <td className="muted">{fmtDate(r.created_at)}</td>
                <td>→</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

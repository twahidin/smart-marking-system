import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { SubmissionRow } from "../api/types";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { StatusPill } from "../components/StatusPill";
import { fmtDate, subjectLabel } from "../lib/format";
import { totalLabel } from "../lib/marks";

export function Submissions() {
  const [rows, setRows] = useState<SubmissionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();
  useEffect(() => {
    let alive = true;
    const load = () => api.get<SubmissionRow[]>("/api/submissions").then((r) => alive && setRows(r)).catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  return (
    <div className="page">
      <div className="page-header">
        <div><h1>Submissions</h1><p className="meta">Scripts you have uploaded for marking.</p></div>
        <Button variant="primary" icon={<Plus size={18} />} onClick={() => nav("/submissions/new")}>Mark a script</Button>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {rows && rows.length === 0 && (
        <EmptyState title="Nothing marked yet">
          <p>Upload a script’s pages and a rubric. Marking runs in the background; questions the AI is unsure about land under <strong>Review</strong>.</p>
          <Link to="/submissions/new" className="btn btn-primary">Mark a script</Link>
        </EmptyState>
      )}
      {rows && rows.length > 0 && (
        <table className="table tall">
          <thead><tr><th>Script</th><th>Subject</th><th className="num">Pages</th><th>Status</th><th className="num">Total</th><th>Uploaded</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="row-link" onClick={() => nav(`/submissions/${r.id}`)}>
                <td><strong>{r.label}</strong></td>
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

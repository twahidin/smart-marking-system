import { Download, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Part, SubmissionDetail as D } from "../api/types";
import { Button } from "../components/Button";
import { CriteriaReading } from "../components/CriteriaTable";
import { MarkDisplay } from "../components/MarkDisplay";
import { Notice } from "../components/Notice";
import { PagePager } from "../components/PagePager";
import { StatusPill } from "../components/StatusPill";
import { downloadFile } from "../lib/download";
import { elapsed, fmtDate, subjectLabel } from "../lib/format";
import { qLabel } from "../lib/marks";

export function SubmissionDetail() {
  const { id } = useParams();
  const [d, setD] = useState<D | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = () => api.get<D>(`/api/submissions/${id}`).then((r) => { if (alive) { setD(r); setError(null); } }).catch((e) => alive && setError(e instanceof ApiError ? e.message : "Could not load"));
    load();
    const stillPolling = !d || ["uploaded", "queued", "marking"].includes(d.status);
    const t = stillPolling ? setInterval(() => { setTick((x) => x + 1); load(); }, 3000) : null;
    return () => { alive = false; if (t) clearInterval(t); };
  }, [id, d?.status]);

  if (error) return <div className="page"><Notice kind="error">{error}</Notice></div>;
  if (!d) return <div className="page muted">Loading…</div>;
  const inProgress = ["uploaded", "queued", "marking"].includes(d.status);
  const v2 = d.marks_version === 2;
  const parts = d.parts ?? [];
  const needsYou = v2 ? parts.filter((p) => p.escalated).map((p) => p.q_id) : d.marks.filter((m) => m.escalated).map((m) => m.q_id);
  const needsYouLabels = v2 ? parts.filter((p) => p.escalated).map((p) => p.label) : needsYou.map(qLabel);
  const perQMax = d.rubric.criterion_defs.reduce((s, c) => s + c.max_score, 0);
  // Pages deleted after marking are skipped by the pager; the panel below replaces the viewer once all are gone.
  const livePages = d.pages.filter((p) => !p.deleted);
  const pagesDeleted = !!d.pages_deleted || (d.pages.length > 0 && livePages.length === 0);
  const canDownload = d.status === "done" || d.status === "needs_you";

  const retry = async () => {
    setRetryError(null);
    try { await api.post(`/api/submissions/${d.id}/retry`); setD({ ...d, status: "queued" }); }
    catch (e) { setRetryError(e instanceof ApiError ? e.message : "Could not retry — check your connection and try again."); }
  };
  const download = async () => {
    setDownloading(true); setDownloadError(null);
    try { await downloadFile(`/api/submissions/${d.id}/record.docx`, `${d.label || `submission-${d.id}`} — marking record.docx`); }
    catch (e) { setDownloadError(e instanceof ApiError ? e.message : "Could not download — check your connection and try again."); }
    finally { setDownloading(false); }
  };

  return (
    <div>
      <div className="page" style={{ paddingBottom: 24 }}>
        <Link to="/submissions" className="breadcrumb">← Submissions</Link>
        <div className="page-header">
          <div>
            <h1>{d.label}</h1>
            <p className="meta">{d.assignment_title ? `${d.assignment_title} · ` : ""}{subjectLabel[d.subject]}{d.context && ` · ${d.context}`} · uploaded {fmtDate(d.created_at)} · {d.pages.length} page{d.pages.length === 1 ? "" : "s"}{d.marked_at ? ` · marked ${fmtDate(d.marked_at)}` : ""}</p>
            <div className="actions" style={{ marginTop: 12, alignItems: "center" }}>
              <Button variant="secondary" icon={<Download size={16} aria-hidden />} onClick={download} disabled={!canDownload || downloading} title={canDownload ? undefined : "Available once marking finishes."}>{downloading ? "Preparing…" : "Download marking record"}</Button>
              {!canDownload && <span className="help">Available once marking finishes.</span>}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="label-caps">Total</div>
            {d.totals ? <div style={{ fontSize: 40, fontWeight: 800, lineHeight: 1 }}><MarkDisplay earned={d.totals.total} upper={d.totals.total_upper} max={d.totals.total_max} squares={false} /></div> : <div className="tertiary" style={{ fontSize: 24 }}>—</div>}
            <div style={{ marginTop: 8 }}><StatusPill status={d.status} needsYou={needsYou} /></div>
          </div>
        </div>
        {inProgress && <Notice kind="ok">Marking… {d.job?.started_at ? `started ${elapsed(d.job.started_at)} ago` : "waiting for the worker"}. This page updates by itself.</Notice>}
        {d.status === "failed" && (
          <Notice>
            <strong>Marking failed.</strong> {d.job?.error ?? "Unknown error"}
            {retryError && <div style={{ marginTop: 8 }}><strong>Retry failed.</strong> {retryError}</div>}
            <div style={{ marginTop: 8 }}><Button size="sm" onClick={retry}>Retry</Button> <Link to="/settings" className="btn btn-ghost btn-sm">Check settings</Link></div>
          </Notice>
        )}
        {downloadError && <Notice kind="error"><strong>Download failed.</strong> {downloadError}</Notice>}
        {needsYou.length > 0 && (
          <Notice><TriangleAlert size={16} aria-hidden /> {needsYou.length} {v2 ? "part" : "question"}{needsYou.length > 1 ? "s" : ""} need{needsYou.length > 1 ? "" : "s"} you: {needsYouLabels.join(", ")}. <Link to="/review">Open the review queue</Link></Notice>
        )}
      </div>
      <div className="cols" style={{ borderTop: "2px solid var(--color-divider)" }}>
        <section>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h4 style={{ margin: 0 }}>Pages</h4>
            {!pagesDeleted && <PagePager count={livePages.length} current={Math.min(page, Math.max(0, livePages.length - 1))} onSelect={setPage} />}
          </div>
          {pagesDeleted
            ? <div className="page-view" role="note" aria-label="Pages deleted after marking" style={{ padding: 24 }}><strong style={{ display: "block", marginBottom: 6 }}>Pages deleted after marking</strong><span className="help">The marking record has everything that was read.</span></div>
            : livePages[Math.min(page, livePages.length - 1)] && <div className="page-view"><img className="grayscale" src={`/api/pages/${livePages[Math.min(page, livePages.length - 1)].id}`} alt={`Page ${Math.min(page, livePages.length - 1) + 1}`} /></div>}
        </section>
        <section>
          <h4>{v2 ? (d.scheme_kind === "rubric" ? "Marks by criterion" : "Marks by question part") : "Marks by question"}</h4>
          {v2 ? <PartsTable parts={parts} rubric={d.scheme_kind === "rubric"} inProgress={inProgress} /> : (
            <>
              {d.marks.length === 0 && <p className="muted">{inProgress ? "Marks appear here when marking finishes." : "No questions were found on these pages."}</p>}
              {d.marks.map((m) => {
                const scores = m.teacher_scores ?? m.criterion_scores;
                const total = scores.reduce((s, x) => s + x, 0);
                return (
                  <div className="qrow" key={m.q_id} style={{ display: "block" }}>
                    <button type="button" aria-expanded={open === m.q_id} onClick={() => setOpen(open === m.q_id ? null : m.q_id)}>
                      <span><strong>{qLabel(m.q_id)}</strong> {m.escalated && <span className="pill pill-amber" style={{ marginLeft: 8 }}><TriangleAlert size={12} aria-hidden /> Needs you</span>}{m.teacher_scores && <span className="help" style={{ marginLeft: 8 }}>your mark</span>}</span>
                      <MarkDisplay earned={total} max={perQMax} upper={m.escalated && !m.teacher_scores ? perQMax : undefined} />
                    </button>
                    {open === m.q_id && (
                      <div className="qrow-body">
                        <CriteriaReading defs={d.rubric.criterion_defs} scores={scores} />
                        {m.evidence && <div className="callout"><span className="label-caps">Evidence</span><div>“{m.evidence}”</div></div>}
                        {m.rationale && <p className="help">{m.rationale}</p>}
                        <p className="help">Confidence {m.confidence === null ? "—" : Math.round(m.confidence * 100) + "%"}{m.reason && ` · ${m.reason}`}</p>
                        {m.queue_id && <Link to={`/review?item=${m.queue_id}`} className="btn btn-ghost btn-sm">Resolve in the review queue →</Link>}
                      </div>
                    )}
                  </div>
                );
              })}
            </>
          )}
          {d.feedback && (
            <div style={{ marginTop: 32 }}>
              <hr className="rule-2" />
              <h4 style={{ marginTop: 16 }}>Feedback report</h4>
              <p>{d.feedback.summary}</p>
              <h6>What you did well</h6><ul>{d.feedback.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
              <h6>Question by question</h6>
              {d.feedback.per_question_comments.map((c) => <p key={c.q_id}><strong style={{ display: "inline-block", width: 96 }}>{qLabel(c.q_id)}</strong>{c.comment} <em>Try next: {c.suggested_action}</em></p>)}
              <h6>Work on next</h6><ul>{d.feedback.improvement_plan.map((s, i) => <li key={i}>{s}</li>)}</ul>
              <h6>Next steps</h6><ol>{d.feedback.next_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

const clip = (s: string, n = 600) => (s.length > n ? s.slice(0, n).trimEnd() + "…" : s);

/** Column 2 of the record: the scheme answer with its allocation labels, or the rubric criterion with its bands. */
function SchemeCell({ part }: { part: Part }) {
  const s = part.scheme;
  if (!s) return <span className="help">No scheme row — marked outside the scheme.</span>;
  if ("answer" in s) {
    return (
      <>
        <div style={{ whiteSpace: "pre-wrap" }}>{s.answer || <span className="tertiary">—</span>}</div>
        {s.marks.length > 0 && <div className="help" style={{ marginTop: 4, fontVariantNumeric: "tabular-nums" }}>[{s.marks.map((m) => `${m.label} ${m.marks}`).join(" · ")}]</div>}
        {s.notes && <div className="help" style={{ marginTop: 4 }}>{s.notes}</div>}
      </>
    );
  }
  return <>{s.bands.map((b) => <div key={b.band} className="help" style={{ marginTop: 2 }}><strong>Band {b.band}</strong> · {b.marks} — {b.descriptor}</div>)}</>;
}

/** Column 5: awarded chips + total, the teacher's mark, or the amber "Needs you" pill with the reason. */
function AwardedCell({ part }: { part: Part }) {
  if (part.teacher) {
    return (
      <div>
        <div style={{ fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{part.teacher.total} / {part.max} <span className="help">(teacher)</span></div>
        {"allocations" in part.teacher && <div className="chips" style={{ marginTop: 4 }}>{part.teacher.allocations.map((a) => <span key={a.label} className={`alloc ${a.got ? "got" : "lost"}`}>{a.label} {a.got ? "✓" : "✗"}</span>)}</div>}
        {"band" in part.teacher && <div className="help" style={{ marginTop: 4 }}>Band {part.teacher.band}</div>}
      </div>
    );
  }
  if (part.escalated) {
    return (
      <div>
        <span className="pill pill-amber"><TriangleAlert size={12} strokeWidth={2.5} aria-hidden /> Needs you</span>
        {part.reason && <div className="help" style={{ marginTop: 6 }}>{part.reason}</div>}
        {part.queue_id && <div style={{ marginTop: 6 }}><Link to={`/review?item=${part.queue_id}`} className="btn btn-ghost btn-sm">Resolve in the review queue →</Link></div>}
      </div>
    );
  }
  return (
    <div>
      {part.awarded && part.awarded.length > 0 && <div className="chips" style={{ marginBottom: 4 }}>{part.awarded.map((a) => <span key={a.label} className={`alloc ${a.got ? "got" : "lost"}`} title={a.why || undefined}>{a.label} {a.got ? "✓" : "✗"}</span>)}</div>}
      {part.band && <div className="help" style={{ marginBottom: 4 }}>Band {part.band}</div>}
      <MarkDisplay earned={part.total} max={part.max} squares={false} />
    </div>
  );
}

function PartsTable({ parts, rubric, inProgress }: { parts: Part[]; rubric: boolean; inProgress: boolean }) {
  if (parts.length === 0) return <p className="muted">{inProgress ? "Marks appear here when marking finishes." : "No parts were marked on these pages."}</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="table parts" aria-label={rubric ? "Marks by criterion" : "Marks by question part"}>
        <thead><tr><th>{rubric ? "Criterion" : "Question & part"}</th><th>{rubric ? "Bands" : "Scheme answer"}</th><th>Student’s answer</th><th>Justification</th><th>Awarded</th></tr></thead>
        <tbody>
          {parts.map((p) => (
            <tr key={p.q_id} className={p.escalated && !p.teacher ? "warn" : ""}>
              <td><strong>{p.label}</strong>{p.question_text && <div className="help" style={{ marginTop: 4 }}>{p.question_text}</div>}</td>
              <td><SchemeCell part={p} /></td>
              <td style={{ whiteSpace: "pre-wrap" }}>{p.illegible ? <span className="tertiary">(illegible)</span> : (clip(p.extracted) || <span className="tertiary">—</span>)}{!p.illegible && p.workings && <div className="help" style={{ marginTop: 4 }}>Workings: {clip(p.workings, 300)}</div>}</td>
              <td className="help" style={{ color: "var(--ink)" }}>{p.justification || <span className="tertiary">—</span>}{!p.in_scheme && <div className="warn-note" style={{ marginTop: 4 }}>Not in the scheme</div>}</td>
              <td><AwardedCell part={p} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

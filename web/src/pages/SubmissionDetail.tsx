import { TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { SubmissionDetail as D } from "../api/types";
import { Button } from "../components/Button";
import { CriteriaReading } from "../components/CriteriaTable";
import { MarkDisplay } from "../components/MarkDisplay";
import { Notice } from "../components/Notice";
import { PagePager } from "../components/PagePager";
import { StatusPill } from "../components/StatusPill";
import { elapsed, fmtDate, subjectLabel } from "../lib/format";
import { qLabel } from "../lib/marks";

export function SubmissionDetail() {
  const { id } = useParams();
  const [d, setD] = useState<D | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = () => api.get<D>(`/api/submissions/${id}`).then((r) => { if (alive) { setD(r); setError(null); } }).catch((e) => alive && setError(e instanceof ApiError ? e.message : "Could not load"));
    load();
    const t = setInterval(() => { setTick((x) => x + 1); if (!d || ["uploaded", "queued", "marking"].includes(d.status)) load(); }, 3000);
    return () => { alive = false; clearInterval(t); };
  }, [id, d?.status]);

  if (error) return <div className="page"><Notice kind="error">{error}</Notice></div>;
  if (!d) return <div className="page muted">Loading…</div>;
  const inProgress = ["uploaded", "queued", "marking"].includes(d.status);
  const needsYou = d.marks.filter((m) => m.escalated).map((m) => m.q_id);
  const perQMax = d.rubric.criterion_defs.reduce((s, c) => s + c.max_score, 0);

  const retry = async () => { await api.post(`/api/submissions/${d.id}/retry`); setD({ ...d, status: "queued" }); };

  return (
    <div>
      <div className="page" style={{ paddingBottom: 24 }}>
        <Link to="/submissions" className="breadcrumb">← Submissions</Link>
        <div className="page-header">
          <div>
            <h1>{d.label}</h1>
            <p className="meta">{subjectLabel[d.subject]}{d.context && ` · ${d.context}`} · uploaded {fmtDate(d.created_at)} · {d.pages.length} page{d.pages.length === 1 ? "" : "s"}</p>
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
            <strong>Marking failed.</strong> {d.job?.error ?? "Unknown error"}<div style={{ marginTop: 8 }}><Button size="sm" onClick={retry}>Retry</Button> <Link to="/settings" className="btn btn-ghost btn-sm">Check settings</Link></div>
          </Notice>
        )}
        {needsYou.length > 0 && (
          <Notice><TriangleAlert size={16} aria-hidden /> {needsYou.length} question{needsYou.length > 1 ? "s" : ""} need{needsYou.length > 1 ? "" : "s"} you: {needsYou.map(qLabel).join(", ")}. <Link to="/review">Open the review queue</Link></Notice>
        )}
      </div>
      <div className="cols" style={{ borderTop: "2px solid var(--color-divider)" }}>
        <section>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h4 style={{ margin: 0 }}>Pages</h4>
            <PagePager count={d.pages.length} current={page} onSelect={setPage} />
          </div>
          {d.pages[page] && <div className="page-view"><img className="grayscale" src={`/api/pages/${d.pages[page].id}`} alt={`Page ${page + 1}`} /></div>}
        </section>
        <section>
          <h4>Marks by question</h4>
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

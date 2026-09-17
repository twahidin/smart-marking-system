import { Download, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { InsightsPayload } from "../api/types";
import { downloadFile } from "../lib/download";
import { fmtDate, providerLabel } from "../lib/format";
import { Button } from "./Button";
import { Notice } from "./Notice";

const POLL_MS = 5_000;          // while the generate job is queued or running
const WEAK = 3;                 // the weakest parts the chart marks amber
const msg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

/** "38 of 40 marked · 3 still being marked or waiting for you · mean 15.2 / 25" */
function headline(stats: InsightsPayload["stats"]): string {
  const bits = [`${stats.n_marked} of ${stats.n_students} marked`];
  if (stats.n_pending) bits.push(`${stats.n_pending} still being marked or waiting for you`);
  if (stats.totals.mean !== null) bits.push(`mean ${stats.totals.mean} / ${stats.totals.max}`);
  return bits.join(" · ");
}

/**
 * One assignment's insights: the numbers computed from the marks (always there), and the AI narrative
 * over them (there once a generate job has succeeded). Every bar carries its own number — the amber
 * weakest-part highlight is never the only thing saying a part went badly.
 */
export function InsightsPanel({ classId, caId }: { classId: number; caId: number }) {
  const base = `/api/classes/${classId}/assignments/${caId}`;
  const [data, setData] = useState<InsightsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"regenerate" | "pdf" | null>(null);
  const live = useRef(true);

  const load = useCallback(async () => {
    try { const p = await api.get<InsightsPayload>(`${base}/insights`); if (live.current) { setData(p); setError(null); } }
    catch (e) { if (live.current) setError(msg(e, "Couldn't load the insights.")); }
  }, [base]);

  useEffect(() => {
    live.current = true;
    load();
    return () => { live.current = false; };
  }, [load]);

  // Poll only while the narrative is being written, so a settled panel makes no requests.
  const generating = data?.job?.status === "queued" || data?.job?.status === "running";
  useEffect(() => {
    if (!generating) return;
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [generating, load]);

  const regenerate = async () => {
    setBusy("regenerate"); setError(null);
    try {
      await api.post(`${base}/insights/regenerate`);
      // The job is queued server-side; showing it straight away starts the poll without waiting a tick.
      if (live.current) setData((d) => (d ? { ...d, job: { status: "queued" } } : d));
    } catch (e) { if (live.current) setError(msg(e, "Couldn't start the insights — try again.")); }
    finally { if (live.current) setBusy(null); }
  };
  const pdf = async () => {
    setBusy("pdf"); setError(null);
    try { await downloadFile(`${base}/insights.pdf`, "insights.pdf"); }
    catch (e) { if (live.current) setError(msg(e, "Couldn't download the insights — try again.")); }
    finally { if (live.current) setBusy(null); }
  };

  if (error && !data) return <Notice kind="error">{error}</Notice>;
  if (!data) return <p className="muted">Loading…</p>;

  const { stats, report } = data;
  const labels = new Map(stats.parts.map((p) => [p.q_id, p.label]));
  const partLabel = (q_id: string) => labels.get(q_id) ?? q_id;
  const byReg = new Map(stats.students.map((s) => [s.reg_no, s]));
  const weak = new Set(stats.weakest.slice(0, WEAK));
  const nothing = stats.n_marked === 0;
  const tallest = Math.max(1, ...stats.totals.buckets.map((b) => b.n));
  const generated = data.generated_at
    ? `Generated ${fmtDate(data.generated_at)}${data.provider ? ` · ${providerLabel[data.provider] ?? data.provider} ${data.model ?? ""}` : ""}`
    : null;

  return (
    <div>
      <div className="section-head">
        <div>
          <p className="meta" style={{ margin: 0 }}>{headline(stats)}</p>
          {generated && <p className="help" style={{ margin: "4px 0 0" }}>{generated}</p>}
        </div>
        <div className="actions">
          <Button variant="secondary" icon={<RefreshCw size={16} aria-hidden />} onClick={regenerate}
            disabled={busy !== null || generating || nothing} title={nothing ? "Nothing has been marked yet." : undefined}>
            {generating ? "Generating…" : "Regenerate"}
          </Button>
          <Button variant="secondary" icon={<Download size={16} aria-hidden />} onClick={pdf} disabled={busy !== null}>
            {busy === "pdf" ? "Preparing…" : "Download PDF"}
          </Button>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}

      {nothing && <p className="help">Nothing marked yet — the insights appear as soon as the first script has been marked.</p>}
      {!nothing && (
        <>
          {!report && <p className="help">The AI summary hasn't been generated yet — the numbers below are live.</p>}
          {/* A failed generate keeps whatever narrative was there before, so say so either way rather
              than leaving the teacher to wonder why nothing changed. */}
          {data.error && (
            report
              ? <Notice>The last regenerate attempt didn't finish: {data.error} — the summary below is the one from before.</Notice>
              : <Notice>The last attempt didn't finish: {data.error}</Notice>
          )}

          <section className="section">
            <h2>Marks by part</h2>
            <p className="help">Mean % of the marks available, in scheme order. The weakest parts are amber.</p>
            <ol className="bars" role="list" aria-label="Marks by part">
              {stats.parts.map((p) => (
                <li key={p.q_id} className={weak.has(p.q_id) ? "weak" : undefined}>
                  <span>{p.label}</span>
                  <span className="bar" style={{ width: `${p.mean_pct ?? 0}%` }} />
                  <span className="pct">{p.mean_pct === null ? "—" : `${p.mean_pct}%`}</span>
                </li>
              ))}
            </ol>
          </section>

          {stats.most_lost.length > 0 && (
            <section className="section">
              <h2>Most-lost allocations</h2>
              <ul className="points">
                {stats.most_lost.map((a) => (
                  <li key={`${a.q_id}-${a.label}`}>{`${partLabel(a.q_id)} · ${a.label} — ${a.lost} of ${a.of}`}</li>
                ))}
              </ul>
            </section>
          )}

          {report && (
            <>
              <section className="section">
                <h2>Summary</h2>
                <p>{report.summary}</p>
              </section>
              {report.strengths.length > 0 && (
                <section className="section">
                  <h2>Strengths</h2>
                  <ul className="points">{report.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
                </section>
              )}
              {report.gaps.length > 0 && (
                <section className="section">
                  <h2>Gaps</h2>
                  <ul className="points">
                    {report.gaps.map((g, i) => (
                      <li key={i}>
                        <strong>{g.title}</strong> <span className="muted">({g.part_ids.map(partLabel).join(", ") || "—"})</span>
                        <br />{g.what_went_wrong} — {g.students_affected} script{g.students_affected === 1 ? "" : "s"} affected
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {report.recommendations.length > 0 && (
                <section className="section">
                  <h2>Recommended next steps</h2>
                  <ul className="points">
                    {report.recommendations.map((r, i) => (
                      <li key={i}>
                        <strong>{r.title}</strong> <span className="muted">({r.part_ids.map(partLabel).join(", ") || "—"})</span>
                        <br />{r.detail}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {report.students_to_support.length > 0 && (
                <section className="section">
                  <h2>Students to support</h2>
                  {/* The narrative names register numbers — the model never saw a name — so the roster puts them back. */}
                  <table className="table" aria-label="Students to support">
                    <thead><tr><th className="num">#</th><th>Name</th><th>Weak parts</th><th>Focus</th></tr></thead>
                    <tbody>
                      {report.students_to_support.flatMap((s, i) => s.reg_nos.map((n) => {
                        const student = byReg.get(n);
                        return (
                          <tr key={`${i}-${n}`}>
                            <td className="num">{n}</td>
                            <td><strong>{student?.name ?? "—"}</strong></td>
                            <td className="muted">{student && student.weak_parts.length ? student.weak_parts.map(partLabel).join(", ") : "—"}</td>
                            <td>{s.focus}</td>
                          </tr>
                        );
                      }))}
                    </tbody>
                  </table>
                </section>
              )}
            </>
          )}

          {stats.totals.buckets.length > 0 && (
            <section className="section">
              <h2>Score distribution</h2>
              <p className="help">How many scripts scored in each band, out of {stats.totals.max}.</p>
              <ol className="bars" role="list" aria-label="Score distribution">
                {stats.totals.buckets.map((b) => (
                  <li key={b.from}>
                    <span>{b.from}–{b.to}</span>
                    <span className="bar" style={{ width: `${Math.round((b.n / tallest) * 100)}%` }} />
                    <span className="pct">{b.n}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </>
      )}
    </div>
  );
}

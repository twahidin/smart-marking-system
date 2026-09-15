import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { QueueItem } from "../api/types";
import { Button } from "../components/Button";
import { CriteriaReview } from "../components/CriteriaTable";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { PagePager } from "../components/PagePager";
import { qLabel } from "../lib/marks";

export function Review() {
  const { refreshQueue } = useOutletContext<{ refreshQueue: () => void }>();
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [i, setI] = useState(0);
  const [values, setValues] = useState<(number | "")[]>([]);
  const [reason, setReason] = useState("");
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [params] = useSearchParams();

  const load = useCallback(async () => {
    const list = await api.get<QueueItem[]>("/api/queue");
    setItems(list);
    const want = Number(params.get("item"));
    const idx = want ? Math.max(0, list.findIndex((x) => x.id === want)) : 0;
    setI(Math.min(idx, Math.max(0, list.length - 1)));
  }, [params]);
  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  const item = items?.[i];
  useEffect(() => { if (item) { setValues(item.criterion_defs.map(() => "")); setReason(""); setPage(0); } }, [item?.id]);

  const complete = useMemo(() => values.length > 0 && values.every((v) => v !== ""), [values]);
  const acceptProposed = () => item && setValues(item.proposed_criterion_scores.map((v) => v));

  const save = async () => {
    if (!item || !complete) return;
    setBusy(true); setError(null);
    try {
      await api.post(`/api/queue/${item.id}/resolve`, { criterion_scores: values as number[], reason });
      const rest = items!.filter((x) => x.id !== item.id);
      setItems(rest); setI(Math.min(i, Math.max(0, rest.length - 1)));
      refreshQueue();
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not save"); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "TEXTAREA") return;
      if (e.key === "ArrowLeft") setI((x) => Math.max(0, x - 1));
      else if (e.key === "ArrowRight") setI((x) => Math.min((items?.length ?? 1) - 1, x + 1));
      else if (e.key.toLowerCase() === "a" && tag !== "INPUT") acceptProposed();
      else if (e.key === "Enter" && tag !== "INPUT") { e.preventDefault(); save(); }
      else if (/^[0-9]$/.test(e.key) && tag !== "INPUT" && item) {
        const focusIdx = 0; const max = item.criterion_defs[focusIdx].max_score;
        setValues((v) => v.map((x, j) => (j === focusIdx ? Math.min(max, Number(e.key)) : x)));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (error && !items) return <div className="page"><Notice kind="error">{error}</Notice></div>;
  if (!items) return <div className="page muted">Loading…</div>;
  if (!item) return <div className="page"><EmptyState title="Nothing needs you"><p>Every question has a mark. New escalations appear here as scripts are marked.</p><Link to="/submissions" className="btn btn-secondary">Back to submissions</Link></EmptyState></div>;

  return (
    <div>
      <div className="toolbar">
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <Link to={`/submissions/${item.submission_id}`} className="breadcrumb" style={{ margin: 0 }}>← {item.submission_label}</Link>
          <strong>Needs you</strong><span className="muted">{i + 1} of {items.length}</span>
        </div>
        <div className="help" aria-hidden>
          <span className="key">←</span> <span className="key">→</span> move · <span className="key">A</span> accept · <span className="key">1–9</span> first mark · <span className="key">↵</span> save &amp; next
        </div>
      </div>
      <div className="cols">
        <section>
          <div className="label-caps">Student</div>
          <p style={{ fontSize: 18, fontWeight: 600 }}>{item.submission_label}</p>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><div className="label-caps">Page {page + 1}</div><PagePager count={item.page_ids.length} current={page} onSelect={setPage} /></div>
          {item.page_ids[page] && <div className="page-view" style={{ maxHeight: 420, overflow: "auto" }}><img className="grayscale" src={`/api/pages/${item.page_ids[page]}`} alt={`Page ${page + 1}`} /></div>}
          <div className="label-caps" style={{ marginTop: 16 }}>What we read</div>
          <div className="page-view" style={{ padding: 12, fontSize: 15, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{item.transcription || <span className="tertiary">Nothing legible for this question.</span>}{item.workings && <div className="help" style={{ marginTop: 8 }}>Workings: {item.workings}</div>}</div>
          <div style={{ marginTop: 16 }}><Notice><strong>Why this is here</strong> — {item.reason}.{item.reviewer_note && <> Reviewer: “{item.reviewer_note}”.</>}</Notice></div>
        </section>
        <section>
          <div className="label-caps">Question {qLabel(item.q_id).replace("Q", "")}</div>
          {item.rationale && <p className="help">{item.rationale}</p>}
          <CriteriaReview defs={item.criterion_defs} proposed={item.proposed_criterion_scores} evidence={item.evidence} values={values} onChange={setValues} />
          <div className="field" style={{ marginTop: 16 }}>
            <label htmlFor="reason">Reason (kept with your correction)</label>
            <textarea id="reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Method is correct; arithmetic slip in the last line." />
          </div>
          {error && <Notice kind="error">{error}</Notice>}
          <div className="actions" style={{ marginTop: 16, paddingTop: 16, borderTop: "2px solid var(--color-divider)" }}>
            <Button size="lg" onClick={() => setI(Math.max(0, i - 1))} disabled={i === 0}>← Previous</Button>
            <Button size="lg" onClick={acceptProposed} keyHint="A">Accept proposed</Button>
            <Button size="lg" variant="primary" wide onClick={save} disabled={!complete || busy} keyHint="↵">{busy ? "Saving…" : "Save & next"}</Button>
          </div>
        </section>
      </div>
    </div>
  );
}

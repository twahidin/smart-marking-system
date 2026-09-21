import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Band, MarkPoint, QueueItem, ResolveBody } from "../api/types";
import { AllocationPicker, toggleAllocation } from "../components/AllocationPicker";
import { BandPicker } from "../components/BandPicker";
import { Button } from "../components/Button";
import { CriteriaReview } from "../components/CriteriaTable";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { PagePager } from "../components/PagePager";
import { qLabel } from "../lib/marks";

/** The allocations a v2 mark-scheme item is decided against: the scheme row's, or — for a part the scheme has
 *  no row for — the marker's own, which the API accepts in that case. */
function allocationsOf(item: QueueItem): MarkPoint[] {
  const row = item.scheme_row;
  if (row && "marks" in row) return row.marks;
  const p = item.proposed;
  if (p && "awarded" in p) return p.awarded.map((a) => ({ label: a.label, marks: a.marks }));
  return [];
}
const bandsOf = (item: QueueItem): Band[] => (item.scheme_row && "bands" in item.scheme_row ? item.scheme_row.bands : []);
const proposedGot = (item: QueueItem): string[] => (item.proposed && "awarded" in item.proposed ? item.proposed.awarded.filter((a) => a.got).map((a) => a.label) : []);
/** True when the key was typed into a text-like input (the digit belongs to the text, not the picker); a focused
 *  checkbox or radio still lets the digit keys toggle allocations. */
const typingField = (target: EventTarget | null): boolean =>
  target instanceof HTMLInputElement && !["checkbox", "radio"].includes(target.type);
const proposedBand = (item: QueueItem): string | null => (item.proposed && "band" in item.proposed ? item.proposed.band : null);
const proposedMarks = (item: QueueItem): number | null => (item.proposed && "marks" in item.proposed ? item.proposed.marks : null);
/** The most a part with nothing to tick can be given: the scheme row's total, else the marker's proposed total. */
const totalMax = (item: QueueItem): number => {
  const row = item.scheme_row;
  const rowMax = row && "marks" in row ? row.marks.reduce((s, m) => s + m.marks, 0) : 0;
  return Math.max(rowMax, item.proposed_total ?? 0);
};

export function Review() {
  const { refreshQueue } = useOutletContext<{ refreshQueue: () => void }>();
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [i, setI] = useState(0);
  const [values, setValues] = useState<(number | "")[]>([]);
  const [got, setGot] = useState<string[]>([]);
  const [band, setBand] = useState<string | null>(null);
  const [bandMarks, setBandMarks] = useState<number | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [decided, setDecided] = useState(false);
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
  const v2 = item?.marks_version === 2;
  const kind = v2 ? item!.scheme_kind ?? "mark_scheme" : null;
  useEffect(() => { if (item) { setValues(item.criterion_defs.map(() => "")); setGot([]); setBand(null); setBandMarks(null); setTotal(null); setDecided(false); setReason(""); setPage(0); } }, [item?.id]);

  const noAllocations = kind === "mark_scheme" && !!item && allocationsOf(item).length === 0;
  const complete = useMemo(() => {
    if (kind === "mark_scheme") return noAllocations ? total !== null : decided;
    if (kind === "rubric") return band !== null;
    return values.length > 0 && values.every((v) => v !== "");
  }, [kind, noAllocations, total, decided, band, values]);

  const acceptProposed = () => {
    if (!item) return;
    if (kind === "mark_scheme") { if (noAllocations) setTotal(item.proposed_total ?? 0); else { setGot(proposedGot(item)); setDecided(true); } }
    else if (kind === "rubric") { setBand(proposedBand(item)); setBandMarks(null); }
    else setValues(item.proposed_criterion_scores.map((v) => v));
  };
  const changeGot = (next: string[]) => { setGot(next); setDecided(true); };
  const changeBand = (b: string, marks?: number) => { setBand(b); setBandMarks(marks ?? null); };

  const save = async () => {
    if (!item || !complete) return;
    setBusy(true); setError(null);
    const body: ResolveBody = kind === "mark_scheme"
      ? noAllocations ? { total: total!, reason } : { allocations: allocationsOf(item).map((m) => ({ label: m.label, got: got.includes(m.label) })), reason }
      : kind === "rubric" ? { band: band!, ...(bandMarks === null ? {} : { marks: bandMarks }), reason } : { criterion_scores: values as number[], reason };
    try {
      await api.post(`/api/queue/${item.id}/resolve`, body);
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
      if (e.key === "ArrowLeft" && tag !== "INPUT") setI((x) => Math.max(0, x - 1));
      else if (e.key === "ArrowRight" && tag !== "INPUT") setI((x) => Math.min((items?.length ?? 1) - 1, x + 1));
      else if (e.key.toLowerCase() === "a" && tag !== "INPUT") acceptProposed();
      else if (e.key === "Enter" && tag !== "INPUT") { e.preventDefault(); save(); }
      else if (/^[1-9]$/.test(e.key) && item && kind === "mark_scheme" && !typingField(e.target)) { e.preventDefault(); changeGot(toggleAllocation(allocationsOf(item), got, Number(e.key))); }
      else if (/^[0-9]$/.test(e.key) && tag !== "INPUT" && item && !v2) {
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

  const heading = v2 ? (kind === "rubric" ? item.label ?? item.q_id : `Question ${item.label ?? qLabel(item.q_id)}`) : `Question ${qLabel(item.q_id).replace("Q", "")}`;
  const schemeRow = item.scheme_row;

  return (
    <div>
      <div className="toolbar">
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <Link to={`/submissions/${item.submission_id}`} className="breadcrumb" style={{ margin: 0 }}>← {item.submission_label}</Link>
          <strong>Needs you</strong><span className="muted">{i + 1} of {items.length}</span>
        </div>
        <div className="help" aria-hidden>
          <span className="key">←</span> <span className="key">→</span> move · <span className="key">A</span> accept · {kind !== "rubric" && <><span className="key">1–9</span> {kind === "mark_scheme" ? "toggle allocation" : "first mark"} · </>}<span className="key">↵</span> save &amp; next
        </div>
      </div>
      <div className="cols">
        <section>
          <div className="label-caps">Student</div>
          <p style={{ fontSize: 18, fontWeight: 600 }}>{item.submission_label}</p>
          {item.page_ids.length > 0
            ? <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><div className="label-caps">Page {page + 1}</div><PagePager count={item.page_ids.length} current={page} onSelect={setPage} /></div>
                {item.page_ids[page] && <div className="page-view" style={{ maxHeight: 420, overflow: "auto" }}><img className="grayscale" src={`/api/pages/${item.page_ids[page]}`} alt={`Page ${page + 1}`} /></div>}
              </>
            : <p className="help">{item.input_kind !== "files"
                // A mixed script has pages too, so an empty crop means they were deleted after marking.
                ? "Pages deleted after marking — the transcription below is what was read."
                : "Handed in as files — the transcription below is what was read."}</p>}
          <div className="label-caps" style={{ marginTop: 16 }}>What we read</div>
          <div className="page-view" style={{ padding: 12, fontSize: 15, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{item.transcription || <span className="tertiary">Nothing legible for this question.</span>}{item.workings && <div className="help" style={{ marginTop: 8 }}>Workings: {item.workings}</div>}</div>
          <div style={{ marginTop: 16 }}><Notice><strong>Why this is here</strong> — <span title={item.reason}>{item.reason_text ?? "Teacher to review"}</span>.{item.reviewer_note && <> Reviewer: “{item.reviewer_note}”.</>}</Notice></div>
        </section>
        <section>
          <div className="label-caps">{heading}</div>
          {v2 && item.question_text && <p style={{ marginTop: 4 }}>{item.question_text}</p>}
          {v2 && kind === "mark_scheme" && (
            <div className="callout" aria-label="Scheme answer">
              <span className="label-caps">Scheme answer</span>
              {schemeRow && "answer" in schemeRow
                ? <><div style={{ whiteSpace: "pre-wrap" }}>{schemeRow.answer || <span className="tertiary">—</span>}</div>{schemeRow.notes && <div className="help" style={{ marginTop: 4 }}>{schemeRow.notes}</div>}</>
                : <div className="help">No scheme row for this part — decide against the marker’s allocations.</div>}
            </div>
          )}
          {item.rationale && <p className="help">{item.rationale}</p>}
          {kind === "mark_scheme" && <AllocationPicker marks={allocationsOf(item)} got={got} onChange={changeGot} proposed={item.proposed && "awarded" in item.proposed ? item.proposed.awarded : undefined} total={total} onTotal={setTotal} max={totalMax(item)} />}
          {kind === "rubric" && <BandPicker bands={bandsOf(item)} value={band} marks={bandMarks} onChange={changeBand} proposed={proposedBand(item)} proposedMarks={proposedMarks(item)} />}
          {!v2 && <CriteriaReview defs={item.criterion_defs} proposed={item.proposed_criterion_scores} evidence={item.evidence} values={values} onChange={setValues} />}
          <div className="field" style={{ marginTop: 16 }}>
            <label htmlFor="reason">Reason (kept with your correction)</label>
            <textarea id="reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Method is correct; arithmetic slip in the last line." />
          </div>
          {error && <Notice kind="error">{error}</Notice>}
          <div className="actions" style={{ marginTop: 16, paddingTop: 16, borderTop: "2px solid var(--color-divider)" }}>
            <Button size="lg" onClick={() => setI(Math.max(0, i - 1))} disabled={i === 0}>← Previous</Button>
            <Button size="lg" onClick={acceptProposed} keyHint="A" disabled={v2 && !item.proposed}>Accept proposed</Button>
            <Button size="lg" variant="primary" wide onClick={save} disabled={!complete || busy} keyHint="↵" title={complete ? undefined : kind === "mark_scheme" ? (noAllocations ? "Type the mark, or accept the proposed total." : "Tick the allocations earned, or accept the proposed marks.") : kind === "rubric" ? "Pick a band." : undefined}>{busy ? "Saving…" : "Save & next"}</Button>
          </div>
        </section>
      </div>
    </div>
  );
}

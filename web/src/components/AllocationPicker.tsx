import { useState } from "react";
import type { AwardedAllocation, MarkPoint } from "../api/types";

type Props = {
  /** `got` holds allocation keys (see `allocationKeys`), not labels: a scheme may repeat a label. */
  marks: MarkPoint[]; got: string[]; onChange: (got: string[]) => void;
  proposed?: AwardedAllocation[]; disabled?: boolean;
  /** For a part with no allocations to tick: the typed total, its setter and the most it can be. */
  total?: number | null; onTotal?: (n: number) => void; max?: number;
};

const plural = (n: number) => `${n} mark${n === 1 ? "" : "s"}`;

/** Each allocation's identity: its label and which occurrence of that label it is ("B1#0", "B1#1"), because a mark
 *  scheme may give the same label twice — "B1 for comparing, B1 for reporting". */
export function allocationKeys(marks: MarkPoint[]): string[] {
  const seen = new Map<string, number>();
  return marks.map((m) => { const k = seen.get(m.label) ?? 0; seen.set(m.label, k + 1); return `${m.label}#${k}`; });
}

/** The marker's decision per allocation key: the k-th awarded entry with a label answers that label's k-th allocation. */
export function proposedByKey(marks: MarkPoint[], awarded: AwardedAllocation[] | undefined): Map<string, boolean> {
  const out = new Map<string, boolean>();
  if (!awarded) return out;
  const keys = allocationKeys(awarded.map((a) => ({ label: a.label, marks: a.marks })));
  const valid = new Set(allocationKeys(marks));
  awarded.forEach((a, i) => { if (valid.has(keys[i])) out.set(keys[i], a.got); });
  return out;
}

/** The keys the marker awarded — what the picker starts on. */
export const proposedKeys = (marks: MarkPoint[], awarded: AwardedAllocation[] | undefined): string[] =>
  [...proposedByKey(marks, awarded)].filter(([, g]) => g).map(([k]) => k);

/** `got` with the nth (1-based) allocation flipped — what the digit keys do in the review queue. */
export function toggleAllocation(marks: MarkPoint[], got: string[], n: number): string[] {
  const key = allocationKeys(marks)[n - 1];
  if (!key) return got;
  return got.includes(key) ? got.filter((k) => k !== key) : [...got, key];
}

export const allocationTotal = (marks: MarkPoint[], got: string[]): number => {
  const keys = allocationKeys(marks);
  return marks.reduce((s, m, i) => s + (got.includes(keys[i]) ? m.marks : 0), 0);
};
export const allocationMax = (marks: MarkPoint[]): number => marks.reduce((s, m) => s + m.marks, 0);

/** A mark box: shows the committed value, but keeps what is being typed (an empty box, a half-typed number) until
 *  it is a whole mark the caller accepts; on blur it snaps back to the committed value. */
function MarkBox({ value, max, label, disabled, onCommit }: { value: number; max: number; label: string; disabled: boolean; onCommit: (n: number) => boolean }) {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <input type="number" className="input mark-box" inputMode="numeric" min={0} max={max} step={1} aria-label={label} disabled={disabled}
      value={draft ?? String(value)} onFocus={(e) => e.target.select()} onBlur={() => setDraft(null)}
      onChange={(e) => {
        const raw = e.target.value;
        setDraft(raw);
        if (raw === "") return;
        const n = Math.floor(Number(raw));
        if (!Number.isFinite(n)) return;
        const clamped = Math.max(0, Math.min(max, n));
        if (onCommit(clamped) && clamped !== n) setDraft(String(clamped));
      }} />
  );
}

/** The mark-scheme row's allocations (M1 / A1 …), each with a mark box that starts at the marker's proposal: change
 *  any you disagree with. An allocation is all or nothing, so its box takes 0 or its full marks. */
export function AllocationPicker({ marks, got, onChange, proposed, disabled = false, total = null, onTotal, max = 0 }: Props) {
  const [partial, setPartial] = useState<string | null>(null);
  if (marks.length === 0) {
    const proposedTotal = proposed ? proposed.reduce((s, a) => s + (a.got ? a.marks : 0), 0) : null;
    return (
      <div>
        <p className="help" role="note">This part has no allocations — give the mark as a number, out of {max}.</p>
        <table className="table criteria picker" aria-label="Allocations">
          <thead><tr><th>Part</th><th className="num">Proposed</th><th className="num" style={{ width: 120 }}>Your mark</th></tr></thead>
          <tfoot><tr><td>Part total</td><td className="num">{proposedTotal === null ? "—" : `${proposedTotal} / ${max}`}</td>
            <td className="num"><MarkBox value={total ?? 0} max={max} label="Your mark" disabled={disabled} onCommit={(n) => { onTotal?.(n); return true; }} /> <span className="help">/ {max}</span></td></tr></tfoot>
        </table>
      </div>
    );
  }
  const keys = allocationKeys(marks);
  const proposedBy = proposedByKey(marks, proposed);
  const proposedTotal = proposed ? proposed.reduce((s, a) => s + (a.got ? a.marks : 0), 0) : null;
  const count = (label: string) => marks.filter((x) => x.label === label).length;
  const set = (key: string, on: boolean) => onChange(on ? (got.includes(key) ? got : [...got, key]) : got.filter((k) => k !== key));
  return (
    <div>
      {proposed && <p className="help" role="note">Each mark starts at the marker’s proposal — change any you disagree with.</p>}
      <table className="table criteria picker" aria-label="Allocations">
        <thead><tr><th>Allocation</th><th className="num">Proposed</th><th className="num" style={{ width: 120 }}>Your mark</th></tr></thead>
        <tbody>
          {marks.map((m, i) => {
            const key = keys[i];
            const on = got.includes(key);
            const p = proposedBy.get(key);
            const nth = count(m.label) > 1 ? ` (${Number(key.split("#").pop()) + 1} of ${count(m.label)})` : "";
            const changed = p !== undefined && p !== on;
            return (
              <tr key={key} className={changed ? "changed" : undefined}>
                <td>
                  <span style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 40 }}>
                    <strong>{m.label}</strong><span className="help">{plural(m.marks)}{nth}</span>
                    {i < 9 && <span className="key" aria-hidden title={`Press ${i + 1} to switch ${m.label} between 0 and ${m.marks}`}>{i + 1}</span>}
                  </span>
                </td>
                <td className="num">{p === undefined ? "—" : p ? m.marks : 0}</td>
                <td className="num">
                  <MarkBox value={on ? m.marks : 0} max={m.marks} label={`${m.label}${nth} · your mark out of ${m.marks}`} disabled={disabled}
                    onCommit={(n) => {
                      if (n === 0 || n === m.marks) { setPartial(null); set(key, n === m.marks); return true; }
                      setPartial(`${m.label} is all or nothing — give 0 or ${m.marks}.`); return false;
                    }} /> <span className="help">/ {m.marks}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot><tr><td>Part total</td><td className="num">{proposedTotal === null ? "—" : `${proposedTotal} / ${allocationMax(marks)}`}</td><td className="num" style={{ fontSize: 18 }} aria-label="Your mark">{allocationTotal(marks, got)} / {allocationMax(marks)}</td></tr></tfoot>
      </table>
      {partial && <p className="help" role="alert" style={{ color: "var(--color-error, #b3261e)" }}>{partial}</p>}
    </div>
  );
}

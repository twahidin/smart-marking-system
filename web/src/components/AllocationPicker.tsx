import { useState } from "react";
import type { AwardedAllocation, MarkPoint } from "../api/types";

type Props = {
  marks: MarkPoint[]; got: string[]; onChange: (got: string[]) => void;
  proposed?: AwardedAllocation[]; disabled?: boolean;
  /** For a part with no allocations to tick: the typed total, its setter and the most it can be. */
  total?: number | null; onTotal?: (n: number) => void; max?: number;
};

const plural = (n: number) => `${n} mark${n === 1 ? "" : "s"}`;

/** `got` with the nth (1-based) allocation flipped — what the digit keys do in the review queue. */
export function toggleAllocation(marks: MarkPoint[], got: string[], n: number): string[] {
  const m = marks[n - 1];
  if (!m) return got;
  return got.includes(m.label) ? got.filter((l) => l !== m.label) : [...got, m.label];
}

export const allocationTotal = (marks: MarkPoint[], got: string[]): number => marks.reduce((s, m) => s + (got.includes(m.label) ? m.marks : 0), 0);
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
  const proposedBy = new Map((proposed ?? []).map((a) => [a.label, a.got]));
  const proposedTotal = proposed ? proposed.reduce((s, a) => s + (a.got ? a.marks : 0), 0) : null;
  const set = (m: MarkPoint, on: boolean) => onChange(on ? (got.includes(m.label) ? got : [...got, m.label]) : got.filter((l) => l !== m.label));
  return (
    <div>
      {proposed && <p className="help" role="note">Each mark starts at the marker’s proposal — change any you disagree with.</p>}
      <table className="table criteria picker" aria-label="Allocations">
        <thead><tr><th>Allocation</th><th className="num">Proposed</th><th className="num" style={{ width: 120 }}>Your mark</th></tr></thead>
        <tbody>
          {marks.map((m, i) => {
            const on = got.includes(m.label);
            const p = proposedBy.get(m.label);
            const changed = p !== undefined && p !== on;
            return (
              <tr key={`${m.label}-${i}`} className={changed ? "changed" : undefined}>
                <td>
                  <span style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 40 }}>
                    <strong>{m.label}</strong><span className="help">{plural(m.marks)}</span>
                    {i < 9 && <span className="key" aria-hidden title={`Press ${i + 1} to switch ${m.label} between 0 and ${m.marks}`}>{i + 1}</span>}
                  </span>
                </td>
                <td className="num">{p === undefined ? "—" : p ? m.marks : 0}</td>
                <td className="num">
                  <MarkBox value={on ? m.marks : 0} max={m.marks} label={`${m.label} · your mark out of ${m.marks}`} disabled={disabled}
                    onCommit={(n) => {
                      if (n === 0 || n === m.marks) { setPartial(null); set(m, n === m.marks); return true; }
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

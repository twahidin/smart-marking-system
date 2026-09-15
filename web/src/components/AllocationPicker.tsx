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

/** The mark-scheme row's allocations as checkboxes (M1 / A1 …): tick what the student earned. The proposed
 *  column shows the marker's decision so the teacher can see where they differ. */
export function AllocationPicker({ marks, got, onChange, proposed, disabled = false, total = null, onTotal, max = 0 }: Props) {
  if (marks.length === 0) {
    const proposedTotal = proposed ? proposed.reduce((s, a) => s + (a.got ? a.marks : 0), 0) : null;
    return (
      <div>
        <p className="help" role="note">This part has no allocations to tick — give the mark as a number, out of {max}.</p>
        <table className="table criteria picker" aria-label="Allocations">
          <thead><tr><th>Part</th><th className="num">Proposed</th><th className="num" style={{ width: 120 }}>Your mark</th></tr></thead>
          <tfoot><tr><td>Part total</td><td className="num">{proposedTotal === null ? "—" : `${proposedTotal} / ${max}`}</td>
            <td className="num"><input type="number" className="input" inputMode="numeric" min={0} max={max} step={1} value={total ?? ""} disabled={disabled} aria-label="Your mark" style={{ width: 72, fontSize: 18, textAlign: "right" }}
              onChange={(e) => { const n = Math.floor(Number(e.target.value)); if (e.target.value !== "" && Number.isFinite(n) && onTotal) onTotal(Math.max(0, Math.min(max, n))); }} /> <span className="help">/ {max}</span></td></tr></tfoot>
        </table>
      </div>
    );
  }
  const proposedBy = new Map((proposed ?? []).map((a) => [a.label, a.got]));
  const proposedTotal = proposed ? proposed.reduce((s, a) => s + (a.got ? a.marks : 0), 0) : null;
  return (
    <table className="table criteria picker" aria-label="Allocations">
      <thead><tr><th>Allocation</th><th className="num">Proposed</th><th className="num" style={{ width: 88 }}>Your mark</th></tr></thead>
      <tbody>
        {marks.map((m, i) => {
          const on = got.includes(m.label);
          const p = proposedBy.get(m.label);
          return (
            <tr key={`${m.label}-${i}`}>
              <td>
                <label className="pick" style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 40, cursor: disabled ? "default" : "pointer" }}>
                  <input type="checkbox" checked={on} disabled={disabled} onChange={() => onChange(toggleAllocation(marks, got, i + 1))} aria-label={`${m.label} · ${plural(m.marks)}`} style={{ width: 18, height: 18 }} />
                  <strong>{m.label}</strong><span className="help">{plural(m.marks)}</span>
                  {i < 9 && <span className="key" aria-hidden>{i + 1}</span>}
                </label>
              </td>
              <td className="num">{p === undefined ? "—" : p ? "✓" : "✗"}</td>
              <td className="num">{on ? m.marks : 0}</td>
            </tr>
          );
        })}
      </tbody>
      <tfoot><tr><td>Part total</td><td className="num">{proposedTotal === null ? "—" : `${proposedTotal} / ${allocationMax(marks)}`}</td><td className="num" style={{ fontSize: 18 }} aria-label="Your mark">{allocationTotal(marks, got)} / {allocationMax(marks)}</td></tr></tfoot>
    </table>
  );
}

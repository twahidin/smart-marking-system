import { X } from "lucide-react";
import type { Band, RubricBands } from "../api/types";
import { bestBand, emptyBand, emptyCriterion, schemeTotal } from "../lib/scheme";

type Props = { rows: RubricBands[]; onChange: (rows: RubricBands[]) => void; disabled?: boolean };

/** The essay rubric: criteria, each with its bands (name, marks, descriptor). */
export function RubricTable({ rows, onChange, disabled = false }: Props) {
  const set = (i: number, patch: Partial<RubricBands>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const setBand = (i: number, k: number, patch: Partial<Band>) =>
    set(i, { bands: rows[i].bands.map((b, l) => (l === k ? { ...b, ...patch } : b)) });
  return (
    <table className="table editor-table" aria-label="Rubric table" aria-busy={disabled || undefined}>
      <thead><tr><th style={{ width: "22%" }}>Criterion</th><th>Bands</th><th className="num" style={{ width: 64 }}>Max</th><th style={{ width: 48 }} /></tr></thead>
      <tbody>
        {rows.map((r, i) => {
          const name = r.criterion.trim() || `criterion ${i + 1}`;
          return (
            <tr key={i}>
              <td><input className="input" disabled={disabled} aria-label={`Criterion ${i + 1} name`} placeholder="Organisation" value={r.criterion} onChange={(e) => set(i, { criterion: e.target.value })} /></td>
              <td>
                <table className="bands" aria-label={`Bands for ${name}`}>
                  <tbody>
                    {r.bands.map((b, k) => (
                      <tr key={k}>
                        <td className="band"><input className="input" disabled={disabled} aria-label={`Band ${k + 1} name for ${name}`} placeholder="A" value={b.band} onChange={(e) => setBand(i, k, { band: e.target.value })} /></td>
                        <td className="num"><input className="input" type="number" min={0} disabled={disabled} aria-label={`Band ${k + 1} marks for ${name}`} value={b.marks} onChange={(e) => setBand(i, k, { marks: e.target.value === "" ? 0 : Number(e.target.value) })} /></td>
                        <td><textarea className="input" rows={1} disabled={disabled} aria-label={`Band ${k + 1} descriptor for ${name}`} placeholder="Clear structure with a strong opening and close" value={b.descriptor} onChange={(e) => setBand(i, k, { descriptor: e.target.value })} /></td>
                        <td style={{ width: 40 }}><button type="button" className="btn btn-ghost btn-sm" disabled={disabled} aria-label={`Remove band ${k + 1} for ${name}`} onClick={() => set(i, { bands: r.bands.filter((_, l) => l !== k) })}><X size={14} /></button></td>
                      </tr>
                    ))}
                    <tr><td colSpan={4}><button type="button" className="btn btn-ghost btn-sm" disabled={disabled} aria-label={`Add band for ${name}`} onClick={() => set(i, { bands: [...r.bands, emptyBand()] })}>+ Add band</button></td></tr>
                  </tbody>
                </table>
              </td>
              <td className="num label" aria-label={`Max marks for ${name}`}>{bestBand(r)}</td>
              <td><button type="button" className="btn btn-ghost btn-sm" disabled={disabled} aria-label={`Remove criterion ${i + 1}`} onClick={() => onChange(rows.filter((_, j) => j !== i))}><X size={16} /></button></td>
            </tr>
          );
        })}
      </tbody>
      <tfoot><tr>
        <td colSpan={2}><button type="button" className="btn btn-ghost btn-sm" disabled={disabled} onClick={() => onChange([...rows, emptyCriterion()])}>+ Add criterion</button></td>
        <td className="num" aria-label="Rubric total">{schemeTotal("rubric", [], rows)}</td><td />
      </tr></tfoot>
    </table>
  );
}

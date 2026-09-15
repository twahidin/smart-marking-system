import { X } from "lucide-react";
import type { Criterion } from "../api/types";
import { rubricTotal, type Row } from "../lib/rubric";

export function CriteriaEditor({ rows, onChange }: { rows: Row[]; onChange: (rows: Row[]) => void }) {
  const set = (i: number, patch: Partial<Row>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <table className="table criteria">
      <thead><tr><th>Criterion</th><th>Description</th><th className="num">Max</th><th /></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td><input className="input" aria-label={`Criterion ${i + 1} id`} placeholder={`c${i + 1}`} value={r.id} onChange={(e) => set(i, { id: e.target.value })} /></td>
            <td><input className="input" aria-label={`Criterion ${i + 1} description`} placeholder="Correct method" value={r.description} onChange={(e) => set(i, { description: e.target.value })} /></td>
            <td className="num"><input className="input" type="number" min={1} aria-label={`Criterion ${i + 1} max marks`} value={r.max_score} onChange={(e) => set(i, { max_score: Number(e.target.value) })} /></td>
            <td><button type="button" className="btn btn-ghost btn-sm" aria-label={`Remove criterion ${i + 1}`} onClick={() => onChange(rows.filter((_, j) => j !== i))}><X size={16} /></button></td>
          </tr>
        ))}
      </tbody>
      <tfoot><tr><td colSpan={2}><button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange([...rows, { id: "", description: "", max_score: 1 }])}>+ Add criterion</button></td><td className="num">{rubricTotal(rows)}</td><td /></tr></tfoot>
    </table>
  );
}

export function CriteriaReview({ defs, proposed, evidence, values, onChange }:
  { defs: Criterion[]; proposed: number[]; evidence?: string; values: (number | "")[]; onChange: (v: (number | "")[]) => void }) {
  const total = values.reduce<number>((s, v) => s + (v === "" ? 0 : v), 0);
  const max = defs.reduce((s, d) => s + d.max_score, 0);
  return (
    <table className="table criteria">
      <thead><tr><th>Criterion</th><th className="num">Proposed</th><th className="num" style={{ width: 88 }}>Your mark</th></tr></thead>
      <tbody>
        {defs.map((d, i) => (
          <tr key={d.id} className={values[i] === "" ? "uncertain" : ""}>
            <td><strong>{d.description}</strong>{i === 0 && evidence && <div className="evidence">“{evidence}”</div>}</td>
            <td className="num">{proposed[i] ?? "?"} / {d.max_score}</td>
            <td className="num"><input className={`input ${values[i] === "" ? "needs" : ""}`} type="number" min={0} max={d.max_score} placeholder="?" aria-label={`Your mark for ${d.description}`} value={values[i]} data-criterion={i}
              onChange={(e) => onChange(values.map((v, j) => (j === i ? (e.target.value === "" ? "" : Math.max(0, Math.min(d.max_score, Number(e.target.value)))) : v)))} /></td>
          </tr>
        ))}
      </tbody>
      <tfoot><tr><td>Question total</td><td className="num">{proposed.reduce((s, p) => s + p, 0)} / {max}</td><td className="num" style={{ fontSize: 18 }}>{total} / {max}</td></tr></tfoot>
    </table>
  );
}

export function CriteriaReading({ defs, scores }: { defs: Criterion[]; scores: number[] }) {
  return (
    <table className="table criteria">
      <tbody>{defs.map((d, i) => <tr key={d.id}><td>{d.description}</td><td className="num">{scores[i] ?? "—"} / {d.max_score}</td></tr>)}</tbody>
    </table>
  );
}

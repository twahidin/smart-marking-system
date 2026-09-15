import { X } from "lucide-react";
import type { Question } from "../api/types";
import { emptyQuestion, qLabel } from "../lib/scheme";

/** Editable list of the paper's questions and parts: id (what the paper prints), text and marks. */
/** `disabled` locks every control (used while the paper is being read, so nothing typed is overwritten). */
export function QuestionsTable({ rows, onChange, disabled = false }: { rows: Question[]; onChange: (rows: Question[]) => void; disabled?: boolean }) {
  const set = (i: number, patch: Partial<Question>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const move = (i: number, d: -1 | 1) => {
    const j = i + d;
    if (j < 0 || j >= rows.length) return;
    const next = [...rows];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };
  const total = rows.reduce((s, r) => s + (Number.isInteger(Number(r.max_marks)) ? Number(r.max_marks) : 0), 0);
  return (
    <table className="table editor-table" aria-label="Questions table" aria-busy={disabled || undefined}>
      <thead><tr><th style={{ width: 72 }}>Label</th><th style={{ width: 96 }}>Id</th><th>Question</th><th className="num" style={{ width: 88 }}>Marks</th><th style={{ width: 132 }} /></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="label">{qLabel(r.q_id) || "—"}</td>
            <td className="id"><input className="input" disabled={disabled} aria-label={`Question ${i + 1} id`} placeholder="1a" value={r.q_id} onChange={(e) => set(i, { q_id: e.target.value })} /></td>
            <td><textarea className="input" rows={1} disabled={disabled} aria-label={`Question ${i + 1} text`} placeholder="Solve 2x + 3 = 7" value={r.text} onChange={(e) => set(i, { text: e.target.value })} /></td>
            <td className="num"><input className="input" type="number" min={0} disabled={disabled} aria-label={`Question ${i + 1} marks`} value={r.max_marks} onChange={(e) => set(i, { max_marks: e.target.value === "" ? 0 : Number(e.target.value) })} /></td>
            <td>
              <div className="actions" style={{ flexWrap: "nowrap", justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-ghost btn-sm" aria-label={`Move question ${i + 1} up`} disabled={disabled || i === 0} onClick={() => move(i, -1)}>↑</button>
                <button type="button" className="btn btn-ghost btn-sm" aria-label={`Move question ${i + 1} down`} disabled={disabled || i === rows.length - 1} onClick={() => move(i, 1)}>↓</button>
                <button type="button" className="btn btn-ghost btn-sm" aria-label={`Remove question ${i + 1}`} disabled={disabled} onClick={() => onChange(rows.filter((_, j) => j !== i))}><X size={16} /></button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot><tr>
        <td colSpan={3}><button type="button" className="btn btn-ghost btn-sm" disabled={disabled} onClick={() => onChange([...rows, emptyQuestion()])}>+ Add question</button></td>
        <td className="num" aria-label="Total marks">{total}</td><td />
      </tr></tfoot>
    </table>
  );
}

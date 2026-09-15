import { TriangleAlert, X } from "lucide-react";
import type { MarkPoint, MarkSchemeEntry, Question } from "../api/types";
import { emptyMarkPoint, emptySchemeRow, qLabel, rowTotal, schemeTotal } from "../lib/scheme";

type Props = { questions: Question[]; rows: MarkSchemeEntry[]; onChange: (rows: MarkSchemeEntry[]) => void };

const key = (id: string) => (id ?? "").trim();

/** The mark scheme, one row per question part, shown in the paper's order. A question with no row gets an
 *  amber "No scheme row" line with a button to add one; rows that match no question are listed last, flagged. */
export function MarkSchemeTable({ questions, rows, onChange }: Props) {
  const set = (i: number, patch: Partial<MarkSchemeEntry>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const setMark = (i: number, k: number, patch: Partial<MarkPoint>) =>
    set(i, { marks: rows[i].marks.map((m, l) => (l === k ? { ...m, ...patch } : m)) });
  const remove = (i: number) => onChange(rows.filter((_, j) => j !== i));

  const firstRowFor = new Map<string, number>();
  rows.forEach((r, i) => { if (!firstRowFor.has(key(r.q_id))) firstRowFor.set(key(r.q_id), i); });
  const questionIds = new Set(questions.map((q) => key(q.q_id)));
  const shownUnderQuestion = new Set<number>();
  const ordered: { q?: Question; i?: number }[] = [];
  for (const q of questions) {
    const i = firstRowFor.get(key(q.q_id));
    if (i !== undefined && !shownUnderQuestion.has(i)) { shownUnderQuestion.add(i); ordered.push({ q, i }); }
    else ordered.push({ q });
  }
  rows.forEach((_, i) => { if (!shownUnderQuestion.has(i)) ordered.push({ i }); });

  const renderRow = (i: number, q: Question | undefined, n: number) => {
    const r = rows[i];
    const id = key(r.q_id);
    const orphan = !q && !questionIds.has(id);
    const duplicate = !q && questionIds.has(id);
    const name = qLabel(id) || `row ${n}`;
    return (
      <tr key={`r${i}`} className={orphan || duplicate ? "warn" : ""}>
        <td className="id">
          <input className="input" aria-label={`Scheme row ${n} question id`} placeholder="1a" value={r.q_id} onChange={(e) => set(i, { q_id: e.target.value })} />
          {qLabel(id) !== id && <div className="help" style={{ marginTop: 4 }}>{qLabel(id)}</div>}
          {orphan && <div className="warn-note" style={{ marginTop: 6 }}><TriangleAlert size={14} strokeWidth={2.5} aria-hidden />{id ? `No question ${qLabel(id)} on the paper` : "Needs a question id"}</div>}
          {duplicate && <div className="warn-note" style={{ marginTop: 6 }}><TriangleAlert size={14} strokeWidth={2.5} aria-hidden />Second row for {qLabel(id)} — only the first is used</div>}
        </td>
        <td><textarea className="input" rows={1} aria-label={`Expected answer for ${name}`} placeholder="x = 2 (or equivalent)" value={r.answer} onChange={(e) => set(i, { answer: e.target.value })} /></td>
        <td>
          <div className="chips" aria-label={`Allocations for ${name}`}>
            {r.marks.map((m, k) => (
              <span className="chip" key={k}>
                <input className="input" aria-label={`Allocation ${k + 1} label for ${name}`} placeholder="M1" value={m.label} onChange={(e) => setMark(i, k, { label: e.target.value })} />
                <input className="input mk" type="number" min={0} aria-label={`Allocation ${k + 1} marks for ${name}`} value={m.marks} onChange={(e) => setMark(i, k, { marks: e.target.value === "" ? 0 : Number(e.target.value) })} />
                <button type="button" className="btn btn-ghost btn-sm" aria-label={`Remove allocation ${k + 1} for ${name}`} onClick={() => set(i, { marks: r.marks.filter((_, l) => l !== k) })}><X size={14} /></button>
              </span>
            ))}
            <button type="button" className="btn btn-ghost btn-sm" aria-label={`Add allocation for ${name}`} onClick={() => set(i, { marks: [...r.marks, emptyMarkPoint()] })}>+ Add</button>
          </div>
        </td>
        <td className="num label" aria-label={`Total for ${name}`}>{rowTotal(r)}</td>
        <td><input className="input" aria-label={`Notes for ${name}`} placeholder="Accept any correct method" value={r.notes} onChange={(e) => set(i, { notes: e.target.value })} /></td>
        <td><button type="button" className="btn btn-ghost btn-sm" aria-label={`Remove scheme row ${n}`} onClick={() => remove(i)}><X size={16} /></button></td>
      </tr>
    );
  };

  return (
    <table className="table editor-table" aria-label="Mark scheme table">
      <thead><tr><th style={{ width: 104 }}>Question &amp; part</th><th>Expected answer</th><th style={{ width: "30%" }}>Allocation</th><th className="num" style={{ width: 64 }}>Marks</th><th style={{ width: "22%" }}>Notes</th><th style={{ width: 48 }} /></tr></thead>
      <tbody>
        {ordered.map((o, n) => {
          if (o.i !== undefined) return renderRow(o.i, o.q, n + 1);
          const q = o.q!;
          return (
            <tr key={`q${n}`} className="warn">
              <td className="label">{qLabel(q.q_id) || "—"}</td>
              <td colSpan={4}>
                <span className="warn-note"><TriangleAlert size={14} strokeWidth={2.5} aria-hidden />No scheme row for {qLabel(q.q_id) || "this question"}</span>
                {q.text && <div className="help" style={{ marginTop: 4 }}>{q.text}</div>}
              </td>
              <td><button type="button" className="btn btn-ghost btn-sm" style={{ whiteSpace: "nowrap" }} onClick={() => onChange([...rows, emptySchemeRow(key(q.q_id))])}>Add row</button></td>
            </tr>
          );
        })}
      </tbody>
      <tfoot><tr>
        <td colSpan={3}><button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange([...rows, emptySchemeRow()])}>+ Add row</button></td>
        <td className="num" aria-label="Scheme total">{schemeTotal("mark_scheme", questions, rows)}</td><td colSpan={2} />
      </tr></tfoot>
    </table>
  );
}

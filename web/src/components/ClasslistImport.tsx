import { useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ClasslistPreviewRow, Student } from "../api/types";
import { Button } from "./Button";
import { Notice } from "./Notice";

const ISSUE: Record<string, string> = { missing_name: "Missing name", bad_reg_no: "Not a register number", duplicate_reg_no: "Duplicate register number" };

/** Drop a CSV → server preview (with per-row issues) → "Confirm classlist" replaces the roster. */
export function ClasslistImport({ classId, hasStudents, onSaved }: { classId: number; hasStudents: boolean; onSaved: (students: Student[], kept: number[]) => void }) {
  const [rows, setRows] = useState<ClasslistPreviewRow[] | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const pick = async (file: File) => {
    const form = new FormData(); form.append("file", file);
    setBusy(true);
    try { const p = await api.postForm<{ rows: ClasslistPreviewRow[]; errors: string[] }>(`/api/classes/${classId}/students/preview`, form); setRows(p.rows); setErrors(p.errors); }
    catch (e) { setErrors([e instanceof ApiError ? e.message : "Couldn't read that file."]); setRows(null); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    if (!rows) return;
    setBusy(true);
    try { const r = await api.put<{ students: Student[]; kept: number[] }>(`/api/classes/${classId}/students`, { rows: rows.map((x) => ({ reg_no: x.reg_no, name: x.name })) }); setRows(null); onSaved(r.students, r.kept); }
    catch (e) { setErrors([e instanceof ApiError ? e.message : "Couldn't save the classlist."]); }
    finally { setBusy(false); }
  };
  const clean = !!rows && rows.length > 0 && rows.every((r) => r.issues.length === 0);
  return (
    <div className="section">
      {!hasStudents && !rows && (
        <div className="empty">
          <h3>Upload the classlist</h3>
          <p className="help">A CSV with two columns: name, reg_no — one row per student. The header row can be in any case.</p>
        </div>
      )}
      <div className="actions">
        <Button variant={hasStudents ? "secondary" : "primary"} onClick={() => input.current?.click()} disabled={busy}>{hasStudents ? "Replace classlist" : "Choose CSV"}</Button>
        <input ref={input} type="file" accept=".csv,text/csv" hidden aria-label="Choose classlist file" onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f); e.target.value = ""; }} />
      </div>
      {errors.map((e) => <Notice key={e} kind="error">{e}</Notice>)}
      {rows && (
        <>
          <table className="table" style={{ marginTop: 16 }}><thead><tr><th className="num">#</th><th>Name</th><th>Issue</th></tr></thead>
            <tbody>{rows.map((r, i) => <tr key={i} className={r.issues.length ? "warn" : ""}><td className="num">{r.reg_no ?? r.raw_reg_no}</td><td>{r.name || "—"}</td><td>{r.issues.map((x) => ISSUE[x] ?? x).join(", ")}</td></tr>)}</tbody></table>
          <p className="help">{rows.length} student{rows.length === 1 ? "" : "s"}. {clean ? "Looks good." : "Fix the rows with issues in the file and upload it again."}</p>
          <div className="actions"><Button variant="primary" onClick={confirm} disabled={!clean || busy}>Confirm classlist</Button><Button variant="secondary" onClick={() => setRows(null)}>Cancel</Button></div>
        </>
      )}
    </div>
  );
}

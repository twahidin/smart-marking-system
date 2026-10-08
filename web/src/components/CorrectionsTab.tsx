import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Correction, CorrectionStatus } from "../api/types";
import { Notice } from "./Notice";

const WORD: Record<CorrectionStatus, string> = { submitted: "Waiting for the Marker", remarked: "Re-marked", accepted: "Accepted", overridden: "Overridden", rejected: "Rejected", released: "Released" };
const message = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong — try again.");

/** The corrections a class set's students have sent in: the Marker's re-mark beside each, to accept, override or
 *  reject, and one button to release what has been decided. */
export function CorrectionsTab({ classAssignmentId }: { classAssignmentId: number }) {
  const [rows, setRows] = useState<Correction[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [override, setOverride] = useState<Record<number, string>>({});
  const [released, setReleased] = useState<number | null>(null);
  const load = useCallback(
    () => api.get<Correction[]>(`/api/review/corrections?class_assignment_id=${classAssignmentId}`).then(setRows).catch((e) => setError(message(e))),
    [classAssignmentId],
  );
  useEffect(() => { setRows(null); setReleased(null); load(); }, [load]);
  const act = async (id: number, action: "accept" | "override" | "reject", body?: unknown) => {
    setError(null);
    try { await api.post(`/api/corrections/${id}/${action}`, body); await load(); } catch (e) { setError(message(e)); }
  };
  const release = async () => {
    setError(null);
    try {
      const r = await api.post<{ released: number }>(`/api/class-assignments/${classAssignmentId}/release-corrections`);
      setReleased(r.released); await load();
    } catch (e) { setError(message(e)); }
  };
  const ready = rows?.filter((r) => r.status === "accepted" || r.status === "overridden").length ?? 0;
  return (
    <section className="corrections" aria-label="Corrections">
      {error && <Notice kind="error">{error}</Notice>}
      {released !== null && <Notice kind="ok">{`Released ${released} correction${released === 1 ? "" : "s"}.`}</Notice>}
      <div className="actions" style={{ alignItems: "center" }}>
        <button type="button" className="btn btn-primary" onClick={release}>Release corrections</button>
        <span className="muted">{`${ready} ready to release`}</span>
      </div>
      {rows === null && !error && <p className="muted">Loading…</p>}
      {rows?.length === 0 && <p className="muted">No corrections yet.</p>}
      {rows?.map((r) => {
        const mx = r.remark_max ?? 0;
        const typed = override[r.id] ?? "";
        return (
          <article key={r.id} className="card correction">
            <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
              <strong>{`${r.submission_label} · ${r.q_id}`}</strong>
              <span className={`pill ${r.status === "released" ? "pill-outline" : "pill-neutral"}`}>{WORD[r.status]}</span>
            </header>
            <p className="muted">{`Reason given: ${r.reason}`}</p>
            {r.text && <p className="student-read">{r.text}</p>}
            {r.page_id && <img src={`/api/pages/${r.page_id}`} alt="The student's corrected working" style={{ maxWidth: "100%", borderRadius: 12 }} />}
            {r.error && <Notice kind="error">{`Re-mark failed · mark it yourself: ${r.error}`}</Notice>}
            {r.remark_total !== null && <p><strong>{`Re-marked ${r.remark_total} / ${mx}`}</strong></p>}
            {r.remark_note && r.remark_note.split("\n").map((line, i) => <p key={i} className="thought-note">{line}</p>)}
            {r.teacher_total !== null && <p>{`Your mark: ${r.teacher_total} / ${mx}`}</p>}
            {r.status !== "released" && r.status !== "rejected" && (
              <div className="actions" style={{ alignItems: "center" }}>
                {r.remark_total !== null && <button type="button" className="btn btn-primary btn-sm" onClick={() => act(r.id, "accept")}>{`Accept ${r.remark_total} / ${mx}`}</button>}
                <label className="help">Override mark
                  <input aria-label="Override mark" className="input" type="number" min={0} max={mx} step={0.5} value={typed} onChange={(e) => setOverride({ ...override, [r.id]: e.target.value })} />
                </label>
                <button type="button" className="btn btn-secondary btn-sm" disabled={typed === ""} onClick={() => act(r.id, "override", { total: Number(typed) })}>Override</button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => {
                  const reason = window.prompt("Why is this not accepted? (the student sees this)") ?? "";
                  if (reason.trim()) act(r.id, "reject", { reason: reason.trim() });
                }}>Reject</button>
              </div>
            )}
          </article>
        );
      })}
    </section>
  );
}

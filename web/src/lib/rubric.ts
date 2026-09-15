import type { Criterion } from "../api/types";

export type Row = Criterion;

export const emptyRow = (): Row => ({ id: "", description: "", max_score: 1 });

export function rubricTotal(rows: Row[]): number {
  return rows.reduce((s, r) => s + (Number(r.max_score) || 0), 0);
}

export function validateRows(rows: Row[]): string | null {
  if (rows.length === 0) return "Add at least one criterion.";
  for (const r of rows) {
    if (!r.description.trim()) return "Every criterion needs a description.";
    if (!Number.isInteger(r.max_score) || r.max_score < 1) return "Max marks must be a whole number of 1 or more.";
  }
  return null;
}

export function rowsToRubricJson(rows: Row[]): string {
  const criterion_defs = rows.map((r, i) => ({ id: r.id.trim() || `c${i + 1}`, description: r.description.trim(), max_score: Number(r.max_score) }));
  return JSON.stringify({ criterion_defs });
}

export function jsonToRows(json: string): Row[] {
  const parsed = JSON.parse(json);
  if (!parsed || !Array.isArray(parsed.criterion_defs)) throw new Error("Expected {\"criterion_defs\": [...]}");
  return parsed.criterion_defs.map((c: any, i: number) => ({
    id: String(c.id ?? `c${i + 1}`), description: String(c.description ?? ""), max_score: Number(c.max_score ?? 0),
  }));
}

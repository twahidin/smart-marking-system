// Shapes, totals, matching and validation for an assignment's question list and its mark scheme / rubric.
// Mirrors src/sms/schemas/scheme.py (q_label, scheme_total) so the editor shows what the server will store.
import type { Band, Criterion, MarkPoint, MarkSchemeEntry, Question, Rubric, RubricBands, SchemeKind } from "../api/types";
import { rowsToRubricJson, validateRows, type Row } from "./rubric";

export type { Band, MarkPoint, MarkSchemeEntry, Question, RubricBands, SchemeKind };
export type Scheme = MarkSchemeEntry[] | RubricBands[];

export const kindLabel: Record<SchemeKind, string> = { mark_scheme: "Maths / Science — mark scheme", rubric: "Essay — rubric", criteria: "Quick mark" };

export const emptyQuestion = (): Question => ({ q_id: "", text: "", max_marks: 1 });
export const emptySchemeRow = (q_id = ""): MarkSchemeEntry => ({ q_id, answer: "", marks: [], notes: "" });
export const emptyMarkPoint = (): MarkPoint => ({ label: "", marks: 1 });
export const emptyCriterion = (): RubricBands => ({ criterion: "", bands: [emptyBand()] });
export const emptyBand = (): Band => ({ band: "", marks: 1, descriptor: "" });

const Q_ID = /^(q)?(\d+)([a-z])?([ivx]+)?$/i;
const ROMAN = /^[ivx]+$/i;

/** Teacher-facing label for a question id: "1a" → "1(a)", "2bii" → "2(b)(ii)", "4iii" → "4(iii)", "q1" → "Q1".
 *  Anything else (already formatted, free text) is returned unchanged. */
export function qLabel(qId: string): string {
  const raw = (qId ?? "").trim();
  const m = Q_ID.exec(raw);
  if (!m) return raw;
  const [, prefix, number, letter, roman] = m;
  const suffix = (letter ?? "") + (roman ?? "");
  const parts = suffix.length > 1 && ROMAN.test(suffix)
    ? [suffix.toLowerCase()] // "4iii": one roman part, not the letter "i" plus "ii"
    : [letter, roman].filter((p): p is string => !!p).map((p) => p.toLowerCase());
  return (prefix ? "Q" : "") + number + parts.map((p) => `(${p})`).join("");
}

const int = (v: unknown) => (Number.isInteger(Number(v)) ? Number(v) : 0);
const key = (id: string) => (id ?? "").trim();

export const rowTotal = (row: MarkSchemeEntry): number => (row.marks ?? []).reduce((s, m) => s + int(m.marks), 0);
export const bestBand = (c: RubricBands): number => (c.bands ?? []).reduce((s, b) => Math.max(s, int(b.marks)), 0);

/** Total marks the assignment is out of — same rule as the server's scheme_total. */
export function schemeTotal(kind: SchemeKind, questions: Question[], scheme: Scheme): number {
  if (kind === "rubric") return (scheme as RubricBands[]).reduce((s, c) => s + bestBand(c), 0);
  if (kind === "mark_scheme") {
    const rows = new Map<string, number>();
    for (const r of scheme as MarkSchemeEntry[]) if (!rows.has(key(r.q_id))) rows.set(key(r.q_id), rowTotal(r));
    if (questions.length === 0) return Array.from(rows.values()).reduce((s, v) => s + v, 0);
    return questions.reduce((s, q) => s + (rows.get(key(q.q_id)) ?? int(q.max_marks)), 0);
  }
  return questions.reduce((s, q) => s + int(q.max_marks), 0);
}

/** q_ids of questions that have no mark-scheme row, in paper order. */
export function unmatchedQuestions(questions: Question[], scheme: MarkSchemeEntry[]): string[] {
  const rows = new Set(scheme.map((r) => key(r.q_id)));
  return questions.map((q) => key(q.q_id)).filter((id) => !rows.has(id));
}

/** Indexes of mark-scheme rows whose q_id is not on the paper (blank ids included). */
export function orphanRows(questions: Question[], scheme: MarkSchemeEntry[]): number[] {
  const ids = new Set(questions.map((q) => key(q.q_id)));
  return scheme.map((r, i) => (ids.has(key(r.q_id)) ? -1 : i)).filter((i) => i >= 0);
}

function listLabels(ids: string[]): string {
  const labels = ids.map(qLabel);
  if (labels.length === 1) return labels[0];
  if (labels.length <= 3) return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
  return `${labels.slice(0, 3).join(", ")} and ${labels.length - 3} more`;
}

function validateQuestions(questions: Question[]): string | null {
  const seen = new Set<string>();
  for (const q of questions) {
    const id = key(q.q_id);
    if (!id) return "Every question needs an id, like 1a.";
    if (seen.has(id)) return `Question ids must be unique — ${qLabel(id)} appears twice.`;
    seen.add(id);
    if (!Number.isInteger(Number(q.max_marks)) || Number(q.max_marks) < 0) return `Marks for ${qLabel(id)} must be a whole number of 0 or more.`;
  }
  return null;
}

/** Why the assignment cannot be saved yet, in one plain sentence — or null when it can. */
export function validateTemplate(kind: SchemeKind, questions: Question[], scheme: Scheme, criteria: Row[]): string | null {
  if (kind === "criteria") return validateRows(criteria);
  if (questions.length === 0) return "Add at least one question.";
  const qProblem = validateQuestions(questions);
  if (qProblem) return qProblem;
  if (kind === "mark_scheme") {
    for (const r of scheme as MarkSchemeEntry[]) {
      const id = key(r.q_id);
      if (!id) return "Every scheme row needs a question id.";
      for (const m of r.marks ?? []) {
        if (!key(m.label)) return `Every allocation for ${qLabel(id)} needs a label, like M1.`;
        if (!Number.isInteger(Number(m.marks)) || Number(m.marks) < 0) return `Allocation marks for ${qLabel(id)} must be a whole number of 0 or more.`;
      }
    }
    const missing = unmatchedQuestions(questions, scheme as MarkSchemeEntry[]);
    if (missing.length === 1) return `Add a scheme row for ${qLabel(missing[0])}.`;
    if (missing.length > 1) return `Add scheme rows for ${listLabels(missing)}.`;
    return null;
  }
  const rows = scheme as RubricBands[];
  if (rows.length === 0) return "Add at least one criterion.";
  for (const c of rows) {
    const name = key(c.criterion);
    if (!name) return "Every criterion needs a name.";
    if (!c.bands || c.bands.length === 0) return `Add at least one band to ${name}.`;
    for (const b of c.bands) {
      if (!key(b.band)) return `Every band for ${name} needs a name.`;
      if (!Number.isInteger(Number(b.marks)) || Number(b.marks) < 0) return `Band marks for ${name} must be a whole number of 0 or more.`;
    }
  }
  return null;
}

const slug = (s: string) => s.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

function uniqueIds(defs: Criterion[]): Criterion[] {
  const seen = new Map<string, number>();
  return defs.map((d) => {
    const base = d.id || "c";
    const n = (seen.get(base) ?? 0) + 1;
    seen.set(base, n);
    return { ...d, id: n === 1 ? base : `${base}-${n}` };
  });
}

/** The batch-2 `rubric` the API still requires for every kind: for a mark scheme one criterion per question
 *  (worth its scheme row, or the paper's marks), for a rubric one per criterion (worth its best band). An empty
 *  draft gets a single zero-mark placeholder so it can be stored before the paper is read. */
export function placeholderRubric(kind: SchemeKind, questions: Question[], scheme: Scheme, criteria: Row[]): Rubric {
  let defs: Criterion[];
  if (kind === "criteria") {
    defs = criteria.length ? (JSON.parse(rowsToRubricJson(criteria)) as Rubric).criterion_defs : [];
  } else if (kind === "mark_scheme") {
    const rows = new Map<string, number>();
    for (const r of scheme as MarkSchemeEntry[]) if (!rows.has(key(r.q_id))) rows.set(key(r.q_id), rowTotal(r));
    defs = questions.filter((q) => key(q.q_id)).map((q) => ({
      id: key(q.q_id), description: (q.text || "").trim().slice(0, 200) || qLabel(q.q_id),
      max_score: rows.get(key(q.q_id)) ?? int(q.max_marks),
    }));
  } else {
    defs = (scheme as RubricBands[]).filter((c) => key(c.criterion)).map((c) => ({
      id: slug(c.criterion) || "c", description: c.criterion.trim(), max_score: bestBand(c),
    }));
  }
  if (defs.length === 0) defs = [{ id: "draft", description: "Draft", max_score: 0 }];
  return { criterion_defs: uniqueIds(defs) };
}

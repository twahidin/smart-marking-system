export type Subject = "math" | "language" | "science";
export type SubmissionStatus = "uploaded" | "queued" | "marking" | "needs_you" | "done" | "failed";

export interface ModelSpec { id: string; label: string; vision: boolean }
export interface ProviderSpec {
  id: string; label: string; transport: string; base_url: string | null; mode: string;
  default_model: string; default_rpm: number; models: ModelSpec[]; key_url: string; note: string; base_url_editable: boolean;
}
export interface Settings {
  provider: string; model: string; base_url: string | null; extractor_model: string | null;
  rpm_limit: number; confidence_threshold: number; has_key: boolean; key_hint: string; auto_reflect: boolean;
}
export interface Check { ok: boolean; latency_ms: number; error: string | null }
export interface ProbeResult { text: Check; vision: Check }

export interface Criterion { id: string; description: string; max_score: number }
export interface Rubric { criterion_defs: Criterion[] }

export type SchemeKind = "criteria" | "mark_scheme" | "rubric";
export interface Question { q_id: string; text: string; max_marks: number }
export interface MarkSchemeEntry { q_id: string; answer: string; marks: { label: string; marks: number }[]; notes: string }
export interface RubricBands { criterion: string; bands: { band: string; marks: number; descriptor: string }[] }
export interface AssignmentTemplate {
  id: number; title: string; subject: Subject; context: string; rubric: Rubric;
  criteria_count: number; total_marks: number; times_used: number; created_at: string; updated_at: string;
  scheme_kind: SchemeKind; questions: Question[]; scheme: MarkSchemeEntry[] | RubricBands[]; paper_page_ids: number[];
}

export interface SubmissionRow {
  id: number; label: string; subject: Subject; page_count: number; status: SubmissionStatus; created_at: string;
  total: number | null; total_upper: number | null; total_max: number | null; needs_you_qids: string[];
  assignment_id: number | null; assignment_title: string | null;
}
export interface Page { id: number; page_index: number; width: number; height: number }
export interface Mark {
  q_id: string; criterion_scores: number[]; total: number; max: number; confidence: number | null;
  evidence: string; rationale: string; escalated: boolean; reason: string | null; queue_id: number | null;
  teacher_scores: number[] | null;
}
export interface Feedback {
  summary: string; strengths: string[];
  per_question_comments: { q_id: string; comment: string; suggested_action: string }[];
  improvement_plan: string[]; next_steps: string[];
}
export interface Job { status: "queued" | "running" | "done" | "failed"; attempts: number; error: string | null; started_at: string | null; finished_at: string | null }
export interface SubmissionDetail {
  id: number; label: string; subject: Subject; context: string; status: SubmissionStatus; created_at: string;
  rubric: Rubric; pages: Page[]; marks: Mark[]; totals: { total: number; total_upper: number; total_max: number } | null;
  feedback: Feedback | null; job: Job | null; assignment_id: number | null; assignment_title: string | null;
}
export interface QueueItem {
  id: number; submission_id: number; submission_label: string; q_id: string; reason: string; created_at: string;
  transcription: string; workings: string; proposed_criterion_scores: number[]; proposed_total: number | null;
  evidence: string; rationale: string; reviewer_note: string; criterion_defs: Criterion[]; page_ids: number[];
}
export interface Note { id: number; subject: string; note: string; status: string; created_at?: string }
export interface Exemplar { id: number; subject: string; topic: string; q_id: string; answer_text: string; awarded: number; max_score: number; why_it_matters: string; status: string }
export interface ReflectionRun { id: number; subject: string; lookback_days: number; proposed_notes: number; started_at: string; finished_at: string | null; error: string | null }
export interface ReflectionRuns { runs: ReflectionRun[]; pending: string[] }
export type Stats = Record<string, { count: number; mean_latency_ms: number; total_tokens_in: number; total_tokens_out: number }>;

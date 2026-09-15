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
  delete_pages_after_marking: boolean;
}
export interface Check { ok: boolean; latency_ms: number; error: string | null }
export interface ProbeResult { text: Check; vision: Check }

export interface Criterion { id: string; description: string; max_score: number }
export interface Rubric { criterion_defs: Criterion[] }

export type SchemeKind = "criteria" | "mark_scheme" | "rubric";
export interface Question { q_id: string; text: string; max_marks: number }
export interface MarkPoint { label: string; marks: number }
export interface MarkSchemeEntry { q_id: string; answer: string; marks: MarkPoint[]; notes: string }
export interface Band { band: string; marks: number; descriptor: string }
export interface RubricBands { criterion: string; bands: Band[] }
export interface AssignmentTemplate {
  id: number; title: string; subject: Subject; context: string; rubric: Rubric;
  criteria_count: number; total_marks: number; times_used: number; created_at: string; updated_at: string;
  scheme_kind: SchemeKind; questions: Question[]; scheme: MarkSchemeEntry[] | RubricBands[];
  paper_page_ids: number[]; scheme_page_ids: number[];
  delete_pages_after_marking: boolean | null; effective_delete_pages: boolean;
}
export interface AssignmentBody {
  title: string; subject: Subject; context: string; rubric: Rubric; scheme_kind: SchemeKind;
  questions: Question[]; scheme: MarkSchemeEntry[] | RubricBands[]; delete_pages_after_marking: boolean | null;
}
export type ExtractJobStatus = "queued" | "running" | "done" | "failed" | null;
export interface ExtractState { status: ExtractJobStatus; error: string | null; job_id: number | null }
export interface ExtractStatus { paper: ExtractState; scheme: ExtractState }

export interface SubmissionRow {
  id: number; label: string; subject: Subject; page_count: number; status: SubmissionStatus; created_at: string;
  total: number | null; total_upper: number | null; total_max: number | null; needs_you_qids: string[];
  assignment_id: number | null; assignment_title: string | null;
}
export interface Page { id: number; page_index: number; width: number; height: number; deleted?: boolean }
export interface Mark {
  q_id: string; criterion_scores: number[]; total: number; max: number; confidence: number | null;
  evidence: string; rationale: string; escalated: boolean; reason: string | null; reason_text?: string | null; queue_id: number | null;
  teacher_scores: number[] | null;
}
/** One awarded allocation of a v2 mark-scheme part (M1 / A1 …). */
export interface AwardedAllocation { label: string; marks: number; got: boolean; why?: string }
/** The scheme row a v2 part was marked against: a mark-scheme row or a rubric criterion with its bands. */
export type PartScheme = { answer: string; marks: MarkPoint[]; notes?: string } | { criterion: string; bands: Band[] };
/** Teacher's resolution of a v2 part, as stored from the review queue. */
export type TeacherMark = { allocations: AwardedAllocation[]; total: number } | { band: string; marks: number; total: number };
/** One row of a v2 (per-part) run: a question part (mark scheme) or a criterion (rubric). */
export interface Part {
  q_id: string; label: string; question_text: string; scheme: PartScheme | null;
  extracted: string; workings: string; illegible: boolean;
  awarded?: AwardedAllocation[]; band?: string; descriptor_met?: string;
  total: number; max: number; justification: string; in_scheme: boolean; confidence: number | null;
  /** `reason` is the pipeline's code (e.g. "not in scheme"); `reason_text` is the sentence the teacher reads. */
  escalated: boolean; reason: string | null; reason_text: string | null; queue_id: number | null; teacher: TeacherMark | null;
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
  /** 1 = criteria per question (slice 1); 2 = per-part marks against a mark scheme / rubric (`parts`). */
  marks_version?: 1 | 2; parts?: Part[]; scheme_kind?: SchemeKind | null;
  pages_deleted?: boolean; run_id?: string | null; marked_at?: string | null;
}
export interface QueueItem {
  id: number; submission_id: number; submission_label: string; q_id: string; reason: string; reason_text?: string; created_at: string;
  transcription: string; workings: string; proposed_criterion_scores: number[]; proposed_total: number | null;
  evidence: string; rationale: string; reviewer_note: string; criterion_defs: Criterion[]; page_ids: number[];
  /** v2 items: the part's label and question, the scheme row it was marked against and the stored mark as the proposal. */
  marks_version?: 1 | 2; scheme_kind?: "mark_scheme" | "rubric"; label?: string; question_text?: string;
  scheme_row?: MarkSchemeEntry | RubricBands | null; proposed?: ProposedPart | null;
}
export type ProposedPart = { q_id: string; awarded: AwardedAllocation[]; total: number; justification?: string } | { criterion: string; band: string; marks: number; justification?: string };
/** Resolve bodies: v1 sends one mark per criterion; v2 sends the allocations got / lost, or the band. */
export type ResolveBody = { criterion_scores: number[]; reason: string } | { allocations: { label: string; got: boolean }[]; reason: string } | { band: string; reason: string };
export interface Note { id: number; subject: string; note: string; status: string; created_at?: string }
export interface Exemplar { id: number; subject: string; topic: string; q_id: string; answer_text: string; awarded: number; max_score: number; why_it_matters: string; status: string }
export interface ReflectionRun { id: number; subject: string; lookback_days: number; proposed_notes: number; started_at: string; finished_at: string | null; error: string | null }
export interface ReflectionRuns { runs: ReflectionRun[]; pending: string[] }
export type Stats = Record<string, { count: number; mean_latency_ms: number; total_tokens_in: number; total_tokens_out: number }>;

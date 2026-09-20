export type Subject = "math" | "language" | "science" | "mt" | "computing";
/** The script's language, for Mother Tongue only: Chinese, Malay or Tamil. */
export type MtLanguage = "zh" | "ms" | "ta";
/** Every subject's saved model default; null = Auto, so the subject follows Settings. */
export type SubjectModels = Record<Subject, { provider: string; model: string; extractor_model: string | null } | null>;
export type SubmissionStatus = "uploaded" | "queued" | "marking" | "needs_you" | "done" | "failed";

export interface ModelSpec { id: string; label: string; vision: boolean; /** saved by the teacher under “My models”, not part of the curated list */ custom?: boolean }
export interface ProviderSpec {
  id: string; label: string; transport: string; base_url: string | null; mode: string;
  default_model: string; default_rpm: number; models: ModelSpec[]; key_url: string; note: string; base_url_editable: boolean;
  /** the provider lets the teacher save their own model ids (TokenRouter, OpenRouter) */
  custom_models: boolean;
}
export interface Settings {
  provider: string; model: string; base_url: string | null; extractor_model: string | null;
  rpm_limit: number; confidence_threshold: number; has_key: boolean; key_hint: string; keys?: Record<string, string>; auto_reflect: boolean;
  delete_pages_after_marking: boolean;
  /** Telegram: linked once a bot token is saved *and* the teacher has pressed /start in the chat. */
  telegram_linked: boolean; telegram_bot_hint: string; telegram_chat_id: string | null;
  telegram_instant: boolean; /** "HH:MM" in `timezone` */ telegram_daily_time: string; timezone: string; app_url: string | null;
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
  /** The script's language — set for subject `mt`, null for every other subject. */
  language: MtLanguage | null;
  criteria_count: number; total_marks: number; times_used: number; created_at: string; updated_at: string;
  submission_count?: number; pending_count?: number; class_assignment_count?: number;
  scheme_kind: SchemeKind; questions: Question[]; scheme: MarkSchemeEntry[] | RubricBands[];
  paper_page_ids: number[]; scheme_page_ids: number[];
  delete_pages_after_marking: boolean | null; effective_delete_pages: boolean;
  /** The model this assignment pins itself to; all three null = Auto (it follows Settings). */
  provider: string | null; model: string | null; extractor_model: string | null;
  /** What will actually run: the assignment's own model, or the one saved under Settings. */
  effective_model: EffectiveModel;
}
export interface EffectiveModel {
  provider: string; model: string; extractor_model: string | null;
  /** Where it came from: the assignment's own pin, its subject's default, or Settings. */
  source: "assignment" | "subject" | "settings";
}
export interface AssignmentBody {
  title: string; subject: Subject; context: string; rubric: Rubric; scheme_kind: SchemeKind;
  questions: Question[]; scheme: MarkSchemeEntry[] | RubricBands[]; delete_pages_after_marking: boolean | null;
  /** Required when the subject is `mt`; sent as null for every other subject. */
  language?: MtLanguage | null;
  /** Omitted or null = Auto. A PUT that leaves these out clears a saved override, so every caller sends them. */
  provider?: string | null; model?: string | null; extractor_model?: string | null;
}
export type ExtractJobStatus = "queued" | "running" | "done" | "failed" | null;
export interface ExtractState { status: ExtractJobStatus; error: string | null; job_id: number | null }
export interface ExtractStatus { paper: ExtractState; scheme: ExtractState }

export interface SubmissionRow {
  id: number; label: string; subject: Subject; page_count: number;
  /** Program files handed in beside (or instead of) the pages. */
  file_count: number;
  status: SubmissionStatus; created_at: string;
  total: number | null; total_upper: number | null; total_max: number | null; needs_you_qids: string[];
  assignment_id: number | null; assignment_title: string | null;
  /** `"4E2 · #12"` when the script was handed in against a class assignment, else null. */
  class_label?: string | null; class_assignment_id?: number | null;
}
export interface Page { id: number; page_index: number; width: number; height: number; deleted?: boolean }
/** How a script arrived: photos or PDFs, program files, or both. */
export type InputKind = "pages" | "files" | "mixed";
/** One program file handed in: `text_rendered` is what the marker read (null for a .sb3 or before a run),
 *  `matched` says whether the transcription actually cited it, `deleted` that its bytes are gone. */
export interface SubmissionFile {
  id: number; name: string; kind: "py" | "sb3" | "xlsx"; size: number;
  text_rendered: string | null; deleted: boolean; matched: boolean;
}
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
  rubric: Rubric; pages: Page[]; input_kind: InputKind; files: SubmissionFile[];
  marks: Mark[]; totals: { total: number; total_upper: number; total_max: number } | null;
  feedback: Feedback | null; job: Job | null; assignment_id: number | null; assignment_title: string | null;
  /** 1 = criteria per question (slice 1); 2 = per-part marks against a mark scheme / rubric (`parts`). */
  marks_version?: 1 | 2; parts?: Part[]; scheme_kind?: SchemeKind | null;
  pages_deleted?: boolean; run_id?: string | null; marked_at?: string | null; marked_by?: string | null;
  class_label?: string | null; class_assignment_id?: number | null;
}
export interface QueueItem {
  id: number; submission_id: number; submission_label: string; q_id: string; reason: string; reason_text?: string; created_at: string;
  transcription: string; workings: string; proposed_criterion_scores: number[]; proposed_total: number | null;
  evidence: string; rationale: string; reviewer_note: string; criterion_defs: Criterion[]; page_ids: number[];
  /** Why `page_ids` may be empty without the pages having been deleted: the script came in as files. */
  input_kind: InputKind;
  /** v2 items: the part's label and question, the scheme row it was marked against and the stored mark as the proposal. */
  marks_version?: 1 | 2; scheme_kind?: "mark_scheme" | "rubric"; label?: string; question_text?: string;
  scheme_row?: MarkSchemeEntry | RubricBands | null; proposed?: ProposedPart | null;
}
export type ProposedPart = { q_id: string; awarded: AwardedAllocation[]; total: number; justification?: string } | { criterion: string; band: string; marks: number; justification?: string };
/** Resolve bodies: v1 sends one mark per criterion; v2 sends the allocations got / lost (or a bare total when the part has
 *  none to tick), or the band (with marks 0 to award nothing for a criterion the rubric has no bands for). */
export type ResolveBody = { criterion_scores: number[]; reason: string } | { allocations: { label: string; got: boolean }[]; reason: string } | { total: number; reason: string } | { band: string; marks?: number; reason: string };
export interface Note { id: number; subject: string; note: string; status: string; created_at?: string }
export interface Exemplar { id: number; subject: string; topic: string; q_id: string; answer_text: string; awarded: number; max_score: number; why_it_matters: string; status: string }
export interface ReflectionRun { id: number; subject: string; lookback_days: number; proposed_notes: number; started_at: string; finished_at: string | null; error: string | null }
export interface ReflectionRuns { runs: ReflectionRun[]; pending: string[] }
export type Stats = Record<string, { count: number; mean_latency_ms: number; total_tokens_in: number; total_tokens_out: number }>;

/* ---- classes, classlists and class assignments (slice 2) ---- */
export interface ClassRow { id: number; name: string; code: string; student_count: number; open_assignments: number; archived_at: string | null; created_at: string; updated_at: string }
export interface Student { id: number; reg_no: number; name: string; submissions: number; last_seen_at: string | null }
export interface ClasslistPreviewRow { reg_no: number | null; raw_reg_no: string; name: string; issues: ("missing_name" | "bad_reg_no" | "duplicate_reg_no")[] }
export type ClassAssignmentStatus = "draft" | "open" | "released";
export interface ClassAssignment {
  id: number; class_id: number; template_id: number; title: string; due_at: string | null; status: ClassAssignmentStatus;
  derived_status: ClassAssignmentStatus | "marking"; allow_student_uploads: boolean; released_at: string | null;
  template_deleted: boolean; subject: Subject | null; scheme_kind: SchemeKind | null; submission_count: number; created_at: string; updated_at: string;
}
export type RosterStatus = "not_handed_in" | "handed_in" | "marking" | "failed" | "needs_you" | "ready" | "released";
export interface RosterRow { student_id: number; reg_no: number; name: string; submission_id: number | null; pages: number; handed_in_at: string | null; late: boolean; source: "teacher" | "student" | null; status: RosterStatus; total: number | null; total_upper: number | null; total_max: number | null; needs_you_parts: string[] }
export interface Roster { rows: RosterRow[]; counts: Record<"not_handed_in" | "handed_in" | "marking" | "needs_you" | "ready", number> }
export interface ClassAssignmentDetail extends ClassAssignment { roster: Roster }

/* ---- insights (slice 3): the numbers computed from the marks, plus the AI narrative over them ---- */
export interface InsightsBucket { from: number; to: number; n: number }
/** A mark-scheme allocation (M1 / A1 …) or a rubric band, and how many marked scripts lost it. */
export interface InsightsAllocation { label: string; lost: number }
export interface InsightsPart {
  q_id: string; label: string; max: number; /** scripts with a settled mark for this part */ attempted: number;
  mean_pct: number | null; full: number; zero: number; allocations: InsightsAllocation[];
  not_in_scheme: number; illegible: number; pending: number;
}
/** One allocation the class lost most often: `lost` of the `of` scripts with a settled mark for the part. */
export interface InsightsMostLost { q_id: string; label: string; lost: number; of: number }
export interface InsightsStudent { student_id: number; reg_no: number; name: string; total: number; max: number; weak_parts: string[] }
export interface InsightsStats {
  n_students: number; n_marked: number; n_pending: number;
  totals: { mean: number | null; median: number | null; max: number; buckets: InsightsBucket[] };
  /** scheme order */ parts: InsightsPart[]; /** weakest first */ weakest: string[];
  most_lost: InsightsMostLost[]; students: InsightsStudent[];
}
export interface InsightsGap { part_ids: string[]; title: string; what_went_wrong: string; students_affected: number }
export interface InsightsRecommendation { title: string; detail: string; part_ids: string[] }
/** Who to follow up, by register number — the model never sees a name, so the app joins them back. */
export interface InsightsSupport { reg_nos: number[]; focus: string }
export interface InsightsReport {
  summary: string; strengths: string[]; gaps: InsightsGap[];
  recommendations: InsightsRecommendation[]; students_to_support: InsightsSupport[];
}
export interface InsightsPayload {
  stats: InsightsStats; /** null until a narrative has been generated */ report: InsightsReport | null;
  n_marked: number; provider: string | null; model: string | null; generated_at: string | null;
  /** why the last generate failed (typically no API key saved) — the numbers are still there */ error: string | null;
  job: { status: Job["status"] } | null;
}

/* ---- student-facing (class code + register number session) ---- */
export type StudentAssignmentStatus = "to_hand_in" | "handed_in" | "checking" | "feedback_ready";
export interface StudentMe { class_name: string; code: string; student_name: string; reg_no: number }
export interface StudentAssignment { id: number; title: string; due_at: string | null; status: StudentAssignmentStatus; handed_in_at: string | null; pages: number; allow_student_uploads: boolean }
export interface StudentFeedback { summary: string; strengths: string[]; improvement_plan: string[]; next_steps: string[]; total: number | null; max: number | null; questions: { label: string; mark: number; max: number; comment: string; try_next: string; transcription: string }[]; pages: number[] }
export interface StudentAssignmentDetail extends StudentAssignment {
  feedback: StudentFeedback | null;
  subject: Subject;
  /** True for Computing: the hand-in page offers *Add files* beside the photo buttons. */
  accepts_files: boolean;
}

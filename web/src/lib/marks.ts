import type { SubmissionStatus } from "../api/types";

export function totalLabel(t: { total: number; total_upper: number; total_max: number } | null | undefined): string {
  if (!t) return "—";
  return t.total === t.total_upper ? `${t.total} / ${t.total_max}` : `${t.total}–${t.total_upper} / ${t.total_max}`;
}

export function qLabel(qId: string): string {
  return qId.replace(/^q/i, "Q");
}

export function statusLabel(status: SubmissionStatus, needsYou: string[]): string {
  switch (status) {
    case "uploaded": return "Uploaded";
    case "queued": return "Waiting to mark";
    case "marking": return "Marking";
    case "needs_you": return needsYou.length ? `Needs you · ${needsYou.map(qLabel).join(", ")}` : "Needs you";
    case "done": return "Done";
    case "failed": return "Failed";
  }
}

export const pillClass: Record<SubmissionStatus, string> = {
  uploaded: "pill-outline", queued: "pill-neutral", marking: "pill-neutral", needs_you: "pill-amber", done: "pill-ink", failed: "pill-failed",
};

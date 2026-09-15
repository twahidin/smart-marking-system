import { TriangleAlert } from "lucide-react";
import type { SubmissionStatus } from "../api/types";
import { pillClass, statusLabel } from "../lib/marks";

export function StatusPill({ status, needsYou = [] }: { status: SubmissionStatus; needsYou?: string[] }) {
  return (
    <span className={`pill ${pillClass[status]}`} data-status={status}>
      {status === "needs_you" && <TriangleAlert size={14} strokeWidth={2.5} aria-hidden />}
      {statusLabel(status, needsYou)}
    </span>
  );
}

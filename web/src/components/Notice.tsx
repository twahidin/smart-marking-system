import { Check, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

export function Notice({ kind = "amber", children }: { kind?: "amber" | "ok" | "error"; children: ReactNode }) {
  return (
    <div className={`notice ${kind === "ok" ? "notice-ok" : kind === "error" ? "notice-error" : ""}`} role={kind === "ok" ? "status" : "alert"}>
      {kind === "ok" ? <Check size={18} strokeWidth={2.5} aria-hidden /> : <TriangleAlert size={18} strokeWidth={2.5} aria-hidden />}
      <div>{children}</div>
    </div>
  );
}

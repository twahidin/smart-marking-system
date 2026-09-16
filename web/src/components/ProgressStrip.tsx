import type { Roster } from "../api/types";

export type StripBucket = keyof Roster["counts"];

const CELLS: { id: StripBucket; label: string }[] = [
  { id: "not_handed_in", label: "Not handed in" }, { id: "handed_in", label: "Handed in" }, { id: "marking", label: "Marking" },
  { id: "needs_you", label: "Needs you" }, { id: "ready", label: "Ready" },
];

/** Five progress cells; clicking one filters the roster to that bucket, clicking it again clears the filter. */
export function ProgressStrip({ counts, filter, onFilter }: { counts: Roster["counts"]; filter: StripBucket | null; onFilter: (f: StripBucket | null) => void }) {
  return (
    <div className="strip" role="group" aria-label="Progress">
      {CELLS.map((c) => (
        <button key={c.id} type="button" className={`strip-cell ${c.id === "needs_you" && counts.needs_you > 0 ? "amber" : ""}`}
          aria-pressed={filter === c.id} onClick={() => onFilter(filter === c.id ? null : c.id)}>
          <strong>{counts[c.id]}</strong><span>{c.label}</span>
        </button>
      ))}
    </div>
  );
}

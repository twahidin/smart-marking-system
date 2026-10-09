import type { CSSProperties } from "react";
import type { Crew, RoomDesk, Stage } from "../api/types";
import { ART, FRAMES } from "./art";
import { Frames } from "./Frames";
import type { DeviceTier } from "./useDeviceTier";
import { useFilm } from "./useFilm";

export const CREW_OF: Record<Stage, Crew | null> = { read: "reader", mark: "marker", check: "checker", feedback: null, done: null };
const NAME: Record<Crew, string> = { reader: "Reader", marker: "Marker", checker: "Checker" };
/** Where each desk sits on the room image, as percentages of its box. */
const SPOT: Record<Crew, { left: string; top: string }> = { reader: { left: "39%", top: "24%" }, marker: { left: "50%", top: "36%" }, checker: { left: "60%", top: "46%" } };

export function RoomScene2D({ desks, tier, onPick }: { desks: RoomDesk[]; tier: DeviceTier; onPick: (submissionId: number, crew: Crew, label: string) => void }) {
  // Oldest script first, so a crew member's tag is stable between refreshes; the rest at that desk show as "+N".
  const byCrew = new Map<Crew, RoomDesk[]>();
  for (const d of [...desks].sort((a, b) => Date.parse(a.since) - Date.parse(b.since) || a.submission_id - b.submission_id)) {
    const c = CREW_OF[d.stage];
    if (c) byCrew.set(c, [...(byCrew.get(c) ?? []), d]);
  }
  const busy = desks.some((d) => d.stage === "read");
  const [filmOn] = useFilm(tier);
  return (
    <div className="room-scene">
      <img src={ART.room} alt="The marking room: a paper sorter feeds a conveyor to three desks where the Reader, Marker and Checker work" />
      {tier === "2d" && filmOn && <Frames frames={FRAMES.room} />}
      {tier === "2d" && busy && <span className="room-paper slide" aria-hidden />}
      <div className="room-tags">
        {(["reader", "marker", "checker"] as Crew[]).map((crew) => {
          const queue = byCrew.get(crew) ?? [];
          const d = queue[0];
          const more = queue.length - 1;
          const text = d ? `${d.label}${more > 0 ? ` +${more}` : ""}` : null;
          return (
            <button key={crew} type="button" className={`room-tag ${tier === "2d" && d ? "bob" : ""} tag-${crew}`}
              style={{ "--tag-left": SPOT[crew].left, "--tag-top": SPOT[crew].top } as CSSProperties}
              aria-label={text ? `${NAME[crew]} · ${text}` : `${NAME[crew]} · desk empty`} disabled={!d}
              onClick={() => d && onPick(d.submission_id, crew, d.label)}>
              <i className={`dot dot-${crew}`} aria-hidden /><span className="room-tag-text">{NAME[crew]}{text ? ` · ${text}` : " · waiting"}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

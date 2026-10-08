import type { Crew, RoomDesk, Stage } from "../api/types";
import type { DeviceTier } from "./useDeviceTier";

const CREW_OF: Record<Stage, Crew | null> = { read: "reader", mark: "marker", check: "checker", feedback: null, done: null };
const NAME: Record<Crew, string> = { reader: "Reader", marker: "Marker", checker: "Checker" };
/** Where each desk sits on the room image, as percentages of its box. */
const SPOT: Record<Crew, { left: string; top: string }> = { reader: { left: "39%", top: "24%" }, marker: { left: "50%", top: "36%" }, checker: { left: "60%", top: "46%" } };

export function RoomScene2D({ desks, tier, onPick }: { desks: RoomDesk[]; tier: DeviceTier; onPick: (submissionId: number, crew: Crew, label: string) => void }) {
  const byCrew = new Map<Crew, RoomDesk>();
  for (const d of desks) { const c = CREW_OF[d.stage]; if (c && !byCrew.has(c)) byCrew.set(c, d); }
  const busy = desks.some((d) => d.stage === "read");
  return (
    <div className="room-scene">
      <img src="/art/room.jpg" alt="The marking room: a paper sorter feeds a conveyor to three desks where the Reader, Marker and Checker work" />
      {tier === "2d" && busy && <span className="room-paper slide" aria-hidden />}
      {(["reader", "marker", "checker"] as Crew[]).map((crew) => {
        const d = byCrew.get(crew);
        return (
          <button key={crew} type="button" className={`room-tag ${tier === "2d" && d ? "bob" : ""} tag-${crew}`} style={SPOT[crew]}
            aria-label={d ? `${NAME[crew]} · ${d.label}` : `${NAME[crew]} · desk empty`} disabled={!d}
            onClick={() => d && onPick(d.submission_id, crew, d.label)}>
            <i className={`dot dot-${crew}`} aria-hidden />{NAME[crew]}{d ? ` · ${d.label}` : " · waiting"}
          </button>
        );
      })}
    </div>
  );
}

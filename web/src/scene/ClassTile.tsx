import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { ClassRow } from "../api/types";
import { subjectColor, type TileKey } from "../lib/format";
import { FILM, SUBJECT_TILE } from "./art";
import { Dots, Flag, Glow } from "./effects";
import type { DeviceTier } from "./useDeviceTier";
import { useInView } from "./useInView";

/** Where the doorway, the teacher and the flag sit on every classroom tile (percentages of the tile). */
const DOOR = { left: "26%", top: "66%" }; const TEACHER = { left: "28%", top: "40%" }; const FLAG = { left: "70%", top: "26%" };

/** At most this many tile films play at once; any tile past the cap shows its still. */
const MAX_FILMS = 6;
const playing = new Set<number>();
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

/** True while this tile holds one of the limited film slots. A tile claims a slot when it becomes eligible and releases it
 *  when it stops being eligible or unmounts, which lets a waiting tile take it. */
function useFilmSlot(id: number, eligible: boolean): boolean {
  const [, bump] = useState(0);
  useEffect(() => { const l = () => bump((n) => n + 1); listeners.add(l); return () => { listeners.delete(l); }; }, []);
  // Claim a slot after every render while eligible and without one, so a tile past the cap takes the next slot that frees.
  useEffect(() => {
    if (eligible && !playing.has(id) && playing.size < MAX_FILMS) { playing.add(id); notify(); }
  });
  useEffect(() => {
    if (!eligible) return;
    return () => { if (playing.delete(id)) notify(); };
  }, [id, eligible]);
  return eligible && playing.has(id);
}

export function ClassTile({ c, tier, labels, film }: { c: ClassRow; tier: DeviceTier; labels: boolean; film: boolean }) {
  // A legacy subject outside the known set (older templates stored 'english') gets the plain classroom.
  const key: TileKey = c.subject && c.subject in SUBJECT_TILE ? c.subject : "general";
  const [broken, setBroken] = useState(false);
  const [hover, setHover] = useState(false);
  const live = tier !== "static";
  const boxRef = useRef<HTMLDivElement>(null);
  const inView = useInView(boxRef);
  const wantsFilm = live && film && !!FILM[key] && !broken && inView;
  const playingFilm = useFilmSlot(c.id, wantsFilm);
  const sub = `${c.code} · ${c.student_count} student${c.student_count === 1 ? "" : "s"} · ${c.open_assignments} open${c.needs_you > 0 ? ` · ${c.needs_you} need you` : ""}`;
  const dot = c.subject && c.subject in subjectColor ? subjectColor[c.subject] : "var(--oak)";
  return (
    <Link to={`/classes/${c.id}`} className="tile" aria-label={`${c.name} · ${sub}`}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onFocus={() => setHover(true)} onBlur={() => setHover(false)}>
      <div className="tile-box" ref={boxRef}>
        <img src={SUBJECT_TILE[key]} alt="" loading="lazy" />
        {playingFilm && <video className="scene-film" src={FILM[key]} poster={SUBJECT_TILE[key]} preload="metadata" autoPlay muted loop playsInline aria-hidden="true" onError={() => setBroken(true)} />}
        {live && c.open_assignments > 0 && <Glow {...DOOR} size="22%" />}
        {live && c.marking > 0 && <Dots {...TEACHER} />}
        {live && c.needs_you > 0 && <Flag {...FLAG} />}
      </div>
      <div className="tile-tag">
        <b><i className="dot" style={{ background: dot }} aria-hidden />{c.name}</b>
        <span className={labels || hover ? "on" : "off"} data-testid="tile-sub">{sub}</span>
      </div>
    </Link>
  );
}

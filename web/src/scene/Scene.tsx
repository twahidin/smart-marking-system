import { Fragment, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { DeviceTier } from "./useDeviceTier";
import { Frames, type Frame } from "./Frames";
import { useFilm } from "./useFilm";
import { useSceneLabels } from "./useSceneLabels";
import { useTour } from "./useTour";

export interface Hotspot { id: string; left: string; top: string; label: string; sub?: string; color?: string; href?: string; onPick?: () => void }
export interface Cue { name: string; key: number }
export type { Frame };

interface Props { name: string; art: string; film?: string; frames?: Frame[]; alt: string; hotspots: Hotspot[]; effects?: ReactNode; cue?: Cue | null; tier: DeviceTier; tourable?: boolean; children?: ReactNode }

/** A painted scene with hover/tap labels, a Show labels switch, a 3 s Tour, optional film loop or frame cycle, ambient effects and one-shot cues. */
export function Scene({ name, art, film, frames, alt, hotspots, effects, cue, tier, tourable = true, children }: Props) {
  const [labels, setLabels] = useSceneLabels(tier);
  const [filmOn, setFilmOn] = useFilm(tier);
  const tour = useTour(hotspots.length);
  const [hover, setHover] = useState<string | null>(null);
  const [pinned, setPinned] = useState<Record<string, boolean>>({});
  const [filmBroken, setFilmBroken] = useState(false);
  const [cueClass, setCueClass] = useState("");

  useEffect(() => {
    if (!cue || tier === "static") { setCueClass(""); return; }
    setCueClass(`cue-${cue.name}`);
    const t = setTimeout(() => setCueClass(""), 1500);
    return () => clearTimeout(t);
  }, [cue?.key, cue?.name, tier]);

  const live = tier !== "static";
  const showFilm = live && filmOn && !!film && !filmBroken;
  const showFrames = live && filmOn && !!frames?.length;
  const isOn = (h: Hotspot, i: number) => labels || hover === h.id || !!pinned[h.id] || tour.index === i;
  const hint = tour.running ? "Touring, one spot every 3 seconds." : labels ? "Every label is open." : "Hover a spot to see its label; tap to keep it open.";

  return (
    <section className="scene card" aria-label={name}>
      <div className="scene-controls">
        <span className="muted scene-hint">{hint}</span>
        <button type="button" className={`btn btn-sm ${labels ? "btn-primary" : "btn-secondary"}`} aria-pressed={labels} onClick={() => setLabels(!labels)}>Show labels</button>
        {tourable && hotspots.length > 0 && <button type="button" className={`btn btn-sm ${tour.running ? "btn-primary" : "btn-secondary"}`} aria-pressed={tour.running} onClick={tour.toggle}>Tour · 3 s</button>}
        {live && (film || !!frames?.length) && <button type="button" className={`btn btn-sm ${filmOn ? "btn-primary" : "btn-secondary"}`} aria-pressed={filmOn} onClick={() => setFilmOn(!filmOn)}>Film</button>}
      </div>
      <div className={`scene-box ${cueClass}`}>
        <img src={art} alt={alt} />
        {showFilm && <video className="scene-film" src={film} poster={art} autoPlay muted loop playsInline aria-hidden="true" onError={() => setFilmBroken(true)} />}
        {showFrames && <Frames frames={frames} />}
        {live && effects}
        {hotspots.map((h, i) => {
          const handlers = { onMouseEnter: () => setHover(h.id), onMouseLeave: () => setHover((v) => (v === h.id ? null : v)), onFocus: () => setHover(h.id), onBlur: () => setHover((v) => (v === h.id ? null : v)) };
          const style = { left: h.left, top: h.top };
          return (
            <Fragment key={h.id}>
              {h.href
                ? <Link to={h.href} className="scene-spot" style={style} aria-label={h.label} aria-description={h.sub} {...handlers} />
                : <button type="button" className={`scene-spot ${pinned[h.id] ? "pinned" : ""}`} style={style} aria-label={h.label} aria-description={h.sub} aria-pressed={!!pinned[h.id]} {...handlers}
                    onClick={() => { setPinned((p) => ({ ...p, [h.id]: !p[h.id] })); h.onPick?.(); }} />}
              <div className={`scene-tag ${isOn(h, i) ? "on" : "off"}`} style={style} aria-hidden="true" data-testid={`tag-${h.id}`}>
                <b>{h.color && <i className="dot" style={{ background: h.color }} />}{h.label}</b>
                {h.sub && <span>{h.sub}</span>}
              </div>
            </Fragment>
          );
        })}
      </div>
      {children}
    </section>
  );
}

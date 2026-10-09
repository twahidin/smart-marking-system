/** A regenerated detail of a painting (a lifted pen, a lit lamp) that fades in over the still; left/top/width are % of the picture's box. */
export interface Frame { src: string; left: string; top: string; width: string; delay: number }

/** The frame cycle: each patch fades in for ~1.5 s of a 6 s loop, offset by its delay. Render only on the live tier, inside a position: relative box. */
export function Frames({ frames }: { frames?: Frame[] }) {
  if (!frames?.length) return null;
  return <>{frames.map((f) => <img key={f.src} className="fx fx-frame" src={f.src} alt="" aria-hidden="true" loading="lazy" style={{ left: f.left, top: f.top, width: f.width, animationDelay: `${f.delay}s` }} />)}</>;
}

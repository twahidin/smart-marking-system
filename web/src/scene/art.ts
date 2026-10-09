import type { TileKey } from "../lib/format";
import type { Frame } from "./Frames";

export const ART = { desk: "/art/desk.jpg", review: "/art/review.jpg", library: "/art/library.jpg", school: "/art/school.jpg", room: "/art/room.jpg", hero: "/art/hero.jpg" } as const;
export const SUBJECT_TILE: Record<TileKey, string> = {
  math: "/art/tile-math.jpg", language: "/art/tile-language.jpg", science: "/art/tile-science.jpg",
  mt: "/art/tile-mt.jpg", computing: "/art/tile-computing.jpg", general: "/art/tile-general.jpg",
};
/** 5 s muted loops made from the tiles; a scene without an entry shows its still. The three large scenes have none:
 *  at full width the clips look soft next to the paintings, so they cycle through regenerated frames (FRAMES) instead. */
export const FILM: Partial<Record<keyof typeof ART | TileKey, string>> = {
  math: "/art/film/tile-math.mp4", language: "/art/film/tile-language.mp4", science: "/art/film/tile-science.mp4",
  mt: "/art/film/tile-mt.mp4", computing: "/art/film/tile-computing.mp4", general: "/art/film/tile-general.mp4",
};
/** Regenerated details cut from second renders of each painting (scripts/scene-frame.py), positioned in % of the scene.
 *  Each fades in over the still for ~1.5 s of a 6 s loop; the Film switch turns the cycle off. */
export const FRAMES: Partial<Record<keyof typeof ART, Frame[]>> = {
  review: [
    { src: "/art/frames/review-b.png", left: "40.08%", top: "30.92%", width: "15.04%", delay: 0 },
    { src: "/art/frames/review-c.png", left: "40.96%", top: "33.82%", width: "14.12%", delay: 3 },
  ],
  desk: [
    { src: "/art/frames/desk-b.png", left: "44.75%", top: "34.65%", width: "7.21%", delay: 0 },
    { src: "/art/frames/desk-c.png", left: "28.42%", top: "35.55%", width: "29.08%", delay: 3 },
  ],
  library: [
    { src: "/art/frames/library-b.png", left: "40.38%", top: "51.45%", width: "10.88%", delay: 0 },
    { src: "/art/frames/library-c.png", left: "41.29%", top: "54.35%", width: "12.54%", delay: 3 },
  ],
  room: [
    { src: "/art/frames/room-b.png", left: "47.19%", top: "36.41%", width: "11.72%", delay: 0 },
    { src: "/art/frames/room-c.png", left: "46.48%", top: "43.14%", width: "14.14%", delay: 2 },
    { src: "/art/frames/room-d.png", left: "36.41%", top: "28.15%", width: "12.11%", delay: 4 },
  ],
  hero: [
    { src: "/art/frames/hero-b.png", left: "31%", top: "36.91%", width: "21.15%", delay: 0 },
    { src: "/art/frames/hero-c.png", left: "49.27%", top: "32.55%", width: "15.52%", delay: 3 },
  ],
};

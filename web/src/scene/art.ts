import type { TileKey } from "../lib/format";

export const ART = { desk: "/art/desk.jpg", review: "/art/review.jpg", library: "/art/library.jpg", school: "/art/school.jpg" } as const;
export const SUBJECT_TILE: Record<TileKey, string> = {
  math: "/art/tile-math.jpg", language: "/art/tile-language.jpg", science: "/art/tile-science.jpg",
  mt: "/art/tile-mt.jpg", computing: "/art/tile-computing.jpg", general: "/art/tile-general.jpg",
};
/** 5 s muted loops made from the stills; a scene without an entry shows its still. */
export const FILM: Partial<Record<keyof typeof ART | TileKey, string>> = {
  desk: "/art/film/desk.mp4", review: "/art/film/review.mp4", library: "/art/film/library.mp4",
  math: "/art/film/tile-math.mp4", language: "/art/film/tile-language.mp4", science: "/art/film/tile-science.mp4",
  mt: "/art/film/tile-mt.mp4", computing: "/art/film/tile-computing.mp4", general: "/art/film/tile-general.mp4",
};

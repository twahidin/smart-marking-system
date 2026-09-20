import { downscale } from "./image";

// Only formats browsers can actually render in an <img>. HEIC (Safari-only, and often reported with an
// empty MIME type) and PDF get the filename card instead of a broken thumbnail.
const THUMBNAIL_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export const canThumbnail = (file: Pick<File, "type">): boolean => THUMBNAIL_TYPES.has(file.type);

/** What a Computing hand-in may carry beside photos, and what every accept list appends for it. */
export const PROGRAM_ACCEPT = ".py,.sb3,.xlsx,.zip";

const PROGRAM_EXTS = PROGRAM_ACCEPT.split(",");

/** Judged by extension, not MIME type: browsers report .sb3 and .xlsx inconsistently (often as
 *  application/octet-stream, sometimes as nothing at all), but the name is always there. */
export const isProgramFile = (file: Pick<File, "name">): boolean =>
  PROGRAM_EXTS.some((ext) => file.name.toLowerCase().endsWith(ext));

const KB = 1024, MB = 1024 * 1024;

/** A size as a teacher would say it: "512 B", "1.2 KB", "3.5 MB". */
export function fmtSize(bytes: number): string {
  if (bytes < KB) return `${Math.round(bytes)} B`;
  if (bytes < MB) return `${(bytes / KB).toFixed(1)} KB`;
  return `${(bytes / MB).toFixed(1)} MB`;
}

/** Everything leaving the browser goes through here: phone and camera photos are 3–5 MB each and the
 *  marker only needs ~2000 px, so they are shrunk first. PDFs (split server-side) and program files
 *  (marked byte for byte) are passed through untouched — re-encoding either would destroy them. */
export async function prepareUploads(files: File[]): Promise<File[]> {
  return Promise.all(files.map((f) => (canThumbnail(f) ? downscale(f) : Promise.resolve(f))));
}

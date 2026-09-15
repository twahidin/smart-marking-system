// Only formats browsers can actually render in an <img>. HEIC (Safari-only, and often reported with an
// empty MIME type) and PDF get the filename card instead of a broken thumbnail.
const THUMBNAIL_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export const canThumbnail = (file: Pick<File, "type">): boolean => THUMBNAIL_TYPES.has(file.type);

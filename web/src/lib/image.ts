// Phone photos are 3–5 MB each; the marker only needs ~2000 px on the long edge. Shrinking on the phone
// keeps a 20-page hand-in under a few MB on a weak signal. Anything the browser cannot draw (PDF, HEIC,
// unknown) goes up as-is, and any failure along the way also falls back to the original file.
const RESIZABLE = new Set(["image/jpeg", "image/png", "image/webp"]);

export async function downscale(file: File, maxEdge = 2000, quality = 0.85): Promise<File> {
  if (!RESIZABLE.has(file.type)) return file;
  const canvas = document.createElement("canvas");
  try {
    // Ask for the drawing surface before decoding: no point decoding a 12-megapixel photo we cannot draw.
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    const bitmap = await loadBitmap(file);
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
    const w = Math.round(bitmap.width * scale), h = Math.round(bitmap.height * scale);
    canvas.width = w; canvas.height = h;
    ctx.drawImage(bitmap, 0, 0, w, h);
    if ("close" in bitmap) bitmap.close(); // the <img> fallback has nothing to release
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/jpeg", quality));
    if (!blob) return file;
    return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch { return file; }
  finally {
    // iOS Safari has a small shared canvas budget — release this one before the next page is drawn.
    canvas.width = 0; canvas.height = 0;
  }
}

async function loadBitmap(file: File): Promise<ImageBitmap | HTMLImageElement> {
  // "from-image" honours EXIF orientation where supported, so photos taken sideways come out upright.
  if (typeof createImageBitmap === "function") return createImageBitmap(file, { imageOrientation: "from-image" });
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file); const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("decode failed")); };
    img.src = url;
  });
}

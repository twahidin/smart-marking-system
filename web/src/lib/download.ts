// Browser downloads: save a Blob through a temporary object URL, and fetch a file endpoint with the
// session cookie so API errors ({"error": {code, message}}) surface as ApiError instead of a broken file.
import { ApiError } from "../api/client";

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** The `filename` (or RFC 5987 `filename*`) of a Content-Disposition header, or null. */
export function dispositionFilename(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star) { try { return decodeURIComponent(star[1].trim()); } catch { /* fall through to the ASCII name */ } }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}

/** GET (or POST `body`) a download endpoint and save the response under the server's filename (or `fallback`). */
export async function downloadFile(path: string, fallback: string, body?: unknown): Promise<void> {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  if (!res.ok) {
    let err: { code: string; message: string } | null = null;
    try { err = (await res.json())?.error ?? null; } catch { err = null; }
    throw new ApiError(res.status, err?.code ?? `http_${res.status}`, err?.message ?? res.statusText);
  }
  saveBlob(await res.blob(), dispositionFilename(res.headers.get("Content-Disposition")) ?? fallback);
}

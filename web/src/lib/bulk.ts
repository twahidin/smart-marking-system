import { unzipSync } from "fflate";
import { isProgramFile, prepareUploads } from "./files";

/** One student's script in a bulk upload: a label (from the filename, editable) and its pages in reading order. */
export interface Script { label: string; files: File[] }

const PAGE_EXTS = [".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"];
const ext = (name: string) => { const i = name.lastIndexOf("."); return i < 0 ? "" : name.slice(i).toLowerCase(); };
const stem = (name: string) => { const base = name.slice(name.lastIndexOf("/") + 1); const i = base.lastIndexOf("."); return i <= 0 ? base : base.slice(0, i); };

export const isZip = (file: Pick<File, "name">): boolean => ext(file.name) === ".zip";
const isPage = (name: string) => PAGE_EXTS.includes(ext(name));

/** A trailing page marker — " 1", "-2", "_p3", " (4)", "page 5" — split off the stem, so "Tan Wei Ling-2.jpg" is
 *  page 2 of "Tan Wei Ling". A stem that is only a number keeps its name and has no page. */
export function splitPage(name: string): { label: string; page: number | null } {
  const s = stem(name).trim();
  const m = /^(.*?)[\s_-]*(?:\((\d+)\)|(?:p|pg|page)?[\s_-]*(\d+))$/i.exec(s);
  if (!m || !m[1].trim()) return { label: s, page: null };
  return { label: m[1].trim(), page: Number(m[2] ?? m[3]) };
}

const bytesOf = (file: File): Promise<Uint8Array> =>
  typeof file.arrayBuffer === "function"
    ? file.arrayBuffer().then((b) => new Uint8Array(b))
    : new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(new Uint8Array(r.result as ArrayBuffer)); r.onerror = () => reject(r.error); r.readAsArrayBuffer(file); });

/** Zips are unpacked in the browser: every page or program file inside comes out as a File named after its entry
 *  (folders, Finder's __MACOSX copies, dotfiles and nested zips are skipped); everything else passes through. */
export async function expandZips(files: File[]): Promise<File[]> {
  const out: File[] = [];
  for (const f of files) {
    if (!isZip(f)) { out.push(f); continue; }
    const entries = unzipSync(await bytesOf(f));
    for (const [path, data] of Object.entries(entries)) {
      const base = path.slice(path.lastIndexOf("/") + 1);
      if (!base || path.endsWith("/") || path.includes("__MACOSX") || base.startsWith(".")) continue;
      if (!isPage(base) && !(isProgramFile({ name: base }) && !isZip({ name: base }))) continue;
      out.push(new File([data as BlobPart], path, { type: mimeOf(base) }));
    }
  }
  return out;
}

const mimeOf = (name: string) => ({ ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp" } as Record<string, string>)[ext(name)] ?? "";

/** Files into scripts: a PDF or program file is a script of its own; images with the same label (filename minus
 *  its page marker) become one script, pages in number order, then name order. Groups already in `into` grow. */
export function groupScripts(files: File[], into: Script[] = []): Script[] {
  const scripts = into.map((s) => ({ ...s, files: [...s.files] }));
  const byLabel = new Map(scripts.map((s) => [s.label.toLowerCase(), s]));
  const pages = new Map<string, { page: number | null; file: File }[]>();
  for (const f of [...files].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))) {
    const e = ext(f.name);
    if (e === ".pdf" || isProgramFile(f)) { scripts.push({ label: stem(f.name).trim() || f.name, files: [f] }); continue; }
    const { label, page } = splitPage(f.name);
    const list = pages.get(label.toLowerCase()) ?? []; list.push({ page, file: f }); pages.set(label.toLowerCase(), list);
    if (!byLabel.has(label.toLowerCase())) { const s = { label, files: [] as File[] }; scripts.push(s); byLabel.set(label.toLowerCase(), s); }
  }
  for (const [key, list] of pages) {
    list.sort((a, b) => (a.page ?? 0) - (b.page ?? 0) || a.file.name.localeCompare(b.file.name, undefined, { numeric: true }));
    byLabel.get(key)!.files.push(...list.map((p) => p.file));
  }
  return scripts;
}

export interface BulkFields { assignment_id: number; subject: string; context: string; rubric: string }
export type Outcome = { ok: true; id: number } | { ok: false; error: string };

/** Uploads scripts through the single-script endpoint, `concurrency` at a time, reporting each result as it lands.
 *  One failure never stops the rest; the caller retries just the failed ones. */
export async function uploadScripts(scripts: Script[], fields: BulkFields, post: (form: FormData) => Promise<{ id: number }>,
                                    onResult: (index: number, outcome: Outcome) => void, concurrency = 2): Promise<Outcome[]> {
  const results: Outcome[] = new Array(scripts.length);
  let next = 0;
  const worker = async () => {
    while (next < scripts.length) {
      const i = next++;
      const s = scripts[i];
      try {
        const fd = new FormData();
        fd.set("label", s.label.trim()); fd.set("subject", fields.subject); fd.set("context", fields.context); fd.set("rubric", fields.rubric);
        fd.set("assignment_id", String(fields.assignment_id));
        (await prepareUploads(s.files)).forEach((f) => fd.append("files", f, f.name.slice(f.name.lastIndexOf("/") + 1)));
        const { id } = await post(fd);
        results[i] = { ok: true, id };
      } catch (e) { results[i] = { ok: false, error: e instanceof Error ? e.message : "Upload failed" }; }
      onResult(i, results[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.max(1, Math.min(concurrency, scripts.length)) }, worker));
  return results;
}

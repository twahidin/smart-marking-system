import { Upload } from "lucide-react";
import { useRef, useState } from "react";

export const PAGE_ACCEPT = ".pdf,.jpg,.jpeg,.png,.heic,.heif,image/*,application/pdf";

export function DropZone({ onFiles, title = "Drop pages here", hint = "PDF, JPG, PNG or HEIC — up to 50 MB", accept = PAGE_ACCEPT }:
  { onFiles: (files: File[]) => void; title?: string; hint?: string; accept?: string }) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className={`drop ${over ? "over" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFiles(Array.from(e.dataTransfer.files)); }}>
      <Upload size={32} aria-hidden />
      <h3>{title}</h3>
      <p className="help">{hint}</p>
      <button type="button" className="btn btn-secondary" onClick={() => input.current?.click()}>Choose files</button>
      <input ref={input} type="file" multiple accept={accept} hidden onChange={(e) => { onFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
    </div>
  );
}

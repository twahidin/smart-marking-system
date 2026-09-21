import { FileCode2, FileSpreadsheet, Puzzle } from "lucide-react";
import { useState } from "react";
import type { SubmissionFile } from "../api/types";
import { fmtSize } from "../lib/files";

const KIND_LABEL: Record<SubmissionFile["kind"], string> = { py: "Python", sb3: "Scratch", xlsx: "Excel" };
const KIND_ICON: Record<SubmissionFile["kind"], typeof FileCode2> = { py: FileCode2, sb3: Puzzle, xlsx: FileSpreadsheet };

/** What the student handed in as files, and what the marker made of each one: the text it read (a .sb3
 *  has none to show), whether any part actually cited it, and whether the bytes have since been deleted. */
export function FilesBlock({ files }: { files: SubmissionFile[] }) {
  return (
    <div className="files-block">
      <h4>Files</h4>
      <ul className="files" aria-label="Files">
        {files.map((f) => <FileRow key={f.id} file={f} />)}
      </ul>
    </div>
  );
}

function FileRow({ file }: { file: SubmissionFile }) {
  const [open, setOpen] = useState(false);
  const Icon = KIND_ICON[file.kind];
  return (
    <li className="file-row">
      <Icon size={18} aria-hidden />
      <div>
        <strong>{file.name}</strong>
        <span className="help" style={{ marginLeft: 8 }}>{KIND_LABEL[file.kind]} · {fmtSize(file.size)}</span>
        {/* Only once a run has decided. `matched: null` is "not marked yet", and `.warn-note` is an
            inline-flex box, so the separator belongs in the flow: "Python · 95 B · Not used …". */}
        {file.matched === false && <><span className="help"> · </span><span className="warn-note">Not used for any part</span></>}
        {file.deleted && <div className="help">Deleted after marking</div>}
        {file.text_rendered && (
          <>
            <button type="button" className="btn btn-ghost btn-sm" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide text" : "Show text"}</button>
            {open && <pre className="file-text">{file.text_rendered}</pre>}
          </>
        )}
      </div>
    </li>
  );
}

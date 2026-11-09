import type { ReactNode } from "react";

export function Dialog({ title, children, footer, onClose, wide = false }: { title: string; children: ReactNode; footer: ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className={wide ? "dialog dialog-wide" : "dialog"} role="dialog" aria-modal="true" aria-labelledby="dlg-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="dlg-title">{title}</h2>
        {/* Only the body scrolls, so the title and the footer's buttons stay in view however long it gets. */}
        <div className="dialog-body">{children}</div>
        <div className="dialog-footer">{footer}</div>
      </div>
    </div>
  );
}

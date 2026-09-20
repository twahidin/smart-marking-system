import { useState } from "react";
import type { ProviderSpec } from "../api/types";

/** What a picker edits: a provider, the model id under it, and an optional separate model for
 *  reading pages ("" = use the same one). */
export type ModelChoice = { provider: string; model: string; extractorModel: string };

const CUSTOM = "__custom__";
export const NO_KEY = "No key saved — add one under Settings";

/** The provider tiles, the model select, the custom-id input and the extractor model — shared by
 *  the assignment editor's Model section and the *By subject* table under Settings. A provider with
 *  no key saved is still offered, so the teacher can see it, but cannot be picked. */
export function ModelPicker({ providers, keys, value, onChange, name, extractorId }: {
  providers: ProviderSpec[];
  /** provider id → key hint; a provider missing from it has no key saved yet. */
  keys: Record<string, string>;
  value: ModelChoice;
  onChange: (next: ModelChoice) => void;
  /** Unique per picker on the page, so two pickers' provider radios are not one group. */
  name: string;
  /** Unique per picker: the id the extractor field's label points at. */
  extractorId: string;
}) {
  // Sticky once the teacher picks "Custom model id…", so the input stays while they type an id
  // that happens to match a listed one.
  const [custom, setCustom] = useState(false);
  const spec = providers.find((p) => p.id === value.provider) ?? null;
  const hasKey = (id: string) => !!keys[id];
  const showCustom = custom || !spec?.models.some((m) => m.id === value.model);
  const pickProvider = (id: string) => {
    setCustom(false);
    onChange({ ...value, provider: id, model: providers.find((p) => p.id === id)?.default_model ?? "" });
  };

  return (
    <>
      <div className="field"><label>Provider</label>
        <div className="seg" role="radiogroup" aria-label="Model provider">
          {providers.map((p) => (
            <label key={p.id} className={`seg-opt ${value.provider === p.id ? "on" : ""}${hasKey(p.id) ? "" : " off"}`} title={hasKey(p.id) ? undefined : NO_KEY}>
              <input type="radio" name={name} checked={value.provider === p.id} disabled={!hasKey(p.id)} onChange={() => pickProvider(p.id)} />{p.label}
            </label>
          ))}
        </div>
      </div>
      <div className="grid-2">
        <div className="field"><label>Model</label>
          <select className="input" aria-label="Model id" value={showCustom ? CUSTOM : value.model}
            onChange={(e) => { if (e.target.value === CUSTOM) setCustom(true); else { setCustom(false); onChange({ ...value, model: e.target.value }); } }}>
            {(spec?.models ?? []).map((m) => <option key={m.id} value={m.id}>{m.label}{m.vision ? " · reads pages" : " · text only"}</option>)}
            <option value={CUSTOM}>Custom model id…</option>
          </select>
          {showCustom && <input className="input" aria-label="Custom model id" placeholder="exact model id" value={value.model} onChange={(e) => onChange({ ...value, model: e.target.value })} />}
        </div>
        <div className="field"><label htmlFor={extractorId}>Different model for reading pages (optional)</label>
          <input id={extractorId} className="input" placeholder="leave blank to use the same model" value={value.extractorModel} onChange={(e) => onChange({ ...value, extractorModel: e.target.value })} />
          <span className="help">Use a cheap vision model to transcribe, and a stronger one to mark.</span></div>
      </div>
    </>
  );
}

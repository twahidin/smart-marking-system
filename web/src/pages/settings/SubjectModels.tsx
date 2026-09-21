import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ProviderSpec, Settings, Subject, SubjectModels as SubjectModelMap } from "../../api/types";
import { Button } from "../../components/Button";
import { ModelPicker, type ModelChoice } from "../../components/ModelPicker";
import { Notice } from "../../components/Notice";
import { SUBJECTS, subjectLabel } from "../../lib/format";

/** What the teacher needs to know when choosing for these two; the rest need nothing said. */
const HINT: Partial<Record<Subject, string>> = {
  mt: "Pick a model that reads Chinese, Malay or Tamil handwriting well",
  computing: "Pick a model that is strong at code",
};
/** null = Auto: the subject follows Settings and has nothing saved of its own. */
type Drafts = Record<Subject, ModelChoice | null>;
const EMPTY_DRAFTS: Drafts = { math: null, language: null, science: null, mt: null, computing: null };

const toDraft = (row: { provider: string; model: string; extractor_model: string | null } | null): ModelChoice | null =>
  (row ? { provider: row.provider, model: row.model, extractorModel: row.extractor_model ?? "" } : null);

/** The *By subject* table under Settings: a model each new assignment of that subject follows.
 *  Each row saves and clears on its own — nothing here rides on the page's own Save. */
export function SubjectModels({ providers, settings, onChange }: {
  providers: ProviderSpec[];
  settings: Settings;
  /** Called after a row is saved or cleared, for anything on the page that follows these. */
  onChange?: () => void;
}) {
  // `saved` is what the server holds (so a switch back to Auto knows whether there is anything to
  // delete); `drafts` is what the teacher is editing.
  const [saved, setSaved] = useState<SubjectModelMap | null>(null);
  const [drafts, setDrafts] = useState<Drafts>(EMPTY_DRAFTS);
  const [busy, setBusy] = useState<Subject | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  useEffect(() => {
    api.get<SubjectModelMap>("/api/settings/subject-models")
      .then((m) => {
        setSaved(m);
        setDrafts(SUBJECTS.reduce((acc, s) => ({ ...acc, [s]: toDraft(m[s]) }), EMPTY_DRAFTS));
      })
      .catch((e) => setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not load the subject models" }));
  }, []);

  const keys = settings.keys ?? (settings.has_key ? { [settings.provider]: settings.key_hint } : {});
  const hasKey = (id: string) => !!keys[id];
  // A row starts on the provider Settings would have used, when that one still has a key.
  const firstUsable = (hasKey(settings.provider) ? settings.provider : providers.find((p) => hasKey(p.id))?.id) ?? null;
  const anyKey = firstUsable !== null;

  const choose = (s: Subject) => {
    if (!firstUsable) return;
    const model = providers.find((p) => p.id === firstUsable)?.default_model ?? "";
    setDrafts((d) => ({ ...d, [s]: { provider: firstUsable, model, extractorModel: "" } }));
  };

  const toAuto = async (s: Subject) => {
    setDrafts((d) => ({ ...d, [s]: null }));
    setMsg(null);
    // Nothing was ever stored for this subject, so there is nothing to clear on the server. When the
    // initial GET failed `saved` is null — not "nothing saved" but "not known", and skipping the
    // DELETE there would leave a pinned model in place while the row read Auto. Send it and let the
    // server decide; clearing what is already clear is harmless.
    if (saved !== null && !saved[s]) return;
    setBusy(s);
    try {
      await api.delete(`/api/settings/subject-models/${s}`);
      setSaved((m) => (m ? { ...m, [s]: null } : m));
      setMsg({ kind: "ok", text: `${subjectLabel[s]} follows Settings again.` });
      onChange?.();
    } catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not clear the subject model" }); }
    finally { setBusy(null); }
  };

  const save = async (s: Subject) => {
    const d = drafts[s];
    if (!d) return;
    setBusy(s); setMsg(null);
    const body = { provider: d.provider, model: d.model.trim(), extractor_model: d.extractorModel.trim() || null };
    try {
      const row = await api.put<{ provider: string; model: string; extractor_model: string | null }>(`/api/settings/subject-models/${s}`, body);
      setSaved((m) => (m ? { ...m, [s]: row } : m));
      setMsg({ kind: "ok", text: `${subjectLabel[s]} saved.` });
      onChange?.();
    } catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not save the subject model" }); }
    finally { setBusy(null); }
  };

  return (
    <section className="section" aria-label="By subject">
      <div className="section-head"><h2>By subject</h2>
        <span className="help">New assignments follow their subject's model; each assignment can still pin its own.</span></div>
      {!anyKey && <p className="help">No keys saved yet — add one above to choose a model here.</p>}
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <table className="table" role="table" aria-label="Model by subject">
        <thead><tr><th>Subject</th><th>Model</th></tr></thead>
        <tbody>
          {SUBJECTS.map((s) => {
            const draft = drafts[s];
            return (
              <tr key={s}>
                <th scope="row" style={{ verticalAlign: "top", textAlign: "left" }}>
                  {subjectLabel[s]}
                  {HINT[s] && <><br /><span className="help">{HINT[s]}</span></>}
                </th>
                <td>
                  <div className="seg" role="radiogroup" aria-label={`${subjectLabel[s]} model`} style={{ maxWidth: 320 }}>
                    <label className={`seg-opt ${draft === null ? "on" : ""}`}>
                      <input type="radio" name={`subject-model-${s}`} checked={draft === null} onChange={() => { void toAuto(s); }} />Auto
                    </label>
                    <label className={`seg-opt ${draft !== null ? "on" : ""}${anyKey ? "" : " off"}`}>
                      <input type="radio" name={`subject-model-${s}`} checked={draft !== null} disabled={!anyKey} onChange={() => choose(s)} />Choose
                    </label>
                  </div>
                  {draft && (
                    <>
                      <ModelPicker providers={providers} keys={keys} name={`subject-provider-${s}`} extractorId={`subject-extractor-${s}`}
                        value={draft} onChange={(v) => setDrafts((d) => ({ ...d, [s]: v }))} />
                      <div className="actions">
                        <Button type="button" onClick={() => { void save(s); }} disabled={busy !== null || !draft.model.trim()}>
                          {busy === s ? "Saving…" : "Save"}
                        </Button>
                      </div>
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { ProbeResult, ProviderSpec, Settings as S } from "../api/types";
import { Button } from "../components/Button";
import { Notice } from "../components/Notice";

type Form = { provider: string; model: string; custom_model: string; api_key: string; base_url: string; extractor_model: string; rpm_limit: number; confidence_threshold: number; auto_reflect: boolean; delete_pages_after_marking: boolean };

export function Settings() {
  const [providers, setProviders] = useState<ProviderSpec[]>([]);
  const [saved, setSaved] = useState<S | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [busy, setBusy] = useState<"test" | "save" | "models" | null>(null);
  const [fetched, setFetched] = useState<string[]>([]);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  useEffect(() => {
    Promise.all([api.get<ProviderSpec[]>("/api/providers"), api.get<S>("/api/settings")]).then(([p, s]) => {
      setProviders(p); setSaved(s);
      const spec = p.find((x) => x.id === s.provider)!;
      const listed = spec.models.some((m) => m.id === s.model);
      setForm({ provider: s.provider, model: listed ? s.model : "__custom__", custom_model: listed ? "" : s.model, api_key: "",
                base_url: s.base_url ?? "", extractor_model: s.extractor_model ?? "", rpm_limit: s.rpm_limit, confidence_threshold: s.confidence_threshold,
                auto_reflect: s.auto_reflect, delete_pages_after_marking: s.delete_pages_after_marking ?? true });
    }).catch((e) => setMsg({ kind: "error", text: e.message }));
  }, []);

  const spec = useMemo(() => providers.find((p) => p.id === form?.provider), [providers, form?.provider]);
  if (!form || !spec || !saved) return <div className="page muted">Loading…</div>;

  const modelId = form.model === "__custom__" ? form.custom_model.trim() : form.model;
  // Keys are stored per provider: the hint and the enabled state follow the *selected* provider, not the saved one.
  const keys = saved.keys ?? (saved.has_key ? { [saved.provider]: saved.key_hint } : {});
  const savedHint = keys[form.provider];
  const hasKey = !!form.api_key || !!savedHint;
  const payload = { provider: form.provider, model: modelId, api_key: form.api_key || undefined, base_url: form.base_url || undefined,
                    extractor_model: form.extractor_model || undefined, rpm_limit: form.rpm_limit, confidence_threshold: form.confidence_threshold,
                    auto_reflect: form.auto_reflect, delete_pages_after_marking: form.delete_pages_after_marking };

  const changeProvider = (id: string) => {
    const p = providers.find((x) => x.id === id)!;
    setForm({ ...form, provider: id, model: p.default_model, custom_model: "", base_url: "", rpm_limit: p.default_rpm });
    setProbe(null); setFetched([]);
  };

  const loadModels = async () => {
    setBusy("models"); setMsg(null);
    try {
      const r = await api.post<{ models: string[] }>("/api/settings/models", { provider: form.provider, api_key: form.api_key || undefined, base_url: form.base_url || undefined });
      setFetched(r.models);
      setMsg(r.models.length ? null : { kind: "error", text: "Your key returned no models." });
    } catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not load models" }); }
    finally { setBusy(null); }
  };

  const removeKey = async () => {
    setBusy("save"); setMsg(null);
    try {
      await api.delete(`/api/settings/keys/${form.provider}`);
      const next = { ...keys }; delete next[form.provider];
      setSaved({ ...saved, keys: next, has_key: saved.provider === form.provider ? false : saved.has_key, key_hint: saved.provider === form.provider ? "" : saved.key_hint });
      setMsg({ kind: "ok", text: `${spec.label} key removed.` });
    } catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not remove the key" }); }
    finally { setBusy(null); }
  };

  const test = async () => {
    setBusy("test"); setMsg(null); setProbe(null);
    try { setProbe(await api.post<ProbeResult>("/api/settings/test", payload)); }
    catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not test" }); }
    finally { setBusy(null); }
  };
  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy("save"); setMsg(null);
    try { const s = await api.put<S>("/api/settings", payload); setSaved(s); setForm({ ...form, api_key: "" }); setMsg({ kind: "ok", text: "Saved." }); }
    catch (err) { setMsg({ kind: "error", text: err instanceof ApiError ? err.message : "Could not save" }); }
    finally { setBusy(null); }
  };

  return (
    <div className="page">
      <div className="page-header"><div><h1>AI model</h1><p className="meta">Which model marks your scripts, and the key it uses.</p></div></div>
      <hr className="rule-2" />
      <form onSubmit={save} style={{ maxWidth: 720, marginTop: 24 }}>
        <div className="field">
          <label>Provider</label>
          <div className="seg" role="radiogroup" aria-label="Provider">
            {providers.map((p) => (
              <label key={p.id} className={`seg-opt ${form.provider === p.id ? "on" : ""}`}>
                <input type="radio" name="provider" value={p.id} checked={form.provider === p.id} onChange={() => changeProvider(p.id)} />{p.label}{keys[p.id] && <span className="key-tick" title="Key saved" aria-hidden> ✓</span>}
              </label>
            ))}
          </div>
          {spec.note && <p className="help">{(spec.id === "google" || spec.id === "openrouter") && <><strong>Free options:</strong> </>}{spec.note}</p>}
        </div>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="model">Model</label>
            <select id="model" className="input" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}>
              {spec.models.map((m) => <option key={m.id} value={m.id}>{m.label}{m.vision ? " · reads pages" : " · text only"}</option>)}
              {fetched.filter((id) => !spec.models.some((m) => m.id === id)).length > 0 && (
                <optgroup label="From your account">
                  {fetched.filter((id) => !spec.models.some((m) => m.id === id)).map((id) => <option key={id} value={id}>{id}</option>)}
                </optgroup>
              )}
              <option value="__custom__">Custom model id…</option>
            </select>
            <button type="button" className="btn btn-ghost btn-sm" onClick={loadModels} disabled={busy !== null || !hasKey} style={{ alignSelf: "flex-start" }}>
              {busy === "models" ? "Loading…" : fetched.length ? `Reload models (${fetched.length} found)` : "Load models from provider"}
            </button>
            {form.model === "__custom__" && <input className="input" placeholder="exact model id" aria-label="Custom model id" value={form.custom_model} onChange={(e) => setForm({ ...form, custom_model: e.target.value })} />}
          </div>
          <div className="field">
            <label htmlFor="key">API key</label>
            <input id="key" className="input" type="password" autoComplete="off" placeholder={savedHint ? `Saved key ending …${savedHint} — leave blank to keep` : `No key saved for ${spec.label} yet — paste one`} value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
            <div className="actions" style={{ alignItems: "center" }}>
              <a className="help" href={spec.key_url} target="_blank" rel="noreferrer">Where to get a {spec.label} key</a>
              {savedHint && <button type="button" className="btn btn-ghost btn-sm" onClick={removeKey} disabled={busy !== null}>Remove {spec.label} key</button>}
            </div>
          </div>
        </div>
        {spec.base_url_editable && (
          <div className="field"><label htmlFor="base">Base URL</label>
            <input id="base" className="input" placeholder={spec.base_url ?? ""} value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} /></div>
        )}
        <div className="grid-2">
          <div className="field"><label htmlFor="ext">Different model for reading pages (optional)</label>
            <input id="ext" className="input" placeholder="leave blank to use the same model" value={form.extractor_model} onChange={(e) => setForm({ ...form, extractor_model: e.target.value })} />
            <span className="help">Use a cheap vision model to transcribe, and a stronger one to mark.</span></div>
          <div className="field"><label htmlFor="rpm">Requests per minute</label>
            <input id="rpm" className="input" type="number" min={0} value={form.rpm_limit} onChange={(e) => setForm({ ...form, rpm_limit: Number(e.target.value) })} />
            <span className="help">0 = no limit. A script needs about 4 requests.</span></div>
        </div>
        <div className="field" style={{ maxWidth: 340 }}><label htmlFor="thr">Ask me when confidence is below</label>
          <input id="thr" className="input" type="number" min={0} max={1} step={0.05} value={form.confidence_threshold} onChange={(e) => setForm({ ...form, confidence_threshold: Number(e.target.value) })} />
          <span className="help">0 turns this off. 0.6 is a sensible start.</span></div>
        <div className="field">
          <label style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 44, cursor: "pointer" }}>
            <input type="checkbox" checked={form.auto_reflect} onChange={(e) => setForm({ ...form, auto_reflect: e.target.checked })} style={{ width: 18, height: 18 }} />
            Run reflection nightly on new corrections
          </label>
          <span className="help">Turns your Review corrections into draft rubric notes once a day. You can also run it any time from Learning.</span>
        </div>
        <div className="field">
          <label style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 44, cursor: "pointer" }}>
            <input type="checkbox" checked={form.delete_pages_after_marking} onChange={(e) => setForm({ ...form, delete_pages_after_marking: e.target.checked })} style={{ width: 18, height: 18 }} />
            Delete student pages after marking (default for new assignments)
          </label>
          <span className="help">Student pages are deleted as soon as a script is done; the marking record keeps the transcription and every mark. Each assignment can override this.</span>
        </div>

        {probe && (
          <Notice kind={probe.text.ok && probe.vision.ok ? "ok" : "amber"}>
            <strong>Text {probe.text.ok ? `✓ ${(probe.text.latency_ms / 1000).toFixed(1)} s` : `✗ ${probe.text.error}`}</strong><br />
            <strong>Vision {probe.vision.ok ? `✓ ${(probe.vision.latency_ms / 1000).toFixed(1)} s` : `✗ ${probe.vision.error}`}</strong>
            {!probe.vision.ok && probe.text.ok && <div>This model may not read images. Pick a model marked “reads pages”, or set a different model for reading pages.</div>}
          </Notice>
        )}
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
        <div className="actions" style={{ marginTop: 24 }}>
          <Button type="button" size="lg" onClick={test} disabled={busy !== null || !modelId || !hasKey}>{busy === "test" ? "Testing…" : "Test connection"}</Button>
          <Button type="submit" variant="primary" size="lg" disabled={busy !== null || !modelId}>{busy === "save" ? "Saving…" : "Save"}</Button>
        </div>
      </form>
    </div>
  );
}

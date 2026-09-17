import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { ProbeResult, ProviderSpec, Settings as S } from "../api/types";
import { Button } from "../components/Button";
import { Notice } from "../components/Notice";

type Form = { provider: string; model: string; custom_model: string; api_key: string; base_url: string; extractor_model: string; rpm_limit: number; confidence_threshold: number; auto_reflect: boolean; delete_pages_after_marking: boolean;
              telegram_bot_token: string; telegram_instant: boolean; telegram_daily_time: string; timezone: string; app_url: string };
/** Offered first in the Time zone select; the browser's full IANA list follows when it can produce one. */
const COMMON_ZONES = ["Asia/Singapore", "Asia/Kuala_Lumpur", "Asia/Jakarta", "Asia/Manila", "Asia/Bangkok", "Asia/Hong_Kong", "Asia/Tokyo", "Australia/Sydney", "Europe/London", "UTC"];

export function Settings() {
  const [providers, setProviders] = useState<ProviderSpec[]>([]);
  const [saved, setSaved] = useState<S | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [busy, setBusy] = useState<"test" | "save" | "models" | "telegram" | "custom" | null>(null);
  const [fetched, setFetched] = useState<string[]>([]);
  const [newModel, setNewModel] = useState({ id: "", label: "", vision: true });
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  useEffect(() => {
    Promise.all([api.get<ProviderSpec[]>("/api/providers"), api.get<S>("/api/settings")]).then(([p, s]) => {
      setProviders(p); setSaved(s);
      const spec = p.find((x) => x.id === s.provider)!;
      const listed = spec.models.some((m) => m.id === s.model);
      setForm({ provider: s.provider, model: listed ? s.model : "__custom__", custom_model: listed ? "" : s.model, api_key: "",
                base_url: s.base_url ?? "", extractor_model: s.extractor_model ?? "", rpm_limit: s.rpm_limit, confidence_threshold: s.confidence_threshold,
                auto_reflect: s.auto_reflect, delete_pages_after_marking: s.delete_pages_after_marking ?? true,
                telegram_bot_token: "", telegram_instant: s.telegram_instant ?? true, telegram_daily_time: s.telegram_daily_time || "07:00",
                timezone: s.timezone || "Asia/Singapore", app_url: s.app_url ?? "" });
    }).catch((e) => setMsg({ kind: "error", text: e.message }));
  }, []);

  const spec = useMemo(() => providers.find((p) => p.id === form?.provider), [providers, form?.provider]);
  const zones = useMemo(() => {
    const all = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
    return [...new Set([...COMMON_ZONES, ...all, form?.timezone ?? ""])].filter(Boolean);
  }, [form?.timezone]);
  if (!form || !spec || !saved) return <div className="page muted">Loading…</div>;

  const modelId = form.model === "__custom__" ? form.custom_model.trim() : form.model;
  // Keys are stored per provider: the hint and the enabled state follow the *selected* provider, not the saved one.
  const keys = saved.keys ?? (saved.has_key ? { [saved.provider]: saved.key_hint } : {});
  const savedHint = keys[form.provider];
  const hasKey = !!form.api_key || !!savedHint;
  const payload = { provider: form.provider, model: modelId, api_key: form.api_key || undefined, base_url: form.base_url || undefined,
                    extractor_model: form.extractor_model || undefined, rpm_limit: form.rpm_limit, confidence_threshold: form.confidence_threshold,
                    auto_reflect: form.auto_reflect, delete_pages_after_marking: form.delete_pages_after_marking,
                    // The PUT body is authoritative for the four below — an omitted field resets to its default — so every save carries them.
                    telegram_bot_token: form.telegram_bot_token || undefined, telegram_instant: form.telegram_instant,
                    telegram_daily_time: form.telegram_daily_time, timezone: form.timezone, app_url: form.app_url.trim() || null };
  const customs = spec.models.filter((m) => m.custom);
  const unlisted = fetched.filter((id) => !spec.models.some((m) => m.id === id));

  const changeProvider = (id: string) => {
    const p = providers.find((x) => x.id === id)!;
    setForm({ ...form, provider: id, model: p.default_model, custom_model: "", base_url: "", rpm_limit: p.default_rpm });
    setProbe(null); setFetched([]); setNewModel({ id: "", label: "", vision: true });
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

  /** Re-read the provider list after the teacher adds or removes one of their own model ids. */
  const refreshProviders = async () => {
    const list = await api.get<ProviderSpec[]>("/api/providers");
    setProviders(list);
    const models = list.find((p) => p.id === form.provider)?.models ?? [];
    if (form.model !== "__custom__" && !models.some((m) => m.id === form.model)) setForm({ ...form, model: "__custom__", custom_model: form.model });
  };

  const addModel = async (id: string, label = "", vision = true) => {
    const model_id = id.trim();
    if (!model_id) return;
    setBusy("custom"); setMsg(null);
    try {
      await api.post(`/api/settings/models/${form.provider}`, { model_id, label: label.trim(), vision });
      setNewModel({ id: "", label: "", vision: true });
      await refreshProviders();
    } catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not add the model" }); }
    finally { setBusy(null); }
  };

  const removeModel = async (id: string) => {
    setBusy("custom"); setMsg(null);
    // Model ids contain slashes and the route takes the rest of the path, so the id goes in unescaped.
    try { await api.delete(`/api/settings/models/${form.provider}/${id}`); await refreshProviders(); }
    catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not remove the model" }); }
    finally { setBusy(null); }
  };

  const telegramTest = async () => {
    setBusy("telegram"); setMsg(null);
    try { await api.post("/api/settings/telegram/test"); setMsg({ kind: "ok", text: "Test message sent — check Telegram." }); }
    catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not send the test message" }); }
    finally { setBusy(null); }
  };

  const telegramUnlink = async () => {
    setBusy("telegram"); setMsg(null);
    try {
      await api.delete("/api/settings/telegram");
      setSaved({ ...saved, telegram_linked: false, telegram_bot_hint: "", telegram_chat_id: null });
      setMsg({ kind: "ok", text: "Telegram unlinked." });
    } catch (e) { setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not unlink Telegram" }); }
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
        {spec.custom_models && (
          <div className="field">
            <label>My models</label>
            <span className="help">Model ids you add stay in the Model list for {spec.label}.</span>
            {customs.length > 0 ? (
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {customs.map((m) => (
                  <li key={m.id} style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 40 }}>
                    <span>{m.label}{m.label !== m.id && <span className="help"> · {m.id}</span>}{!m.vision && <span className="help"> · text only</span>}</span>
                    <button type="button" className="btn btn-ghost btn-sm" aria-label={`Remove ${m.id}`} onClick={() => removeModel(m.id)} disabled={busy !== null}>Remove</button>
                  </li>
                ))}
              </ul>
            ) : <span className="help">None yet.</span>}
            <div className="grid-2">
              <div className="field"><label htmlFor="cm-id">Model id</label>
                <input id="cm-id" className="input" placeholder="exact id, e.g. google/gemini-3.8-flash" value={newModel.id} onChange={(e) => setNewModel({ ...newModel, id: e.target.value })} /></div>
              <div className="field"><label htmlFor="cm-label">Label</label>
                <input id="cm-label" className="input" placeholder="optional — what the Model list shows" value={newModel.label} onChange={(e) => setNewModel({ ...newModel, label: e.target.value })} /></div>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 44, cursor: "pointer" }}>
              <input type="checkbox" checked={newModel.vision} onChange={(e) => setNewModel({ ...newModel, vision: e.target.checked })} style={{ width: 18, height: 18 }} />
              Reads pages
            </label>
            <button type="button" className="btn btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => addModel(newModel.id, newModel.label, newModel.vision)} disabled={busy !== null || !newModel.id.trim()}>
              {busy === "custom" ? "Working…" : "Add model"}
            </button>
            {unlisted.length > 0 && (
              <>
                <span className="help">From your account — add the ones you use:</span>
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {unlisted.map((id) => (
                    <li key={id} style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 40 }}>
                      <span>{id}</span>
                      <button type="button" className="btn btn-ghost btn-sm" aria-label={`Add ${id}`} onClick={() => addModel(id)} disabled={busy !== null}>+ Add</button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
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

        <hr className="rule-2" style={{ marginTop: 24 }} />
        <div className="section-head"><h2>Notifications</h2><span className="help">Telegram messages when scripts come in and when marking finishes, plus a daily report.</span></div>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="tg-token">Telegram bot token</label>
            <input id="tg-token" className="input" type="password" autoComplete="off"
                   placeholder={saved.telegram_bot_hint ? `Saved token ending …${saved.telegram_bot_hint} — leave blank to keep` : "Paste the token from @BotFather"}
                   value={form.telegram_bot_token} onChange={(e) => setForm({ ...form, telegram_bot_token: e.target.value })} />
            <span className="help">
              {saved.telegram_linked
                ? `Linked ✓ (chat …${(saved.telegram_chat_id ?? "").slice(-4)})`
                : "Not linked — save the token, then open your bot in Telegram and press /start"}
            </span>
            {saved.telegram_linked && (
              <div className="actions">
                <button type="button" className="btn btn-ghost btn-sm" onClick={telegramTest} disabled={busy !== null}>Send test message</button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={telegramUnlink} disabled={busy !== null}>Unlink</button>
              </div>
            )}
          </div>
          <div className="field">
            <label htmlFor="app-url">App URL</label>
            <input id="app-url" className="input" placeholder="auto-detected on Railway" value={form.app_url} onChange={(e) => setForm({ ...form, app_url: e.target.value })} />
            <span className="help">Where the links in your Telegram messages point.</span>
          </div>
        </div>
        <div className="field">
          <label style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 44, cursor: "pointer" }}>
            <input type="checkbox" checked={form.telegram_instant} onChange={(e) => setForm({ ...form, telegram_instant: e.target.checked })} style={{ width: 18, height: 18 }} />
            Send instant messages (hand-ins, marking finished)
          </label>
          <span className="help">Turn this off to get the daily report only.</span>
        </div>
        <div className="grid-2">
          <div className="field"><label htmlFor="tg-time">Daily report at</label>
            <input id="tg-time" className="input" type="time" value={form.telegram_daily_time} onChange={(e) => setForm({ ...form, telegram_daily_time: e.target.value })} /></div>
          <div className="field"><label htmlFor="tz">Time zone</label>
            <select id="tz" className="input" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })}>
              {zones.map((z) => <option key={z} value={z}>{z}</option>)}
            </select></div>
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

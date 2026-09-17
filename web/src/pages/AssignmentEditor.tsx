import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { AssignmentBody, AssignmentTemplate, ExtractStatus, MarkSchemeEntry, ProviderSpec, Question, RubricBands, SchemeKind, Settings, Subject } from "../api/types";
import { Button } from "../components/Button";
import { CriteriaEditor } from "../components/CriteriaTable";
import { Dialog } from "../components/Dialog";
import { DropZone } from "../components/DropZone";
import { EmptyState } from "../components/EmptyState";
import { MarkSchemeTable } from "../components/MarkSchemeTable";
import { Notice } from "../components/Notice";
import { QuestionsTable } from "../components/QuestionsTable";
import { RubricTable } from "../components/RubricTable";
import { providerLabel, subjectLabel } from "../lib/format";
import { jsonToRows, type Row } from "../lib/rubric";
import { kindLabel, placeholderRubric, schemeTotal, validateTemplate, type Scheme } from "../lib/scheme";

type Draft = {
  title: string; subject: Subject; kind: SchemeKind | null; context: string;
  questions: Question[]; scheme: Scheme; criteria: Row[]; deletePages: boolean | null;
  /** null = Auto: the assignment follows Settings, and its model fields go with it. */
  provider: string | null; model: string; extractorModel: string;
};
type Upload = "paper" | "scheme";
type Busy = null | "save" | Upload | `read-${Upload}`;

const KINDS: SchemeKind[] = ["mark_scheme", "rubric", "criteria"];
const DEFAULT_SUBJECT: Record<SchemeKind, Subject> = { mark_scheme: "math", rubric: "language", criteria: "math" };
const EMPTY: Draft = { title: "", subject: "math", kind: null, context: "", questions: [], scheme: [], criteria: [], deletePages: null, provider: null, model: "", extractorModel: "" };
const CUSTOM = "__custom__";
const NO_KEY = "No key saved — add one under Settings";
const isActive = (s: string | null | undefined) => s === "queued" || s === "running";

const clampInt = (v: unknown) => Math.max(0, Math.round(Number(v) || 0));
const trimmed = (s: string) => (s ?? "").trim();

/** The request body for a draft. Rows still being typed (blank ids, blank labels) are left out so a draft can
 *  always be stored; explicit Save only runs once validateTemplate is happy, so nothing is dropped then. */
function toBody(d: Draft): AssignmentBody {
  const kind = d.kind ?? "criteria";
  const questions = d.questions.filter((q) => trimmed(q.q_id)).map((q) => ({ q_id: trimmed(q.q_id), text: q.text, max_marks: clampInt(q.max_marks) }));
  let scheme: Scheme = [];
  if (kind === "mark_scheme") {
    scheme = (d.scheme as MarkSchemeEntry[]).filter((r) => trimmed(r.q_id)).map((r) => ({
      q_id: trimmed(r.q_id), answer: r.answer, notes: r.notes,
      marks: r.marks.filter((m) => trimmed(m.label)).map((m) => ({ label: trimmed(m.label), marks: clampInt(m.marks) })),
    }));
  } else if (kind === "rubric") {
    scheme = (d.scheme as RubricBands[]).filter((c) => trimmed(c.criterion)).map((c) => ({
      criterion: trimmed(c.criterion),
      bands: c.bands.filter((b) => trimmed(b.band)).map((b) => ({ band: trimmed(b.band), marks: clampInt(b.marks), descriptor: b.descriptor })),
    }));
  }
  const criteria = d.criteria.filter((c) => trimmed(c.description)).map((c) => ({ ...c, max_score: Math.max(1, clampInt(c.max_score)) }));
  return {
    title: trimmed(d.title), subject: d.subject, context: trimmed(d.context), scheme_kind: kind,
    rubric: placeholderRubric(kind, questions, scheme, criteria), questions, scheme, delete_pages_after_marking: d.deletePages,
    // Auto sends all three as null; the server treats a missing provider as "follow Settings" either way.
    provider: d.provider, model: d.provider ? trimmed(d.model) : null,
    extractor_model: d.provider ? trimmed(d.extractorModel) || null : null,
  };
}

function fromTemplate(t: AssignmentTemplate): Draft {
  return {
    title: t.title, subject: t.subject, kind: t.scheme_kind, context: t.context, questions: t.questions, scheme: t.scheme,
    criteria: t.scheme_kind === "criteria" ? jsonToRows(JSON.stringify(t.rubric)) : [], deletePages: t.delete_pages_after_marking,
    provider: t.provider, model: t.model ?? "", extractorModel: t.extractor_model ?? "",
  };
}

// There is no GET /api/assignments/{id}; the list is small, so the editor picks its template out of it.
const fetchTemplate = async (id: number) => (await api.get<AssignmentTemplate[]>("/api/assignments")).find((t) => t.id === id) ?? null;
const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export function AssignmentEditor({ pollMs = 3000 }: { pollMs?: number }) {
  const { id: param } = useParams();
  const nav = useNavigate();
  const isNew = param === "new";
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [loading, setLoading] = useState(!isNew);
  const [notFound, setNotFound] = useState(false);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [providers, setProviders] = useState<ProviderSpec[]>([]);
  const [customModel, setCustomModel] = useState(false);
  const [pages, setPages] = useState<Record<Upload, number[]>>({ paper: [], scheme: [] });
  const [extract, setExtract] = useState<ExtractStatus | null>(null);
  const [justRead, setJustRead] = useState<Upload | null>(null);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [draftSaved, setDraftSaved] = useState(false);
  const [pendingKind, setPendingKind] = useState<SchemeKind | null>(null);
  const [subjectTouched, setSubjectTouched] = useState(false);
  const [deleteTouched, setDeleteTouched] = useState(false);
  const loadedRef = useRef<number | null>(null);
  const lastSavedRef = useRef<string>("");
  const savingRef = useRef(false);
  const queuedRef = useRef(false);
  // Autosave runs from blur handlers, so it reads the latest state through a ref rather than a stale closure.
  const liveRef = useRef({ draft, templateId, reading: false, busy });
  // One in-flight POST /api/assignments at a time: concurrent callers (paper and scheme dropped back to back) share it.
  const creatingRef = useRef<Promise<number> | null>(null);

  const patch = (p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p }));

  useEffect(() => { api.get<Settings>("/api/settings").then(setSettings).catch(() => setSettings(null)); }, []);
  useEffect(() => { api.get<ProviderSpec[]>("/api/providers").then(setProviders).catch(() => setProviders([])); }, []);

  useEffect(() => {
    if (isNew) return;
    const id = Number(param);
    if (loadedRef.current === id) return;
    if (!Number.isInteger(id)) { setNotFound(true); setLoading(false); return; }
    setLoading(true);
    Promise.all([fetchTemplate(id), api.get<ExtractStatus>(`/api/assignments/${id}/extract`).catch(() => null)])
      .then(([t, s]) => {
        if (!t) { setNotFound(true); return; }
        loadedRef.current = id;
        const d = fromTemplate(t);
        lastSavedRef.current = JSON.stringify(toBody(d));
        setDraft(d); setPages({ paper: t.paper_page_ids, scheme: t.scheme_page_ids }); setExtract(s); setTemplateId(id); setSubjectTouched(true);
      })
      .catch((e) => setError(errMsg(e, "Could not load the assignment.")))
      .finally(() => setLoading(false));
  }, [param, isNew]);

  const reading = !!extract && (isActive(extract.paper.status) || isActive(extract.scheme.status));
  useEffect(() => { liveRef.current = { draft, templateId, reading, busy }; });

  // Poll the extraction jobs while one is queued or running; when one finishes, take its output from the server.
  useEffect(() => {
    if (!templateId || !extract || !reading) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const s = await api.get<ExtractStatus>(`/api/assignments/${templateId}/extract`);
        if (cancelled) return;
        const finished = (["paper", "scheme"] as Upload[]).filter((w) => isActive(extract[w].status) && s[w].status === "done");
        if (finished.length) {
          const t = await fetchTemplate(templateId);
          if (cancelled) return;
          if (t) {
            setDraft((d) => {
              const next = { ...d, ...(finished.includes("paper") ? { questions: t.questions } : {}), ...(finished.includes("scheme") ? { scheme: t.scheme } : {}) };
              lastSavedRef.current = JSON.stringify(toBody(next));
              return next;
            });
            setJustRead(finished[finished.length - 1]);
          }
        }
        setExtract(s);
      } catch {
        if (!cancelled) setTick((n) => n + 1);
      }
    }, pollMs);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [templateId, extract, reading, pollMs, tick]);

  const problem = useMemo(() => {
    if (!draft.kind) return "Choose the assignment type.";
    if (!draft.title.trim()) return "Give the assignment a title.";
    if (draft.provider && !draft.model.trim()) return "Give the model an id, or go back to Auto.";
    if (reading) return "Wait for the pages to be read.";
    return validateTemplate(draft.kind, draft.questions, draft.scheme, draft.criteria);
  }, [draft, reading]);

  // Switching between mark scheme and rubric clears the scheme rows (different shape) and keeps the questions;
  // switching to quick mark clears both, since it has no paper. Either asks first when something would be lost.
  const clearedBy = (kind: SchemeKind) => {
    const scheme = draft.kind !== "criteria" && draft.scheme.length > 0;
    const questions = kind === "criteria" && draft.questions.length > 0;
    return { scheme, questions };
  };
  const chooseKind = (kind: SchemeKind) => {
    if (kind === draft.kind) return;
    const lost = clearedBy(kind);
    if (lost.scheme || lost.questions) { setPendingKind(kind); return; }
    applyKind(kind);
  };
  // An essay's transcription is the whole record of the script, so a new rubric assignment defaults to keeping the
  // pages ("Off"); the other types follow the Settings default. A value the teacher chose by hand is left alone.
  const deletePagesFor = (kind: SchemeKind, d: Draft): boolean | null => {
    if (!isNew || deleteTouched) return d.deletePages;
    return kind === "rubric" ? false : null;
  };
  const applyKind = (kind: SchemeKind) => {
    setDraft((d) => ({ ...d, kind, scheme: [], questions: kind === "criteria" ? [] : d.questions, subject: subjectTouched ? d.subject : DEFAULT_SUBJECT[kind], deletePages: deletePagesFor(kind, d) }));
    setPendingKind(null);
  };

  /** Create the draft on the server the first time something needs an id (an upload, or Save). */
  const ensureTemplate = useCallback((): Promise<number> => {
    if (templateId) return Promise.resolve(templateId);
    if (creatingRef.current) return creatingRef.current;
    if (!draft.title.trim()) return Promise.reject(new ApiError(400, "bad_title", "Give the assignment a title first."));
    const body = toBody(draft);
    creatingRef.current = api.post<AssignmentTemplate>("/api/assignments", body)
      .then((t) => {
        lastSavedRef.current = JSON.stringify(body);
        loadedRef.current = t.id;
        setTemplateId(t.id);
        nav(`/assignments/${t.id}`, { replace: true });
        return t.id;
      })
      .finally(() => { creatingRef.current = null; });
    return creatingRef.current;
  }, [templateId, draft, nav]);

  const upload = async (what: Upload, files: File[]) => {
    if (files.length === 0) return;
    setBusy(what); setError(null); setOk(null); setJustRead(null);
    try {
      const id = await ensureTemplate();
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f, f.name));
      const r = await api.postForm<{ pages: { id: number }[] }>(`/api/assignments/${id}/${what}`, fd);
      setPages((p) => ({ ...p, [what]: r.pages.map((x) => x.id) }));
    } catch (e) { setError(errMsg(e, "Upload failed — check your connection and try again.")); }
    finally { setBusy(null); }
  };

  const read = async (what: Upload) => {
    if (!templateId) return;
    setBusy(`read-${what}`); setError(null); setOk(null); setJustRead(null);
    try {
      await api.post(`/api/assignments/${templateId}/extract/${what}`);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 409)) { setError(errMsg(e, "Could not start reading the pages.")); setBusy(null); return; }
    }
    setExtract((s) => ({ paper: s?.paper ?? { status: null, error: null, job_id: null }, scheme: s?.scheme ?? { status: null, error: null, job_id: null }, [what]: { status: "queued", error: null, job_id: null } }));
    setBusy(null);
  };

  const put = async (id: number, body: AssignmentBody) => {
    await api.put(`/api/assignments/${id}`, body);
    lastSavedRef.current = JSON.stringify(body);
  };

  // Draft autosave: whenever focus leaves a field and something changed, store it (once the template exists).
  // A blur that lands while a save is in flight queues one more save so quick tabbing never drops a change.
  const autosave = async (): Promise<void> => {
    const { draft: d, templateId: id, reading: r, busy: b } = liveRef.current;
    if (!id || !d.kind || !d.title.trim() || r || b) return;
    if (savingRef.current) { queuedRef.current = true; return; }
    const body = toBody(d);
    const json = JSON.stringify(body);
    if (json === lastSavedRef.current) return;
    savingRef.current = true;
    try { await put(id, body); setDraftSaved(true); setError(null); }
    catch (e) { setError(`Draft not saved: ${errMsg(e, "check your connection.")}`); }
    finally {
      savingRef.current = false;
      if (queuedRef.current) { queuedRef.current = false; void autosave(); }
    }
  };

  const save = async () => {
    if (problem || !draft.kind) return;
    setBusy("save"); setError(null); setOk(null); setDraftSaved(false);
    try {
      if (templateId) await put(templateId, toBody(draft));
      else await ensureTemplate();
      setOk("Saved. Pick it under Mark a script to use it.");
    } catch (e) { setError(errMsg(e, "Could not save — try again.")); }
    finally { setBusy(null); }
  };

  if (notFound) {
    return (
      <div className="page">
        <Link to="/assignments" className="breadcrumb">← Assignments</Link>
        <EmptyState title="This assignment no longer exists."><Link to="/assignments">Back to Assignments</Link></EmptyState>
      </div>
    );
  }
  if (loading) return <p className="page muted">Loading…</p>;

  const kind = draft.kind;
  const defaultDelete = settings ? settings.delete_pages_after_marking : null;
  const total = kind ? (kind === "criteria" ? draft.criteria.reduce((s, r) => s + (Number(r.max_score) || 0), 0) : schemeTotal(kind, draft.questions, draft.scheme)) : 0;
  const schemeName = kind === "rubric" ? "rubric" : "mark scheme";
  const status = (what: Upload) => extract?.[what] ?? null;

  // Model: Auto (draft.provider === null) follows Settings; a chosen provider must already have a key saved.
  const keys = settings?.keys ?? (settings?.has_key ? { [settings.provider]: settings.key_hint } : {});
  const hasKey = (id: string) => !!keys[id];
  const spec = providers.find((p) => p.id === draft.provider) ?? null;
  const anyKey = providers.some((p) => hasKey(p.id));
  const modelName = (providerId: string, modelId: string) => {
    const p = providers.find((x) => x.id === providerId);
    return `${p?.label ?? providerLabel[providerId] ?? providerId} · ${p?.models.find((m) => m.id === modelId)?.label ?? modelId}`;
  };
  const showCustomModel = draft.provider !== null && (customModel || !spec?.models.some((m) => m.id === draft.model));
  const pickProvider = (id: string) => { setCustomModel(false); patch({ provider: id, model: providers.find((p) => p.id === id)?.default_model ?? "" }); };
  const chooseOwnModel = () => {
    const from = (settings && hasKey(settings.provider) ? settings.provider : providers.find((p) => hasKey(p.id))?.id) ?? null;
    if (from) pickProvider(from);
  };

  const uploadBlock = (what: Upload, title: string, readLabel: string) => {
    const s = status(what);
    const ids = pages[what];
    const active = isActive(s?.status);
    return (
      <div className="grid-2" style={{ alignItems: "start", marginBottom: 16 }}>
        <div>
          <DropZone onFiles={(f) => upload(what, f)} title={title} hint={templateId ? "PDF, JPG, PNG or HEIC — replaces the current pages" : "PDF, JPG, PNG or HEIC — the draft is created on the first upload"} />
          {busy === what && <p className="help" style={{ marginTop: 8 }}>Uploading…</p>}
        </div>
        <div>
          {ids.length > 0 ? (
            <>
              <p className="help" style={{ marginBottom: 8 }}>{ids.length} page{ids.length === 1 ? "" : "s"} uploaded</p>
              <div className="pages-strip" style={{ marginBottom: 12 }}>
                {ids.map((pid, i) => <img key={pid} className="grayscale" src={`/api/pages/${pid}`} alt={`${title} page ${i + 1}`} />)}
              </div>
              <div className="actions" style={{ alignItems: "center" }}>
                <Button variant="secondary" onClick={() => read(what)} disabled={active || busy !== null}>{active ? "Reading…" : readLabel}</Button>
                {active && <span className="help">Reading the pages — this takes about a minute. The table unlocks when it's done.</span>}
                {!active && justRead === what && <span className="help">Done — check the rows below and fix anything we misread.</span>}
              </div>
              {!active && s?.status === "failed" && <div style={{ marginTop: 12 }}><Notice kind="error">Could not read the pages{s.error ? `: ${s.error}` : ""}. Try again.</Notice></div>}
            </>
          ) : <p className="help">No pages yet. Upload them, or type the rows in below.</p>}
        </div>
      </div>
    );
  };

  return (
    <div className="page" onBlur={() => { void autosave(); }}>
      <Link to="/assignments" className="breadcrumb">← Assignments</Link>
      <div className="page-header">
        <div>
          <h1>{isNew && !templateId ? "New assignment" : draft.title.trim() || "Assignment"}</h1>
          <p className="meta">Choose the type, add the paper and the {schemeName}, then save. Drafts are kept as you go.</p>
        </div>
        {kind && <div className="meta tabular">{draft.questions.length > 0 && `${draft.questions.length} question${draft.questions.length === 1 ? "" : "s"} · `}{total} marks</div>}
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {ok && <Notice kind="ok">{ok}</Notice>}

      <div className="field" style={{ marginTop: 16 }}>
        <label>Type</label>
        <div className="seg" role="radiogroup" aria-label="Assignment type">
          {KINDS.map((k) => (
            <label key={k} className={`seg-opt ${kind === k ? "on" : ""}`}><input type="radio" name="kind" checked={kind === k} onChange={() => chooseKind(k)} />{kindLabel[k]}</label>
          ))}
        </div>
        <span className="help">Mark scheme: marks per question part (M1, A1…). Rubric: bands per criterion for an essay. Quick mark: a short criteria list, no paper.</span>
      </div>

      {kind && (
        <>
          <div className="grid-2">
            <div className="field"><label htmlFor="title">Title</label><input id="title" className="input" placeholder="Sec 4 · Quadratics worksheet 3" value={draft.title} onChange={(e) => patch({ title: e.target.value })} /></div>
            <div className="field"><label>Subject</label>
              <div className="seg" role="radiogroup" aria-label="Subject">
                {(["math", "language", "science"] as Subject[]).map((s) => (
                  <label key={s} className={`seg-opt ${draft.subject === s ? "on" : ""}`}><input type="radio" name="subject" checked={draft.subject === s} onChange={() => { setSubjectTouched(true); patch({ subject: s }); }} />{subjectLabel[s]}</label>
                ))}
              </div></div>
          </div>

          {kind !== "criteria" && (
            <section className="section" aria-label="Question paper">
              <div className="section-head"><h2>Question paper</h2><span className="help">Upload the paper and we read the questions and parts; check the table and correct anything.</span></div>
              {uploadBlock("paper", "Drop the question paper here", "Read questions")}
              <QuestionsTable rows={draft.questions} onChange={(questions) => patch({ questions })} disabled={reading} />
            </section>
          )}

          {kind === "mark_scheme" && (
            <section className="section" aria-label="Mark scheme">
              <div className="section-head"><h2>Mark scheme</h2><span className="help">One row per question part, with its allocations (M1, A1, B1…). Every question needs a row.</span></div>
              {uploadBlock("scheme", "Drop the mark scheme here", "Read mark scheme")}
              <MarkSchemeTable questions={draft.questions} rows={draft.scheme as MarkSchemeEntry[]} onChange={(scheme) => patch({ scheme })} disabled={reading} />
            </section>
          )}

          {kind === "rubric" && (
            <section className="section" aria-label="Rubric">
              <div className="section-head"><h2>Rubric</h2><span className="help">Criteria with their bands, best band first.</span></div>
              {uploadBlock("scheme", "Drop the rubric here", "Read rubric")}
              <RubricTable rows={draft.scheme as RubricBands[]} onChange={(scheme) => patch({ scheme })} disabled={reading} />
            </section>
          )}

          {kind === "criteria" && (
            <section className="section" aria-label="Criteria">
              <div className="section-head"><h2>Criteria</h2><span className="help">Applied to every question of the script.</span></div>
              <CriteriaEditor rows={draft.criteria} onChange={(criteria) => patch({ criteria })} />
            </section>
          )}

          <section className="section" aria-label="Notes">
            <div className="section-head"><h2>Notes</h2><span className="help">Anything the marker should know.</span></div>
            <div className="field"><label htmlFor="notes">Notes (optional)</label>
              <textarea id="notes" className="input" placeholder="Penalise missing units once. Accept any correct method. ECF applies." value={draft.context} onChange={(e) => patch({ context: e.target.value })} /></div>
            <div className="field" style={{ maxWidth: 360 }}><label htmlFor="delete-pages">Delete student pages after marking</label>
              <select id="delete-pages" className="input" value={draft.deletePages === null ? "" : draft.deletePages ? "on" : "off"}
                onChange={(e) => { setDeleteTouched(true); patch({ deletePages: e.target.value === "" ? null : e.target.value === "on" }); }}>
                <option value="">Follow default{defaultDelete === null ? "" : ` (${defaultDelete ? "on" : "off"})`}</option>
                <option value="on">On</option>
                <option value="off">Off</option>
              </select>
              <span className="help">Student pages are deleted as soon as a script is done; the marking record keeps the transcription and every mark. Change the default under Settings.</span></div>
          </section>

          <section className="section" aria-label="Model">
            <div className="section-head"><h2>Model</h2><span className="help">Which model marks this assignment. Auto follows Settings, so changing Settings changes it too.</span></div>
            <div className="field" style={{ maxWidth: 420 }}>
              <div className="seg" role="radiogroup" aria-label="Model">
                <label className={`seg-opt ${draft.provider === null ? "on" : ""}`}>
                  <input type="radio" name="model-mode" checked={draft.provider === null} onChange={() => { setCustomModel(false); patch({ provider: null }); }} />Auto — follow Settings
                </label>
                <label className={`seg-opt ${draft.provider !== null ? "on" : ""}`}>
                  <input type="radio" name="model-mode" checked={draft.provider !== null} onChange={chooseOwnModel} />Choose a model
                </label>
              </div>
              {draft.provider === null && settings && <span className="help">Using {modelName(settings.provider, settings.model)} from Settings</span>}
              {draft.provider === null && providers.length > 0 && !anyKey && <span className="help">No keys saved yet — add one under Settings to choose a model here.</span>}
            </div>
            {draft.provider !== null && (
              <>
                <div className="field"><label>Provider</label>
                  <div className="seg" role="radiogroup" aria-label="Model provider">
                    {providers.map((p) => (
                      <label key={p.id} className={`seg-opt ${draft.provider === p.id ? "on" : ""}${hasKey(p.id) ? "" : " off"}`} title={hasKey(p.id) ? undefined : NO_KEY}>
                        <input type="radio" name="model-provider" checked={draft.provider === p.id} disabled={!hasKey(p.id)} onChange={() => pickProvider(p.id)} />{p.label}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="grid-2">
                  <div className="field"><label>Model</label>
                    <select className="input" aria-label="Model id" value={showCustomModel ? CUSTOM : draft.model}
                      onChange={(e) => { if (e.target.value === CUSTOM) setCustomModel(true); else { setCustomModel(false); patch({ model: e.target.value }); } }}>
                      {(spec?.models ?? []).map((m) => <option key={m.id} value={m.id}>{m.label}{m.vision ? " · reads pages" : " · text only"}</option>)}
                      <option value={CUSTOM}>Custom model id…</option>
                    </select>
                    {showCustomModel && <input className="input" aria-label="Custom model id" placeholder="exact model id" value={draft.model} onChange={(e) => patch({ model: e.target.value })} />}
                  </div>
                  <div className="field"><label htmlFor="assignment-extractor">Different model for reading pages (optional)</label>
                    <input id="assignment-extractor" className="input" placeholder="leave blank to use the same model" value={draft.extractorModel} onChange={(e) => patch({ extractorModel: e.target.value })} />
                    <span className="help">Use a cheap vision model to transcribe, and a stronger one to mark.</span></div>
                </div>
              </>
            )}
          </section>

        </>
      )}

      <hr className="rule-2" style={{ marginTop: 24 }} />
      <div className="actions" style={{ marginTop: 16, alignItems: "center" }}>
        <Button variant="primary" size="lg" onClick={save} disabled={busy !== null || !!problem} title={problem ?? undefined}>{busy === "save" ? "Saving…" : "Save"}</Button>
        <span className="help" aria-live="polite">{problem ?? "Ready to save."}</span>
        {draftSaved && <span className="help" role="status">Draft saved</span>}
      </div>

      {pendingKind && (
        <Dialog title="Change the type?" onClose={() => setPendingKind(null)}
          footer={<><Button variant="secondary" onClick={() => setPendingKind(null)}>Cancel</Button><Button variant="primary" onClick={() => applyKind(pendingKind)}>Change type</Button></>}>
          <p>{pendingKind === "criteria"
            ? `The questions${clearedBy(pendingKind).scheme ? ` and ${schemeName} rows` : ""} you have entered will be cleared — quick mark has no paper. The title and notes stay.`
            : `The ${schemeName} rows you have entered will be cleared. The title, questions and notes stay.`}</p>
        </Dialog>
      )}
    </div>
  );
}

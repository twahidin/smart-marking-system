export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-SG", { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export function elapsed(iso: string | null | undefined): string {
  if (!iso) return "";
  const start = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z").getTime();
  const s = Math.max(0, Math.floor((Date.now() - start) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export const subjectLabel: Record<string, string> = { math: "Maths", language: "English", science: "Science", mt: "MT", computing: "Computing" };

/** The three Mother Tongue languages, in the order the Language select offers them. */
export const languageLabel: Record<string, string> = { zh: "Chinese", ms: "Malay", ta: "Tamil" };

export const schemeLabel: Record<string, string> = { criteria: "Criteria", mark_scheme: "Mark scheme", rubric: "Rubric" };

/** Mirrors the labels in sms.providers.registry, for the pages that name a provider without loading /api/providers. */
export const providerLabel: Record<string, string> = {
  tokenrouter: "TokenRouter", openrouter: "OpenRouter", openai: "OpenAI", anthropic: "Anthropic",
  moonshot: "Moonshot (Kimi)", qwen: "Qwen (Alibaba Model Studio)", google: "Google Gemini",
};

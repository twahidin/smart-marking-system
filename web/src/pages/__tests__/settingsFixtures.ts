import type { ProviderSpec, Settings } from "../../api/types";

/** The provider list and the saved settings both the Settings page tests and the *By subject*
 *  table's tests render against: a key is saved for TokenRouter, none for Google Gemini. */
export const providers: ProviderSpec[] = [
  {
    id: "tokenrouter", label: "TokenRouter", transport: "openai_compatible", base_url: "https://api.tokenrouter.com/v1", mode: "JSON",
    default_model: "z-ai/glm-5.3-flash", default_rpm: 60, key_url: "https://www.tokenrouter.com/", note: "", base_url_editable: false,
    custom_models: false, models: [{ id: "z-ai/glm-5.3-flash", label: "GLM 5.3 Flash", vision: true }],
  },
  {
    id: "google", label: "Google Gemini", transport: "openai_compatible", base_url: "https://generativelanguage.googleapis.com/v1beta/openai/", mode: "JSON",
    default_model: "gemini-3.8-flash", default_rpm: 10, key_url: "https://aistudio.google.com/apikey", base_url_editable: false,
    note: "Free tier: no card needed; roughly 10–30 requests a minute.",
    custom_models: false, models: [{ id: "gemini-3.8-flash", label: "Gemini 3.8 Flash", vision: true }],
  },
];

export const settings: Settings = {
  provider: "tokenrouter", model: "z-ai/glm-5.3-flash", base_url: null, extractor_model: null, rpm_limit: 60, confidence_threshold: 0,
  has_key: true, key_hint: "abcd", keys: { tokenrouter: "abcd" }, auto_reflect: true, delete_pages_after_marking: true,
  telegram_linked: false, telegram_bot_hint: "", telegram_chat_id: null, telegram_instant: true, telegram_daily_time: "07:00",
  timezone: "Asia/Singapore", app_url: null,
};

/** No subject has a model of its own yet. */
export const noSubjectModels = { math: null, language: null, science: null, mt: null, computing: null };

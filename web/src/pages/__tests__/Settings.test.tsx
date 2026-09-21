import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Settings } from "../Settings";
import { noSubjectModels, providers, settings } from "./settingsFixtures";

/** What the mock server currently holds; a test can swap it before rendering with `serve()`. */
let served: { providers: any[]; settings: any; subjectModels: any } = { providers, settings, subjectModels: noSubjectModels };
const serve = (p: any[], s: any) => { served = { ...served, providers: p, settings: s }; };
const calls: { path: string; method: string; body: any }[] = [];
const saved: any[] = [];
const deleted: string[] = [];
/** >0 makes an unforced DELETE of a provider key answer 409 `in_use` with this count. */
let keysInUse = 0;

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const noContent = () => Promise.resolve(new Response(null, { status: 204 }));

function mockFetch(onModels: () => Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      calls.push({ path, method, body });
      if (path === "/api/providers") return json(served.providers);
      if (path === "/api/settings/subject-models" && method === "GET") return json(served.subjectModels);
      if (path.startsWith("/api/settings/subject-models/") && method === "PUT") {
        const subject = path.slice("/api/settings/subject-models/".length);
        const row = { provider: body.provider, model: body.model, extractor_model: body.extractor_model ?? null };
        served.subjectModels = { ...served.subjectModels, [subject]: row };
        return json(row);
      }
      if (path.startsWith("/api/settings/subject-models/") && method === "DELETE") {
        const subject = path.slice("/api/settings/subject-models/".length);
        served.subjectModels = { ...served.subjectModels, [subject]: null };
        return noContent();
      }
      if (path === "/api/settings" && method !== "PUT") return json(served.settings);
      if (path === "/api/settings" && method === "PUT") {
        saved.push(body);
        const { telegram_bot_token: token, ...rest } = body;
        // The server echoes what it stored; a token that arrives links the chat, as /start would have.
        served.settings = { ...served.settings, ...rest,
          ...(token ? { telegram_linked: true, telegram_bot_hint: String(token).slice(-4), telegram_chat_id: "998877665544" } : {}) };
        return json(served.settings);
      }
      if (path === "/api/settings/models") return Promise.resolve(onModels());
      if (path === "/api/settings/telegram/test" && method === "POST") return noContent();
      if (path === "/api/settings/telegram" && method === "DELETE") {
        served.settings = { ...served.settings, telegram_linked: false, telegram_bot_hint: "", telegram_chat_id: null };
        return noContent();
      }
      if (path.startsWith("/api/settings/models/") && method === "POST") {
        const provider = path.slice("/api/settings/models/".length);
        const model = { id: body.model_id, label: body.label || body.model_id, vision: body.vision, custom: true };
        served.providers = served.providers.map((p) => (p.id === provider ? { ...p, models: [...p.models, model] } : p));
        return json(model, 201);
      }
      if (path.startsWith("/api/settings/models/") && method === "DELETE") {
        const [provider, ...idParts] = path.slice("/api/settings/models/".length).split("/");
        const id = idParts.join("/");
        served.providers = served.providers.map((p) => (p.id === provider ? { ...p, models: p.models.filter((m: any) => m.id !== id) } : p));
        return noContent();
      }
      if (path.startsWith("/api/settings/keys/") && method === "DELETE") {
        const suffix = path.slice("/api/settings/keys/".length);
        if (keysInUse && !suffix.includes("force=1")) {
          return json({ count: keysInUse, error: { code: "in_use", message: `${keysInUse} assignments use this provider — they will fail to mark until you pick another model` } }, 409);
        }
        deleted.push(suffix);
        return noContent();
      }
      return Promise.reject(new Error(`Unexpected fetch to ${path}`));
    }),
  );
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); served = { providers, settings, subjectModels: noSubjectModels }; calls.length = 0; saved.length = 0; deleted.length = 0; keysInUse = 0; });

describe("Settings — one key per provider", () => {
  it("shows the saved key for the selected provider only, and removes it on request", async () => {
    mockFetch(() => new Response(JSON.stringify({ models: [] }), { status: 200 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    const key = await screen.findByLabelText("API key");
    expect(key).toHaveAttribute("placeholder", "Saved key ending …abcd — leave blank to keep");
    expect(screen.getByRole("radio", { name: /TokenRouter/ }).closest("label")).toHaveTextContent("✓");
    expect(screen.getByRole("radio", { name: /Google Gemini/ }).closest("label")).not.toHaveTextContent("✓");
    await userEvent.click(screen.getByRole("radio", { name: /Google Gemini/ }));
    expect(key).toHaveAttribute("placeholder", "No key saved for Google Gemini yet — paste one");
    expect(screen.getByRole("button", { name: "Load models from provider" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Remove key/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /TokenRouter/ }));
    expect(screen.getByRole("button", { name: "Load models from provider" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Remove TokenRouter key" }));
    expect(deleted).toEqual(["tokenrouter"]);
    expect(key).toHaveAttribute("placeholder", "No key saved for TokenRouter yet — paste one");
  });

  it("asks before removing a key assignments are pinned to, and forces only on a yes", async () => {
    keysInUse = 3;
    mockFetch(() => new Response(JSON.stringify({ models: [] }), { status: 200 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    const key = await screen.findByLabelText("API key");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    await userEvent.click(screen.getByRole("button", { name: "Remove TokenRouter key" }));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith(
      "3 assignments use this provider — remove the key anyway? They will fail to mark until you pick another model."));
    expect(deleted).toEqual([]);                     // said no: the key is still there
    expect(key).toHaveAttribute("placeholder", "Saved key ending …abcd — leave blank to keep");

    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Remove TokenRouter key" }));
    await waitFor(() => expect(deleted).toEqual(["tokenrouter?force=1"]));
    expect(await screen.findByText("TokenRouter key removed.")).toBeInTheDocument();
    expect(key).toHaveAttribute("placeholder", "No key saved for TokenRouter yet — paste one");
  });
});

describe("Settings — free options", () => {
  it("labels the note as free options for Google Gemini and adopts its default rpm", async () => {
    mockFetch(() => new Response(JSON.stringify({ models: [] }), { status: 200 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    expect(await screen.findByRole("radio", { name: "TokenRouter" })).toBeChecked();
    expect(screen.queryByText("Free options:")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Google Gemini" }));
    expect(screen.getByText("Free options:")).toBeInTheDocument();
    expect(screen.getByText(/no card needed/)).toBeInTheDocument();
    expect(screen.getByLabelText("Requests per minute")).toHaveValue(10);
  });
});

describe("Settings — nightly reflection", () => {
  it("saves the auto_reflect checkbox with the rest of the settings", async () => {
    mockFetch(() => new Response(JSON.stringify({ models: [] }), { status: 200 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    const box = await screen.findByRole("checkbox", { name: "Run reflection nightly on new corrections" });
    expect(box).toBeChecked();
    await userEvent.click(box);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(saved[0].auto_reflect).toBe(false);
  });
});

describe("Settings — load models from provider", () => {
  it("adds the account's models to the dropdown, without duplicating curated ones", async () => {
    mockFetch(() => new Response(JSON.stringify({ models: ["z-ai/glm-5.3-flash", "z-ai/glm-5.3-free", "qwen/qwen3-vl-plus"] }), { status: 200 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("button", { name: "Load models from provider" }));
    const group = await screen.findByRole("group", { name: "From your account" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "z-ai/glm-5.3-free" })).toBeInTheDocument();
    expect(screen.getAllByRole("option", { name: /GLM 5.3 Flash/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Reload models (3 found)" })).toBeInTheDocument();
  });

  it("shows the provider's error when the list call fails", async () => {
    mockFetch(() => new Response(JSON.stringify({ error: { code: "provider_error", message: "HTTP 401: Invalid API key" } }), { status: 502 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("button", { name: "Load models from provider" }));
    expect(await screen.findByText("HTTP 401: Invalid API key")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "From your account" })).not.toBeInTheDocument();
  });
});

describe("Settings — delete pages after marking", () => {
  it("saves the global default with the rest of the settings", async () => {
    mockFetch(() => new Response(JSON.stringify({ models: [] }), { status: 200 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    const box = await screen.findByRole("checkbox", { name: "Delete student pages after marking (default for new assignments)" });
    expect(box).toBeChecked();
    await userEvent.click(box);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(saved[0].delete_pages_after_marking).toBe(false);
  });
});

describe("Settings — notifications", () => {
  it("shows link status, saves the token and daily time, tests and unlinks", async () => {
    mockFetch(() => new Response(JSON.stringify({ models: [] }), { status: 200 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    expect(await screen.findByText(/Not linked/)).toBeInTheDocument();
    expect(screen.getByLabelText("Telegram bot token")).toHaveAttribute("placeholder", "Paste the token from @BotFather");
    expect(screen.queryByRole("button", { name: "Send test message" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Telegram bot token"), "123:abc");
    await userEvent.clear(screen.getByLabelText("Daily report at"));
    await userEvent.type(screen.getByLabelText("Daily report at"), "18:00");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    const put = saved[saved.length - 1];
    expect(put.telegram_bot_token).toBe("123:abc");
    expect(put.telegram_daily_time).toBe("18:00");
    expect(put.timezone).toBe("Asia/Singapore");
    // Once the server reports the chat as linked, the status line and the buttons change.
    expect(await screen.findByText("Linked \u2713 (chat \u20265544)")).toBeInTheDocument();
    // The token is write-only: the field empties on save so the placeholder can report what is stored.
    expect(screen.getByLabelText("Telegram bot token")).toHaveValue("");
    expect(screen.getByLabelText("Telegram bot token")).toHaveAttribute("placeholder", "Saved token ending \u2026:abc \u2014 leave blank to keep");
    await userEvent.click(screen.getByRole("button", { name: "Send test message" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/settings/telegram/test")).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: "Unlink" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/settings/telegram")).toBe(true));
    expect(await screen.findByText(/Not linked/)).toBeInTheDocument();
  });

  it("submits the notification fields on every save, including from other sections", async () => {
    mockFetch(() => new Response(JSON.stringify({ models: [] }), { status: 200 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Run reflection nightly on new corrections" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    const put = saved[saved.length - 1];
    expect(Object.keys(put)).toEqual(expect.arrayContaining(["telegram_instant", "telegram_daily_time", "timezone", "app_url"]));
    expect(put.telegram_instant).toBe(true);
    expect(put.telegram_daily_time).toBe("07:00");
    expect(put.timezone).toBe("Asia/Singapore");
    expect(put.app_url).toBeNull();
  });
});

describe("Settings \u2014 by subject", () => {
  it("puts the model-by-subject table under the provider form and saves a row on its own", async () => {
    mockFetch(() => new Response(JSON.stringify({ models: [] }), { status: 200 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "By subject" })).toBeInTheDocument();
    expect(screen.getByText("New assignments follow their subject's model; each assignment can still pin its own.")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Model by subject" });
    expect(within(table).getAllByRole("rowheader").map((c) => c.textContent)).toEqual(
      expect.arrayContaining(["Maths", "English", "Science"]));

    const mt = screen.getByRole("radiogroup", { name: "MT model" }).closest("tr")!;
    await userEvent.click(within(mt).getByRole("radio", { name: "Choose" }));
    await userEvent.click(within(mt).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.path === "/api/settings/subject-models/mt")).toBe(true));
    const put = calls.find((c) => c.method === "PUT" && c.path === "/api/settings/subject-models/mt")!;
    expect(put.body).toEqual({ provider: "tokenrouter", model: "z-ai/glm-5.3-flash", extractor_model: null });
    // The page's own Save still submits the settings form, not the row.
    expect(saved).toHaveLength(0);
  });
});

describe("Settings \u2014 my models", () => {
  const customProviders = [
    {
      id: "openai", label: "OpenAI", transport: "openai", base_url: null, mode: "TOOLS", default_model: "gpt-5.2-mini", default_rpm: 60,
      key_url: "https://platform.openai.com/api-keys", note: "", base_url_editable: false, api_params: null, custom_models: false,
      models: [{ id: "gpt-5.2-mini", label: "GPT-5.2 mini", vision: true }],
    },
    {
      id: "openrouter", label: "OpenRouter", transport: "openai_compatible", base_url: "https://openrouter.ai/api/v1", mode: "JSON",
      default_model: "z-ai/glm-5.3-free", default_rpm: 20, key_url: "https://openrouter.ai/keys", note: "", base_url_editable: false, api_params: null,
      custom_models: true, models: [{ id: "z-ai/glm-5.3-free", label: "GLM 5.3 Free", vision: true }],
    },
  ];

  it("adds and removes a custom model for OpenRouter and hides the list for OpenAI", async () => {
    serve(customProviders, { ...settings, provider: "openai", model: "gpt-5.2-mini", keys: { openai: "abcd" } });
    mockFetch(() => new Response(JSON.stringify({ models: [] }), { status: 200 }));
    render(<MemoryRouter><Settings /></MemoryRouter>);
    expect(await screen.findByRole("radio", { name: /OpenAI/ })).toBeChecked();
    expect(screen.queryByLabelText("Model id")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /OpenRouter/ }));
    await userEvent.type(screen.getByLabelText("Model id"), "google/gemini-3.8-flash");
    await userEvent.click(screen.getByRole("button", { name: "Add model" }));
    expect(await screen.findByRole("option", { name: /Gemini 3.8 Flash|google\/gemini-3.8-flash/ })).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/settings/models/openrouter"
      && c.body.model_id === "google/gemini-3.8-flash" && c.body.vision === true)).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /Remove google\/gemini-3.8-flash/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/settings/models/openrouter/google/gemini-3.8-flash")).toBe(true));
    await waitFor(() => expect(screen.queryByRole("option", { name: /google\/gemini-3.8-flash/ })).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("radio", { name: /OpenAI/ }));
    expect(screen.queryByLabelText("Model id")).not.toBeInTheDocument();
  });
});

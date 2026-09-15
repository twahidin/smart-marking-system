import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Settings } from "../Settings";

const providers = [
  {
    id: "tokenrouter", label: "TokenRouter", transport: "openai_compatible", base_url: "https://api.tokenrouter.com/v1", mode: "JSON",
    default_model: "z-ai/glm-5.3-flash", default_rpm: 60, key_url: "https://www.tokenrouter.com/", note: "", base_url_editable: false, api_params: null,
    models: [{ id: "z-ai/glm-5.3-flash", label: "GLM 5.3 Flash", vision: true }],
  },
  {
    id: "google", label: "Google Gemini", transport: "openai_compatible", base_url: "https://generativelanguage.googleapis.com/v1beta/openai/", mode: "JSON",
    default_model: "gemini-3.8-flash", default_rpm: 10, key_url: "https://aistudio.google.com/apikey", base_url_editable: false, api_params: null,
    note: "Free tier: no card needed; roughly 10–30 requests a minute.",
    models: [{ id: "gemini-3.8-flash", label: "Gemini 3.8 Flash", vision: true }],
  },
];
const settings = { provider: "tokenrouter", model: "z-ai/glm-5.3-flash", base_url: null, extractor_model: null, rpm_limit: 60, confidence_threshold: 0, has_key: true, key_hint: "abcd", auto_reflect: true };

function mockFetch(onModels: () => Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/providers") return Promise.resolve(new Response(JSON.stringify(providers), { status: 200 }));
      if (path === "/api/settings" && init?.method !== "PUT") return Promise.resolve(new Response(JSON.stringify(settings), { status: 200 }));
      if (path === "/api/settings" && init?.method === "PUT") { saved.push(JSON.parse(String(init.body))); return Promise.resolve(new Response(JSON.stringify({ ...settings, ...saved[saved.length - 1] }), { status: 200 })); }
      if (path === "/api/settings/models") return Promise.resolve(onModels());
      return Promise.reject(new Error(`Unexpected fetch to ${path}`));
    }),
  );
}
const saved: any[] = [];

afterEach(() => { vi.unstubAllGlobals(); saved.length = 0; });

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

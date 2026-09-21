import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { noSubjectModels, providers, settings } from "../../__tests__/settingsFixtures";
import { SubjectModels } from "../SubjectModels";

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const noContent = () => Promise.resolve(new Response(null, { status: 204 }));

let stored: any = noSubjectModels;
/** When set, every PUT answers with this error instead of saving. */
let putError: { code: string; message: string } | null = null;
const calls: { path: string; method: string; body: any }[] = [];

function mockFetch() {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ path, method, body });
    if (path === "/api/settings/subject-models" && method === "GET") return json(stored);
    const subject = path.slice("/api/settings/subject-models/".length);
    if (method === "PUT") {
      if (putError) return json({ error: putError }, 400);
      const row = { provider: body.provider, model: body.model, extractor_model: body.extractor_model ?? null };
      stored = { ...stored, [subject]: row };
      return json(row);
    }
    if (method === "DELETE") { stored = { ...stored, [subject]: null }; return noContent(); }
    return Promise.reject(new Error(`Unexpected fetch to ${method} ${path}`));
  }));
}

const show = () => render(<SubjectModels providers={providers} settings={settings} />);
const row = (subject: string) => screen.getByRole("radiogroup", { name: `${subject} model` }).closest("tr")!;

afterEach(() => { vi.unstubAllGlobals(); stored = noSubjectModels; putError = null; calls.length = 0; });

describe("SubjectModels", () => {
  it("lists every subject on Auto, with the hint each one needs", async () => {
    mockFetch();
    show();
    const table = await screen.findByRole("table", { name: "Model by subject" });
    expect(within(table).getAllByRole("rowheader").map((c) => c.textContent?.replace(/Pick a model.*/, "")))
      .toEqual(["Maths", "English", "Science", "MT", "Computing"]);
    for (const s of ["Maths", "English", "Science", "MT", "Computing"]) {
      expect(within(row(s)).getByRole("radio", { name: "Auto" })).toBeChecked();
      expect(within(row(s)).queryByRole("radiogroup", { name: "Model provider" })).not.toBeInTheDocument();
    }
    expect(within(row("MT")).getByText("Pick a model that reads Chinese, Malay or Tamil handwriting well")).toBeInTheDocument();
    expect(within(row("Computing")).getByText("Pick a model that is strong at code")).toBeInTheDocument();
    expect(within(row("Maths")).queryByText(/^Pick a model/)).not.toBeInTheDocument();
  });

  it("saves a row on its own, and only that row", async () => {
    mockFetch();
    show();
    await screen.findByRole("table", { name: "Model by subject" });
    const mt = row("MT");
    await userEvent.click(within(mt).getByRole("radio", { name: "Choose" }));

    // The tiles start on the provider Settings uses; one with no key saved cannot be picked.
    const tiles = within(mt).getByRole("radiogroup", { name: "Model provider" });
    expect(within(tiles).getByRole("radio", { name: "TokenRouter" })).toBeChecked();
    const google = within(tiles).getByRole("radio", { name: "Google Gemini" });
    expect(google).toBeDisabled();
    expect(google.closest("label")).toHaveAttribute("title", "No key saved — add one under Settings");
    expect(within(mt).getByLabelText("Model id")).toHaveValue("z-ai/glm-5.3-flash");

    await userEvent.type(within(mt).getByLabelText("Different model for reading pages (optional)"), "gemini-3.8-flash");
    await userEvent.click(within(mt).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByText("MT saved.")).toBeInTheDocument());
    expect(calls.filter((c) => c.method === "PUT")).toEqual([{
      path: "/api/settings/subject-models/mt", method: "PUT",
      body: { provider: "tokenrouter", model: "z-ai/glm-5.3-flash", extractor_model: "gemini-3.8-flash" },
    }]);
    // Every other row was left alone.
    expect(within(row("Computing")).getByRole("radio", { name: "Auto" })).toBeChecked();
  });

  it("switching a saved row back to Auto removes its default", async () => {
    stored = { ...noSubjectModels, computing: { provider: "tokenrouter", model: "z-ai/glm-5.3-flash", extractor_model: null } };
    mockFetch();
    show();
    await screen.findByRole("table", { name: "Model by subject" });
    const computing = row("Computing");
    expect(within(computing).getByRole("radio", { name: "Choose" })).toBeChecked();
    expect(within(computing).getByLabelText("Model id")).toHaveValue("z-ai/glm-5.3-flash");

    await userEvent.click(within(computing).getByRole("radio", { name: "Auto" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/settings/subject-models/computing")).toBe(true));
    expect(within(computing).queryByRole("radiogroup", { name: "Model provider" })).not.toBeInTheDocument();
  });

  it("does not call the server when a row that was never saved goes back to Auto", async () => {
    mockFetch();
    show();
    await screen.findByRole("table", { name: "Model by subject" });
    await userEvent.click(within(row("Science")).getByRole("radio", { name: "Choose" }));
    await userEvent.click(within(row("Science")).getByRole("radio", { name: "Auto" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
  });

  it("still clears a row when the initial load failed and nothing is known", async () => {
    // `saved === null` is "we never found out", not "nothing is saved" — skipping the DELETE there
    // would leave a pinned model in place while the row read Auto.
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      calls.push({ path, method, body: null });
      if (method === "GET") return json({ error: { code: "server_error", message: "Could not load the subject models" } }, 500);
      if (method === "DELETE") return noContent();
      return Promise.reject(new Error(`Unexpected fetch to ${method} ${path}`));
    }));
    show();
    expect(await screen.findByText("Could not load the subject models")).toBeInTheDocument();
    // The row reads Auto because nothing loaded, so put it on Choose and back again.
    await userEvent.click(within(row("Computing")).getByRole("radio", { name: "Choose" }));
    await userEvent.click(within(row("Computing")).getByRole("radio", { name: "Auto" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/settings/subject-models/computing")).toBe(true));
    expect(await screen.findByText("Computing follows Settings again.")).toBeInTheDocument();
  });

  it("shows the server's message when a row will not save", async () => {
    putError = { code: "no_key_for_provider", message: "Save a TokenRouter key under Settings first" };
    mockFetch();
    show();
    await screen.findByRole("table", { name: "Model by subject" });
    await userEvent.click(within(row("MT")).getByRole("radio", { name: "Choose" }));
    await userEvent.click(within(row("MT")).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Save a TokenRouter key under Settings first")).toBeInTheDocument();
    expect(within(row("MT")).getByRole("radio", { name: "Choose" })).toBeChecked();
  });
});

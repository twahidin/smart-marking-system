import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Setup } from "../Setup";

const calls: { path: string; method: string; body: any }[] = [];
let needsSetup = true;
let setupStatus = 204;
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function mockFetch() {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input); const method = init?.method ?? "GET";
    calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (path === "/api/setup/status") return json({ needs_setup: needsSetup });
    if (path === "/api/setup" && method === "POST") {
      if (setupStatus === 204) return Promise.resolve(new Response(null, { status: 204 }));
      return json({ error: { code: "already_set_up", message: "already" } }, 409);
    }
    return json({ error: { code: "not_found", message: "nope" } }, 404);
  }));
}

function renderAt(path = "/setup") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/setup" element={<Setup />} />
        <Route path="/sign-in" element={<p>sign-in page</p>} />
        <Route path="/settings" element={<p>settings page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => { vi.unstubAllGlobals(); calls.length = 0; needsSetup = true; setupStatus = 204; });

describe("Setup wizard", () => {
  it("creates the password and continues to Settings step 2", async () => {
    mockFetch(); renderAt();
    const form = await screen.findByRole("form", { name: "Set up Smart Marking" });
    expect(form).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Password"), "teachers-2026");
    await user.type(screen.getByLabelText("Type it again"), "teachers-2026");
    await user.click(screen.getByRole("button", { name: "Set password and continue" }));
    await waitFor(() => expect(screen.getByText("settings page")).toBeInTheDocument());
    const post = calls.find((c) => c.path === "/api/setup" && c.method === "POST");
    expect(post?.body).toEqual({ password: "teachers-2026" });
  });

  it("refuses a mismatch and a short password without calling the API", async () => {
    mockFetch(); renderAt();
    await screen.findByRole("form", { name: "Set up Smart Marking" });
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Password"), "teachers-2026");
    await user.type(screen.getByLabelText("Type it again"), "teachers-2025");
    await user.click(screen.getByRole("button", { name: "Set password and continue" }));
    expect(await screen.findByText("The two passwords don't match.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Password")); await user.type(screen.getByLabelText("Password"), "short");
    await user.clear(screen.getByLabelText("Type it again")); await user.type(screen.getByLabelText("Type it again"), "short");
    await user.click(screen.getByRole("button", { name: "Set password and continue" }));
    expect(await screen.findByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/setup" && c.method === "POST")).toBe(false);
  });

  it("sends an already set-up site to sign-in", async () => {
    needsSetup = false; mockFetch(); renderAt();
    expect(await screen.findByText("sign-in page")).toBeInTheDocument();
  });

  it("goes to sign-in when someone else finished setup first", async () => {
    setupStatus = 409; mockFetch(); renderAt();
    await screen.findByRole("form", { name: "Set up Smart Marking" });
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Password"), "teachers-2026");
    await user.type(screen.getByLabelText("Type it again"), "teachers-2026");
    await user.click(screen.getByRole("button", { name: "Set password and continue" }));
    expect(await screen.findByText("sign-in page")).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

function mockFetch(handlers: Record<string, () => Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      const handler = handlers[path];
      if (!handler) return Promise.reject(new Error(`Unexpected fetch to ${path}`));
      return Promise.resolve(handler());
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App auth gate", () => {
  it("shows the sign-in page when /api/auth/me returns 401", async () => {
    mockFetch({
      "/api/auth/me": () =>
        new Response(JSON.stringify({ error: { code: "unauthenticated", message: "Sign in to continue" } }), { status: 401 }),
    });
    render(
      <MemoryRouter initialEntries={["/submissions"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("fails closed with a retry notice when /api/auth/me returns a server error", async () => {
    mockFetch({
      "/api/auth/me": () =>
        new Response(JSON.stringify({ error: { code: "server_error", message: "boom" } }), { status: 500 }),
    });
    render(
      <MemoryRouter initialEntries={["/submissions"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/Can't reach Smart Marking right now\./)).toBeInTheDocument();
    expect(screen.queryByText("Submissions")).not.toBeInTheDocument();
  });

  it("shows the nav when authenticated", async () => {
    mockFetch({
      "/api/auth/me": () => new Response(JSON.stringify({ authenticated: true }), { status: 200 }),
      "/api/queue": () => new Response(JSON.stringify([]), { status: 200 }),
    });
    render(
      <MemoryRouter initialEntries={["/submissions"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("link", { name: "Submissions" })).toBeInTheDocument();
  });
});

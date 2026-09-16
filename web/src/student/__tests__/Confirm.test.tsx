import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Confirm } from "../Confirm";

function mockFetch(handlers: Record<string, (init?: RequestInit) => Response>) {
  const calls: { path: string; method: string; body?: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const handler = handlers[`${method} ${path}`];
      if (!handler) return Promise.reject(new Error(`Unexpected fetch to ${method} ${path}`));
      return Promise.resolve(handler(init));
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

const state = { code: "CE4R", reg_no: 1, student_name: "Tan Wei Ling", class_name: "4E2" };

function renderConfirm(withState = true) {
  return render(
    <MemoryRouter initialEntries={[withState ? { pathname: "/s/confirm", state } : "/s/confirm"]}>
      <Routes>
        <Route path="/s/confirm" element={<Confirm />} />
        <Route path="/s" element={<p>home page</p>} />
        <Route path="/c/:code" element={<p>enter page</p>} />
        <Route path="/join" element={<p>join page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Confirm", () => {
  it("asks the student to confirm and starts a session on yes", async () => {
    const calls = mockFetch({ "POST /api/student/session": () => new Response(null, { status: 204 }) });
    renderConfirm();
    expect(screen.getByText("Are you Tan Wei Ling, #1 of 4E2?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yes, that's me" }));
    expect(await screen.findByText("home page")).toBeInTheDocument();
    expect(calls[0]).toEqual({ path: "/api/student/session", method: "POST", body: { code: "CE4R", reg_no: 1 } });
  });

  it("goes back to the class link on not me", async () => {
    mockFetch({});
    renderConfirm();
    await userEvent.click(screen.getByRole("button", { name: "Not me" }));
    expect(await screen.findByText("enter page")).toBeInTheDocument();
  });

  it("redirects to /join when there is no state", () => {
    mockFetch({});
    renderConfirm(false);
    expect(screen.getByText("join page")).toBeInTheDocument();
  });

  it("shows an error when the session cannot be started", async () => {
    mockFetch({ "POST /api/student/session": () => new Response(JSON.stringify({ error: { code: "too_many_attempts", message: "Too many tries — wait a minute and try again" } }), { status: 429 }) });
    renderConfirm();
    await userEvent.click(screen.getByRole("button", { name: "Yes, that's me" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many tries");
  });
});

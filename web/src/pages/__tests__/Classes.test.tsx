import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ClassRow } from "../../api/types";
import { Classes } from "../Classes";

function mockFetch(handlers: Record<string, (init?: RequestInit) => Response>) {
  const calls: { path: string; method: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      calls.push({ path, method });
      const handler = handlers[`${method} ${path}`];
      if (!handler) return Promise.reject(new Error(`Unexpected fetch to ${method} ${path}`));
      return Promise.resolve(handler(init));
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("Classes", () => {
  it("lists classes as cards and creates a new one", async () => {
    let list: ClassRow[] = [{ id: 1, name: "4E2 Mathematics", code: "CE4R", student_count: 40, open_assignments: 2, archived_at: null, created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z" },
      { id: 2, name: "Old 3N1", code: "QWER", student_count: 0, open_assignments: 0, archived_at: "2026-09-01T00:00:00Z", created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z" }];
    const calls = mockFetch({
      "GET /api/classes": () => new Response(JSON.stringify(list), { status: 200 }),
      "POST /api/classes": () => { list = [...list, { ...list[0], id: 3, name: "4E1 Science", code: "TZ7K", student_count: 0, open_assignments: 0 }]; return new Response(JSON.stringify(list[2]), { status: 201 }); },
    });
    render(<MemoryRouter><Classes /></MemoryRouter>);
    const card = (await screen.findByText("4E2 Mathematics")).closest("a")!;
    expect(card).toHaveAttribute("href", "/classes/1");
    expect(card).toHaveTextContent("CE4R");
    expect(card).toHaveTextContent("40 students");
    expect(card).toHaveTextContent("2 open");
    expect(screen.getByText("Archived (1)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New class" }));
    await userEvent.type(screen.getByLabelText("Class name"), "4E1 Science");
    await userEvent.click(screen.getByRole("button", { name: "Create class" }));
    expect(await screen.findByText("4E1 Science")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/classes")).toBe(true);
  });

  it("shows the empty state", async () => {
    mockFetch({ "GET /api/classes": () => new Response("[]", { status: 200 }) });
    render(<MemoryRouter><Classes /></MemoryRouter>);
    expect(await screen.findByText(/No classes yet/)).toBeInTheDocument();
  });
});

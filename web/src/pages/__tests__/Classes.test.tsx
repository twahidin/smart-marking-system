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
    let list: ClassRow[] = [{ id: 1, name: "4E2 Mathematics", code: "CE4R", student_count: 40, open_assignments: 2, subject: "math", marking: 0, needs_you: 0, archived_at: null, created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z" },
      { id: 2, name: "Old 3N1", code: "QWER", student_count: 0, open_assignments: 0, subject: null, marking: 0, needs_you: 0, archived_at: "2026-09-01T00:00:00Z", created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z" }];
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
    await userEvent.click(screen.getByRole("button", { name: "Build a classroom" }));
    await userEvent.type(screen.getByLabelText("Class name"), "4E1 Science");
    await userEvent.click(screen.getByRole("button", { name: "Create class" }));
    expect(await screen.findByText("4E1 Science")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/classes")).toBe(true);
  });

  it("draws a tile per live class, a plot for a new class, and sends the subject", async () => {
    const list: ClassRow[] = [{ id: 1, name: "4E2 Mathematics", code: "CE4R", student_count: 40, open_assignments: 2, subject: "math", marking: 0, needs_you: 0, archived_at: null, created_at: "", updated_at: "" }];
    const calls = mockFetch({
      "GET /api/classes": () => new Response(JSON.stringify(list), { status: 200 }),
      "POST /api/classes": (init) => { const body = JSON.parse(String(init?.body)); list.push({ ...list[0], id: 2, name: body.name, subject: body.subject }); return new Response(JSON.stringify(list[1]), { status: 201 }); },
    });
    render(<MemoryRouter><Classes /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: /4E2 Mathematics/ })).toHaveAttribute("href", "/classes/1");
    expect(screen.getByText("Your school")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Build a classroom" }));
    await userEvent.type(screen.getByLabelText("Class name"), "2E3 Science");
    await userEvent.selectOptions(screen.getByLabelText("Subject"), "science");
    await userEvent.click(screen.getByRole("button", { name: "Create class" }));
    expect(calls.find((c) => c.method === "POST")?.path).toBe("/api/classes");
    expect(await screen.findByRole("link", { name: /2E3 Science/ })).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    mockFetch({ "GET /api/classes": () => new Response("[]", { status: 200 }) });
    render(<MemoryRouter><Classes /></MemoryRouter>);
    expect(await screen.findByText(/Your school is empty/)).toBeInTheDocument();
  });
});

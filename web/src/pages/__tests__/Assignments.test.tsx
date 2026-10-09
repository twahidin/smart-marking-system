import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AssignmentTemplate } from "../../api/types";
import { Assignments } from "../Assignments";

const templates: AssignmentTemplate[] = [
  { id: 1, title: "Worksheet 3", subject: "math", context: "Sec 4", rubric: { criterion_defs: [{ id: "c1", description: "method", max_score: 2 }] },
    language: null, criteria_count: 1, total_marks: 2, times_used: 4, created_at: "2026-09-15T03:04:05Z", updated_at: "2026-09-15T03:04:05Z",
    scheme_kind: "mark_scheme", questions: [{ q_id: "q1", text: "Solve 2x + 3 = 7", max_marks: 2 }], scheme: [], paper_page_ids: [11, 12], scheme_page_ids: [], delete_pages_after_marking: null, effective_delete_pages: true,
    provider: null, model: null, extractor_model: null, effective_model: { provider: "openrouter", model: "openrouter/auto", extractor_model: null, source: "settings" } },
  { id: 2, title: "Essay draft", subject: "language", context: "", rubric: { criterion_defs: [{ id: "c1", description: "structure", max_score: 5 }, { id: "c2", description: "grammar", max_score: 3 }] },
    language: null, criteria_count: 2, total_marks: 8, times_used: 0, created_at: "2026-09-14T03:04:05Z", updated_at: "2026-09-14T03:04:05Z",
    scheme_kind: "criteria", questions: [], scheme: [], paper_page_ids: [], scheme_page_ids: [], delete_pages_after_marking: null, effective_delete_pages: true,
    provider: null, model: null, extractor_model: null, effective_model: { provider: "openrouter", model: "openrouter/auto", extractor_model: null, source: "settings" } },
];

// The page also fetches two pieces of scene decoration on mount; every test gets them unless it overrides them.
const decoration: Record<string, (init?: RequestInit) => Response> = {
  "GET /api/class-assignments/due?days=7": () => new Response(JSON.stringify([{ id: 9, class_id: 1, class_name: "3N1", title: "Comprehension — Unit 4", due_at: "2026-10-12T08:00:00Z", status: "open" }]), { status: 200 }),
  "GET /api/room": () => new Response(JSON.stringify({ counts: { queued: 0, read: 1, mark: 0, check: 0, feedback: 0, done: 2, needs_you: 0, failed: 0 }, started_at: null, desks: [], last_event_id: 1 }), { status: 200 }),
};

function mockFetch(handlers: Record<string, (init?: RequestInit) => Response>) {
  handlers = { ...decoration, ...handlers };
  const calls: { path: string; method: string; body: any }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      let body: any = null;
      if (typeof init?.body === "string") { try { body = JSON.parse(init.body); } catch { body = init.body; } }
      calls.push({ path, method, body });
      const handler = handlers[`${method} ${path}`];
      if (!handler) return Promise.reject(new Error(`Unexpected fetch to ${method} ${path}`));
      return Promise.resolve(handler(init));
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

// The desk's folder-rack labels repeat template titles, so the table's own cells are queried through the table.
const inTable = () => within(screen.getByRole("table"));
const findInTable = async (text: string) => within(await screen.findByRole("table")).findByText(text);

describe("Assignments", () => {
  it("lists saved assignments with criteria, marks and usage", async () => {
    mockFetch({ "GET /api/assignments": () => new Response(JSON.stringify(templates), { status: 200 }) });
    render(<MemoryRouter><Assignments /></MemoryRouter>);
    expect(await findInTable("Worksheet 3")).toBeInTheDocument();
    const row = inTable().getByText("Essay draft").closest("tr")!;
    expect(row).toHaveTextContent("English");
    expect(row).toHaveTextContent("2");
    expect(row).toHaveTextContent("8");
    expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(2);
    const ws = inTable().getByText("Worksheet 3").closest("tr")!;
    expect(ws).toHaveTextContent("Mark scheme");
    expect(ws).toHaveTextContent("Paper: 2 pages");
    expect(row).toHaveTextContent("Criteria");
    expect(row).not.toHaveTextContent("Paper:");
  });

  it("captions an assignment that pins its own model", async () => {
    const pinned = [{ ...templates[0], provider: "openai", model: "gpt-5.5", extractor_model: null }, templates[1]];
    mockFetch({ "GET /api/assignments": () => new Response(JSON.stringify(pinned), { status: 200 }) });
    render(<MemoryRouter><Assignments /></MemoryRouter>);
    const ws = (await findInTable("Worksheet 3")).closest("tr")!;
    expect(ws).toHaveTextContent("OpenAI · gpt-5.5");
    // An assignment on Auto says nothing — it follows Settings.
    expect(inTable().getByText("Essay draft").closest("tr")!).not.toHaveTextContent("·");
  });

  it("renaming carries the assignment's model through unchanged", async () => {
    const pinned = [{ ...templates[0], provider: "openai", model: "gpt-5.5", extractor_model: "gpt-5-mini" }];
    const calls = mockFetch({
      "GET /api/assignments": () => new Response(JSON.stringify(pinned), { status: 200 }),
      "PUT /api/assignments/1": () => new Response(JSON.stringify(pinned[0]), { status: 200 }),
    });
    render(<MemoryRouter><Assignments /></MemoryRouter>);
    await findInTable("Worksheet 3");
    await userEvent.click(screen.getAllByRole("button", { name: "Rename" })[0]);
    await userEvent.type(await screen.findByLabelText("Title"), " v2");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.body.title).toBe("Worksheet 3 v2");
    expect(put.body.provider).toBe("openai");
    expect(put.body.model).toBe("gpt-5.5");
    expect(put.body.extractor_model).toBe("gpt-5-mini");
  });

  it("shows the empty state when nothing is saved", async () => {
    mockFetch({ "GET /api/assignments": () => new Response(JSON.stringify([]), { status: 200 }) });
    render(<MemoryRouter><Assignments /></MemoryRouter>);
    expect(await screen.findByText(/No saved assignments yet/)).toBeInTheDocument();
  });

  it("confirming delete removes the row", async () => {
    let list = templates;
    const calls = mockFetch({
      "GET /api/assignments": () => new Response(JSON.stringify(list), { status: 200 }),
      "DELETE /api/assignments/1": () => { list = templates.filter((t) => t.id !== 1); return new Response(null, { status: 204 }); },
    });
    render(<MemoryRouter><Assignments /></MemoryRouter>);
    await findInTable("Worksheet 3");
    await userEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Worksheet 3");
    // Nothing is deleted until the teacher confirms.
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Delete assignment" }));
    await waitFor(() => expect(inTable().queryByText("Worksheet 3")).not.toBeInTheDocument());
    expect(inTable().getByText("Essay draft")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/assignments/1")).toBe(true);
  });
});

describe("Assignments — the desk", () => {
  it("shows the desk, filters the table from the folder rack, and lists what is due on the pinboard", async () => {
    mockFetch({ "GET /api/assignments": () => new Response(JSON.stringify(templates), { status: 200 }) });
    render(<MemoryRouter><Assignments /></MemoryRouter>);
    expect(await screen.findByText("Your desk")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "The teacher's desk" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /Pinboard · due this week/ })).toHaveAttribute("href", "/classes/1/assignments/9");
    expect(await screen.findByRole("link", { name: /Marking now · 1 script/ })).toHaveAttribute("href", "/room");
    await userEvent.click(screen.getByRole("button", { name: /^Maths · 1 folder/ }));
    expect(screen.getByRole("button", { name: "Showing Maths · Show all" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(2); // header + the maths row
    await userEvent.click(screen.getByRole("button", { name: "Showing Maths · Show all" }));
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });
});

describe("Assignments — delete guard", () => {
  it("warns when scripts reference the assignment and deletes with force", async () => {
    const inUse = [{ ...templates[0], submission_count: 3, pending_count: 1 }];
    const calls = mockFetch({
      "GET /api/assignments": () => new Response(JSON.stringify(inUse), { status: 200 }),
      "DELETE /api/assignments/1?force=true": () => new Response(null, { status: 204 }),
    });
    render(<MemoryRouter><Assignments /></MemoryRouter>);
    await findInTable("Worksheet 3");
    await userEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("3 scripts");
    expect(dialog).toHaveTextContent("1 has not been marked yet");
    expect(screen.queryByRole("button", { name: "Delete assignment" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete anyway" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/assignments/1?force=true")).toBe(true));
  });
});

describe("Assignments — delete guard (classes)", () => {
  it("warns when the assignment is set in classes and deletes with force", async () => {
    const inUse = [{ ...templates[0], submission_count: 0, class_assignment_count: 2 }];
    const calls = mockFetch({
      "GET /api/assignments": () => new Response(JSON.stringify(inUse), { status: 200 }),
      "DELETE /api/assignments/1?force=true": () => new Response(null, { status: 204 }),
    });
    render(<MemoryRouter><Assignments /></MemoryRouter>);
    await findInTable("Worksheet 3");
    await userEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("set in 2 classes");
    expect(dialog).not.toHaveTextContent("referenced by");
    expect(screen.queryByRole("button", { name: "Delete assignment" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete anyway" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/assignments/1?force=true")).toBe(true));
  });
});

describe("Assignments — editor links", () => {
  const app = () => (
    <MemoryRouter initialEntries={["/assignments"]}>
      <Routes>
        <Route path="/assignments" element={<Assignments />} />
        <Route path="/assignments/:id" element={<div data-testid="editor">editor</div>} />
      </Routes>
    </MemoryRouter>
  );

  it("+ New assignment opens the editor", async () => {
    mockFetch({ "GET /api/assignments": () => new Response(JSON.stringify(templates), { status: 200 }) });
    render(app());
    await findInTable("Worksheet 3");
    await userEvent.click(screen.getByRole("button", { name: "+ New assignment" }));
    expect(await screen.findByTestId("editor")).toBeInTheDocument();
  });

  it("clicking a row opens that assignment; the row's own buttons do not", async () => {
    mockFetch({ "GET /api/assignments": () => new Response(JSON.stringify(templates), { status: 200 }) });
    render(app());
    await findInTable("Worksheet 3");
    await userEvent.click(screen.getAllByRole("button", { name: "Rename" })[0]);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByTestId("editor")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(inTable().getByText("Worksheet 3"));
    expect(await screen.findByTestId("editor")).toBeInTheDocument();
  });

  it("flags a typed assignment that has no scheme rows yet", async () => {
    mockFetch({ "GET /api/assignments": () => new Response(JSON.stringify(templates), { status: 200 }) });
    render(<MemoryRouter><Assignments /></MemoryRouter>);
    const ws = (await findInTable("Worksheet 3")).closest("tr")!;
    expect(ws).toHaveTextContent("Draft — no scheme yet");
    expect(inTable().getByText("Essay draft").closest("tr")!).not.toHaveTextContent("Draft");
  });
});

describe("Assignments — duplicate", () => {
  it("asks the server to duplicate (so the paper is copied too) and reloads", async () => {
    let list = templates;
    const calls = mockFetch({
      "GET /api/assignments": () => new Response(JSON.stringify(list), { status: 200 }),
      "POST /api/assignments/1/duplicate": () => { list = [...templates, { ...templates[0], id: 3, title: "Worksheet 3 (copy)" }]; return new Response(JSON.stringify(list[2]), { status: 201 }); },
    });
    render(<MemoryRouter><Assignments /></MemoryRouter>);
    await findInTable("Worksheet 3");
    await userEvent.click(screen.getAllByRole("button", { name: "Duplicate" })[0]);
    expect(await findInTable("Worksheet 3 (copy)")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/assignments/1/duplicate")).toBe(true);
  });
});

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ClassAssignment, ClassRow, Student } from "../../api/types";
import { ClassPage } from "../ClassPage";

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

const cls: ClassRow = { id: 1, name: "4E2 Mathematics", code: "CE4R", student_count: 0, open_assignments: 0, archived_at: null, created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z" };
const app = (tab = "") => (
  <MemoryRouter initialEntries={[`/classes/1${tab}`]}><Routes><Route path="/classes/:id" element={<ClassPage />} /></Routes></MemoryRouter>
);

describe("ClassPage", () => {
  it("copies the class link and explains the CSV in the empty state", async () => {
    mockFetch({ "GET /api/classes/1": () => new Response(JSON.stringify(cls), { status: 200 }), "GET /api/classes/1/students": () => new Response("[]", { status: 200 }) });
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(app());
    expect(await screen.findByText("4E2 Mathematics")).toBeInTheDocument();
    expect(screen.getByText(/two columns: name, reg_no/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Copy link" }));
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/\/c\/CE4R$/));
    expect(await screen.findByText(/Paste this into Google Classroom/)).toBeInTheDocument();
  });

  it("previews a CSV with issues, then confirms a clean one", async () => {
    const preview = { rows: [{ reg_no: 1, raw_reg_no: "1", name: "Tan", issues: [] }, { reg_no: 1, raw_reg_no: "1", name: "Lim", issues: ["duplicate_reg_no"] }], errors: [] };
    let students: Student[] = [];
    const calls = mockFetch({
      "GET /api/classes/1": () => new Response(JSON.stringify(cls), { status: 200 }),
      "GET /api/classes/1/students": () => new Response(JSON.stringify(students), { status: 200 }),
      "POST /api/classes/1/students/preview": () => new Response(JSON.stringify(preview), { status: 200 }),
      "PUT /api/classes/1/students": () => { students = [{ id: 1, reg_no: 1, name: "Tan", submissions: 0, last_seen_at: null }]; return new Response(JSON.stringify({ students, kept: [] }), { status: 200 }); },
    });
    render(app());
    await screen.findByText("4E2 Mathematics");
    const input = screen.getByLabelText("Choose classlist file") as HTMLInputElement;
    await userEvent.upload(input, new File(["name,reg_no\nTan,1\nLim,1\n"], "list.csv", { type: "text/csv" }));
    expect(await screen.findByText("Duplicate register number")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm classlist" })).toBeDisabled();
    preview.rows[1] = { reg_no: 2, raw_reg_no: "2", name: "Lim", issues: [] };
    await userEvent.upload(input, new File(["name,reg_no\nTan,1\nLim,2\n"], "list.csv", { type: "text/csv" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm classlist" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Confirm classlist" }));
    expect(await screen.findByRole("cell", { name: "Tan" })).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PUT" && c.path === "/api/classes/1/students")).toBe(true);
  });

  it("sets an assignment from the bank and opens it", async () => {
    const templates = [{ id: 7, title: "Worksheet 3", subject: "math", context: "", rubric: { criterion_defs: [] }, criteria_count: 0, total_marks: 6, times_used: 0, created_at: "", updated_at: "", scheme_kind: "mark_scheme", questions: [], scheme: [], paper_page_ids: [], scheme_page_ids: [], delete_pages_after_marking: null, effective_delete_pages: true }];
    let cas: ClassAssignment[] = [];
    const calls = mockFetch({
      "GET /api/classes/1": () => new Response(JSON.stringify(cls), { status: 200 }),
      "GET /api/classes/1/assignments": () => new Response(JSON.stringify(cas), { status: 200 }),
      "GET /api/assignments": () => new Response(JSON.stringify(templates), { status: 200 }),
      "POST /api/classes/1/assignments": () => { cas = [{ id: 3, class_id: 1, template_id: 7, title: "Worksheet 3", due_at: null, status: "draft", derived_status: "draft", allow_student_uploads: true, released_at: null, template_deleted: false, subject: "math", scheme_kind: "mark_scheme", submission_count: 0, created_at: "", updated_at: "" }]; return new Response(JSON.stringify(cas[0]), { status: 201 }); },
      "PUT /api/classes/1/assignments/3": () => { cas[0] = { ...cas[0], status: "open", derived_status: "open" }; return new Response(JSON.stringify(cas[0]), { status: 200 }); },
    });
    render(app("?tab=assignments"));
    await userEvent.click(await screen.findByRole("button", { name: "Set assignment" }));
    await userEvent.selectOptions(await screen.findByLabelText("Assignment from the bank"), "7");
    await userEvent.click(screen.getByRole("button", { name: "Set for this class" }));
    const row = (await screen.findByText("Worksheet 3")).closest("tr")!;
    expect(row).toHaveTextContent("Draft");
    await userEvent.click(within(row).getByRole("button", { name: "Open" }));
    await waitFor(() => expect(row).toHaveTextContent("Open"));
    expect(calls.some((c) => c.method === "PUT" && c.path === "/api/classes/1/assignments/3")).toBe(true);
    expect(within(row).getByRole("link", { name: "Worksheet 3" })).toHaveAttribute("href", "/classes/1/assignments/3");
  });

  it("keeps the link to a class assignment whose template was deleted, with the warning beside it", async () => {
    const gone: ClassAssignment = { id: 4, class_id: 1, template_id: 9, title: "Old worksheet", due_at: null, status: "open", derived_status: "marking", allow_student_uploads: true, released_at: null, template_deleted: true, subject: "math", scheme_kind: "mark_scheme", submission_count: 2, created_at: "", updated_at: "" };
    mockFetch({
      "GET /api/classes/1": () => new Response(JSON.stringify(cls), { status: 200 }),
      "GET /api/classes/1/assignments": () => new Response(JSON.stringify([gone]), { status: 200 }),
    });
    render(app("?tab=assignments"));
    const row = (await screen.findByText("Old worksheet")).closest("tr")!;
    expect(within(row).getByRole("link", { name: "Old worksheet" })).toHaveAttribute("href", "/classes/1/assignments/4");
    expect(within(row).getByText("Assignment deleted from the bank — set it again")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Open" })).not.toBeInTheDocument();
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ClassAssignmentDetail, ClassRow } from "../../api/types";
import { ClassAssignmentPage } from "../ClassAssignmentPage";

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

const cls: ClassRow = { id: 1, name: "4E2 Mathematics", code: "CE4R", student_count: 4, open_assignments: 1, archived_at: null, created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z" };
const clsHandler = { "GET /api/classes/1": () => new Response(JSON.stringify(cls), { status: 200 }) };

const detail: ClassAssignmentDetail = { id: 3, class_id: 1, template_id: 7, title: "Quadratic equations — Worksheet 3", due_at: "2026-09-10T00:00:00Z", status: "open", derived_status: "marking", allow_student_uploads: true, released_at: null, template_deleted: false, subject: "math", scheme_kind: "mark_scheme", submission_count: 3, created_at: "", updated_at: "",
  roster: { counts: { not_handed_in: 1, handed_in: 0, marking: 1, needs_you: 1, ready: 1 }, rows: [
    { student_id: 1, reg_no: 1, name: "Tan Wei Ling", submission_id: 11, pages: 4, handed_in_at: "2026-09-09T13:02:00Z", late: false, source: "student", status: "needs_you", total: 15, total_upper: 17, total_max: 25, needs_you_parts: ["3"] },
    { student_id: 2, reg_no: 2, name: "Muhammad Danish", submission_id: 12, pages: 3, handed_in_at: "2026-09-11T01:00:00Z", late: true, source: "teacher", status: "ready", total: 21, total_upper: 21, total_max: 25, needs_you_parts: [] },
    { student_id: 3, reg_no: 3, name: "Priya Nair", submission_id: null, pages: 0, handed_in_at: null, late: false, source: null, status: "not_handed_in", total: null, total_upper: null, total_max: null, needs_you_parts: [] },
    { student_id: 4, reg_no: 4, name: "Lim Jun Hao", submission_id: 14, pages: 2, handed_in_at: "2026-09-09T13:02:00Z", late: false, source: "student", status: "marking", total: null, total_upper: null, total_max: null, needs_you_parts: [] },
  ] } };

const app = () => (
  <MemoryRouter initialEntries={["/classes/1/assignments/3"]}>
    <Routes><Route path="/classes/:id/assignments/:caid" element={<ClassAssignmentPage />} /></Routes>
  </MemoryRouter>
);

describe("ClassAssignmentPage", () => {
  it("renders the strip, filters the roster, and disables release while parts need you", async () => {
    mockFetch({ ...clsHandler, "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(detail), { status: 200 }) });
    render(app());
    expect(await screen.findByRole("heading", { name: "Quadratic equations — Worksheet 3" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Needs you/ })).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: "Release feedback" })).toBeDisabled();
    expect(screen.getByText("Needs you · 3")).toBeInTheDocument();
    expect(screen.getByText("15–17 / 25")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tan Wei Ling" })).toHaveAttribute("href", "/submissions/11");
    expect(screen.queryByRole("link", { name: "Priya Nair" })).not.toBeInTheDocument();
    expect(screen.getByText(/late/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Not handed in/ }));
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Upload pages" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all 4" }));
    expect(screen.getAllByRole("row")).toHaveLength(5);
  });

  it("releases feedback after confirming and downloads the CSV", async () => {
    const ready = { ...detail, derived_status: "open" as const, roster: { ...detail.roster, counts: { ...detail.roster.counts, needs_you: 0 }, rows: detail.roster.rows.map((r) => r.status === "needs_you" ? { ...r, status: "ready" as const, needs_you_parts: [] } : r) } };
    const calls = mockFetch({
      ...clsHandler,
      "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(ready), { status: 200 }),
      "POST /api/classes/1/assignments/3/release": () => new Response(JSON.stringify({ ...ready, status: "released", released_at: "2026-09-12T00:00:00Z" }), { status: 200 }),
    });
    render(app());
    await userEvent.click(await screen.findByRole("button", { name: "Release feedback" }));
    // releasing closes student hand-ins; only the teacher's upload adds scripts afterwards
    expect(screen.getByText(/Students can no longer hand in\. Pages you upload for a student later are marked and shown to them automatically\./)).toBeInTheDocument();
    expect(screen.queryByText(/Anyone who hands in later/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Release to students" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/release"))).toBe(true));
    expect(await screen.findByText(/Released/)).toBeInTheDocument();
  });

  it("shows the server's reason when release is refused", async () => {
    const ready = { ...detail, derived_status: "open" as const, roster: { ...detail.roster, counts: { ...detail.roster.counts, needs_you: 0 }, rows: detail.roster.rows.map((r) => r.status === "needs_you" ? { ...r, status: "ready" as const, needs_you_parts: [] } : r) } };
    mockFetch({
      ...clsHandler,
      "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(ready), { status: 200 }),
      "POST /api/classes/1/assignments/3/release": () => new Response(JSON.stringify({ error: { code: "needs_you", message: "1 part still needs you — clear the review queue first" } }), { status: 409 }),
    });
    render(app());
    await userEvent.click(await screen.findByRole("button", { name: "Release feedback" }));
    await userEvent.click(screen.getByRole("button", { name: "Release to students" }));
    expect(await screen.findByText(/still needs you/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Release feedback" })).toBeInTheDocument();
  });

  it("uploads pages for a student who has not handed in", async () => {
    const calls = mockFetch({
      ...clsHandler,
      "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(detail), { status: 200 }),
      "POST /api/classes/1/assignments/3/students/3/upload": () => new Response(JSON.stringify({ id: 99, status: "queued", pages: [] }), { status: 202 }),
    });
    render(app());
    await userEvent.click(await screen.findByRole("button", { name: "Upload pages" }));
    const input = screen.getByLabelText("Choose pages for Priya Nair") as HTMLInputElement;
    await userEvent.upload(input, [new File(["x"], "p1.png", { type: "image/png" })]);
    await userEvent.click(screen.getByRole("button", { name: "Start marking" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/students/3/upload"))).toBe(true));
  });
});

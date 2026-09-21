import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BulkPreview, BulkResult, ClassAssignmentDetail, ClassRow, InsightsPayload } from "../../api/types";
import { ClassAssignmentPage } from "../ClassAssignmentPage";

// Stands in for the canvas resize jsdom cannot run: a 4000 px photo comes back small, and renamed.
vi.mock("../../lib/image", () => ({
  downscale: vi.fn((f: File) => Promise.resolve(new File(["x".repeat(1234)], f.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" }))),
}));

function mockFetch(handlers: Record<string, (init?: RequestInit) => Response>) {
  const calls: { path: string; method: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      calls.push({ path, method, init });
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

const app = (entry = "/classes/1/assignments/3") => (
  <MemoryRouter initialEntries={[entry]}>
    <Routes><Route path="/classes/:id/assignments/:caid" element={<ClassAssignmentPage />} /></Routes>
  </MemoryRouter>
);

const insights: InsightsPayload = {
  stats: { n_students: 4, n_marked: 2, n_pending: 1, totals: { mean: 18, median: 18, max: 25, buckets: [{ from: 0, to: 4, n: 0 }, { from: 5, to: 9, n: 0 }, { from: 10, to: 14, n: 0 }, { from: 15, to: 19, n: 1 }, { from: 20, to: 25, n: 1 }] },
    parts: [{ q_id: "3", label: "3", max: 5, attempted: 2, mean_pct: 40, full: 0, zero: 1, allocations: [{ label: "A1", lost: 2 }], not_in_scheme: 0, illegible: 0, pending: 0 }],
    weakest: ["3"], most_lost: [{ q_id: "3", label: "A1", lost: 2, of: 2 }],
    students: [{ student_id: 1, reg_no: 1, name: "Tan Wei Ling", total: 15, max: 25, weak_parts: ["3"] }] },
  report: null, n_marked: 2, provider: null, model: null, generated_at: null, error: null, job: null,
};

/* ---- bulk upload fixtures ---- */
const zipFile = () => new File(["PK"], "4e2-handins.zip", { type: "application/zip" });
const preview: BulkPreview = {
  matched: [
    { student_id: 3, reg_no: 3, name: "Priya Nair", files: ["03_a.py", "3.jpg"], ignored: ["notes.txt"], already_handed_in: false },
    { student_id: 2, reg_no: 2, name: "Muhammad Danish", files: ["02.pdf"], ignored: [], already_handed_in: true },
    { student_id: 4, reg_no: 4, name: "Lim Jun Hao", files: [], ignored: ["thumbs.db"], already_handed_in: false },
  ],
  ambiguous: ["7 or 17.pdf"],
  unmatched: ["scan copy.pdf"],
};
const result: BulkResult = {
  created: [{ reg_no: 3, ignored: ["notes.txt"] }], skipped: [{ reg_no: 2 }],
  failed: [{ reg_no: 4, error: "no usable files (only: thumbs.db)" }],
  unmatched: ["scan copy.pdf"], ambiguous: ["7 or 17.pdf"],
};
const bulkHandlers = {
  ...clsHandler,
  "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(detail), { status: 200 }),
  "POST /api/classes/1/assignments/3/bulk/preview": () => new Response(JSON.stringify(preview), { status: 200 }),
};
/** Open the dialog and hand it the zip — every bulk test starts here. */
async function pickZip() {
  render(app());
  await userEvent.click(await screen.findByRole("button", { name: "Bulk upload" }));
  await userEvent.upload(screen.getByLabelText("Choose a zip of hand-ins"), zipFile());
  return screen.getByRole("dialog", { name: "Bulk upload" });
}

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

  it("shrinks a teacher's photo before it is uploaded and lists it at its new size", async () => {
    const calls = mockFetch({
      ...clsHandler,
      "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(detail), { status: 200 }),
      "POST /api/classes/1/assignments/3/students/3/upload": () => new Response(JSON.stringify({ id: 99, status: "queued", pages: [] }), { status: 202 }),
    });
    render(app());
    await userEvent.click(await screen.findByRole("button", { name: "Upload pages" }));
    const input = screen.getByLabelText("Choose pages for Priya Nair") as HTMLInputElement;
    // A Maths assignment takes pages only.
    expect(input.accept).not.toMatch(/\.py/);
    await userEvent.upload(input, [new File(["x".repeat(4000)], "big.png", { type: "image/png" })]);
    const listed = await screen.findByText(/big\.jpg/);
    expect(listed).toHaveTextContent("1.2 KB");
    await userEvent.click(screen.getByRole("button", { name: "Start marking" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const form = calls.find((c) => c.method === "POST")!.init!.body as FormData;
    expect(form.getAll("files").map((f) => (f as File).name)).toEqual(["big.jpg"]);
  });

  it("takes program files too when the assignment is Computing", async () => {
    mockFetch({
      ...clsHandler,
      "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify({ ...detail, subject: "computing" }), { status: 200 }),
    });
    render(app());
    await userEvent.click(await screen.findByRole("button", { name: "Upload pages" }));
    const input = screen.getByLabelText("Choose pages for Priya Nair") as HTMLInputElement;
    expect(input.accept).toContain(".py,.sb3,.xlsx,.zip");
    await userEvent.upload(input, [new File(["print(1)"], "prog.py", { type: "text/x-python" })]);
    expect(screen.getByText(/prog\.py/)).toHaveTextContent("8 B");
    expect(screen.getByText(/up to 20 pages and 12 files/)).toBeInTheDocument();
  });

  it("holds the teacher to the same two caps the server enforces", async () => {
    mockFetch({
      ...clsHandler,
      "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify({ ...detail, subject: "computing" }), { status: 200 }),
    });
    render(app());
    await userEvent.click(await screen.findByRole("button", { name: "Upload pages" }));
    const input = screen.getByLabelText("Choose pages for Priya Nair") as HTMLInputElement;
    await userEvent.upload(input, Array.from({ length: 15 }, (_, i) => new File(["x"], `p${i + 1}.py`, { type: "text/x-python" })));
    expect(await screen.findByRole("status")).toHaveTextContent("You can hand in at most 12 files.");
    expect(screen.getAllByRole("listitem")).toHaveLength(12);
    await userEvent.upload(input, Array.from({ length: 12 }, (_, i) => new File(["x"], `q${i + 1}.png`, { type: "image/png" })));
    expect(await screen.findByText(/at most 20 pages or files/)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
  });

  it("shows the insights panel instead of the roster on ?tab=insights", async () => {
    mockFetch({
      ...clsHandler,
      "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(detail), { status: 200 }),
      "GET /api/classes/1/assignments/3/insights": () => new Response(JSON.stringify(insights), { status: 200 }),
    });
    render(app("/classes/1/assignments/3?tab=insights"));
    expect(await screen.findByRole("heading", { name: "Marks by part" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Insights" })).toBeChecked();
    expect(screen.queryByRole("link", { name: "Tan Wei Ling" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Progress" })).not.toBeInTheDocument();
    // ...and the roster comes back from the same segmented control
    await userEvent.click(screen.getByRole("radio", { name: "Roster" }));
    expect(await screen.findByRole("link", { name: "Tan Wei Ling" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Marks by part" })).not.toBeInTheDocument();
  });

  it("opens the insights tab from the roster and puts it in the URL", async () => {
    mockFetch({
      ...clsHandler,
      "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(detail), { status: 200 }),
      "GET /api/classes/1/assignments/3/insights": () => new Response(JSON.stringify(insights), { status: 200 }),
    });
    render(app());
    expect(await screen.findByRole("link", { name: "Tan Wei Ling" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Insights" }));
    expect(await screen.findByRole("heading", { name: "Marks by part" })).toBeInTheDocument();
  });

  it("previews a zip of hand-ins and says what matched, what was skipped and what didn't match", async () => {
    const calls = mockFetch(bulkHandlers);
    const dlg = await pickZip();
    expect(await screen.findByText("#3 Priya Nair — 03_a.py, 3.jpg (skipped: notes.txt)")).toBeInTheDocument();
    expect(screen.getByText("#2 Muhammad Danish — 02.pdf · already handed in — will be skipped")).toBeInTheDocument();
    // A student the zip had nothing usable for is held out of the matched list — the commit would fail for them.
    expect(within(dlg).getByRole("heading", { name: "No usable files" })).toBeInTheDocument();
    expect(screen.getByText("#4 Lim Jun Hao (only: thumbs.db)")).toBeInTheDocument();
    expect(within(dlg).getByRole("heading", { name: "Not matched" })).toBeInTheDocument();
    expect(screen.getByText("scan copy.pdf")).toBeInTheDocument();
    expect(within(dlg).getByRole("heading", { name: "More than one student" })).toBeInTheDocument();
    expect(screen.getByText("7 or 17.pdf")).toBeInTheDocument();
    const form = calls.find((c) => c.path.endsWith("/bulk/preview"))!.init!.body as FormData;
    expect((form.get("zip") as File).name).toBe("4e2-handins.zip");
  });

  it("uploads the zip, reports what came of it and refreshes the roster", async () => {
    const calls = mockFetch({ ...bulkHandlers, "POST /api/classes/1/assignments/3/bulk?replace=0": () => new Response(JSON.stringify(result), { status: 200 }) });
    await pickZip();
    await userEvent.click(await screen.findByRole("button", { name: "Upload" }));
    expect(await screen.findByText("Created 1 · Skipped 1 · Failed 1 · Not matched 1")).toBeInTheDocument();
    expect(screen.getByText("#4 — no usable files (only: thumbs.db)")).toBeInTheDocument();
    const form = calls.find((c) => c.path.includes("/bulk?"))!.init!.body as FormData;
    expect((form.get("zip") as File).name).toBe("4e2-handins.zip");
    await waitFor(() => expect(calls.filter((c) => c.method === "GET" && c.path === "/api/classes/1/assignments/3")).toHaveLength(2));
  });

  it("replaces existing hand-ins when asked, and leaves Failed out when nothing failed", async () => {
    const calls = mockFetch({
      ...bulkHandlers,
      "POST /api/classes/1/assignments/3/bulk?replace=1": () =>
        new Response(JSON.stringify({ ...result, created: [{ reg_no: 3, ignored: [] }, { reg_no: 2, ignored: [] }], skipped: [], failed: [] }), { status: 200 }),
    });
    await pickZip();
    await userEvent.click(await screen.findByRole("checkbox", { name: "Replace existing hand-ins" }));
    expect(screen.getByText("#2 Muhammad Danish — 02.pdf · already handed in — will be replaced")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByText("Created 2 · Skipped 0 · Not matched 1")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/bulk?replace=1"))).toBe(true);
  });

  it("shows the server's message when the zip can't be read", async () => {
    mockFetch({
      ...clsHandler,
      "GET /api/classes/1/assignments/3": () => new Response(JSON.stringify(detail), { status: 200 }),
      "POST /api/classes/1/assignments/3/bulk/preview": () => new Response(JSON.stringify({ error: { code: "bad_zip", message: "That file isn't a zip we can open." } }), { status: 400 }),
    });
    await pickZip();
    expect(await screen.findByText("That file isn't a zip we can open.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
  });
});

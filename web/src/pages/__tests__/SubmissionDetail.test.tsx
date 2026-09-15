import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SubmissionDetail as D } from "../../api/types";
import { SubmissionDetail } from "../SubmissionDetail";

const failed: D = {
  id: 7, label: "Tan Wei Ling", subject: "math", context: "", status: "failed", created_at: "2026-09-15T03:04:05Z",
  rubric: { criterion_defs: [{ id: "c1", description: "method", max_score: 2 }] },
  pages: [{ id: 1, page_index: 0, width: 100, height: 100 }], marks: [], totals: null, feedback: null,
  job: { status: "failed", attempts: 5, error: "Provider returned HTTP 401", started_at: null, finished_at: null },
  assignment_id: null, assignment_title: null,
};

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

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/submissions/7"]}>
      <Routes>
        <Route path="/submissions/:id" element={<SubmissionDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SubmissionDetail retry", () => {
  it("shows the API error inside the failed notice when retry is rejected", async () => {
    mockFetch({
      "/api/submissions/7": () => new Response(JSON.stringify(failed), { status: 200 }),
      "/api/submissions/7/retry": () => new Response(JSON.stringify({ error: { code: "not_failed", message: "Only failed submissions can be retried" } }), { status: 409 }),
    });
    renderDetail();
    await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Only failed submissions can be retried", { exact: false })).toBeInTheDocument();
    // The error sits inside the failed-state notice; the original failure is still shown and the page did not flip to "queued".
    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent("Marking failed. Provider returned HTTP 401");
    expect(notice).toHaveTextContent("Retry failed. Only failed submissions can be retried");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("falls back to a generic message when retry throws a network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/api/submissions/7") return Promise.resolve(new Response(JSON.stringify(failed), { status: 200 }));
        return Promise.reject(new TypeError("Failed to fetch"));
      }),
    );
    renderDetail();
    await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/Could not retry/)).toBeInTheDocument();
  });
});

const v2: D = {
  id: 9, label: "Lim Jun Hao", subject: "math", context: "", status: "needs_you", created_at: "2026-09-15T03:04:05Z",
  rubric: { criterion_defs: [{ id: "1a", description: "Solve", max_score: 3 }, { id: "1b", description: "Hence", max_score: 2 }, { id: "2", description: "Sketch", max_score: 4 }] },
  pages: [{ id: 1, page_index: 0, width: 100, height: 100, deleted: false }, { id: 2, page_index: 1, width: 100, height: 100, deleted: false }],
  marks: [], marks_version: 2, scheme_kind: "mark_scheme", pages_deleted: false, run_id: "run-9", marked_at: "2026-09-15T03:10:00Z",
  totals: { total: 5, total_upper: 7, total_max: 9 }, feedback: null,
  job: { status: "done", attempts: 1, error: null, started_at: null, finished_at: null },
  assignment_id: 3, assignment_title: "Quadratics — Worksheet 3",
  parts: [
    { q_id: "1a", label: "1(a)", question_text: "Solve 2x + 3 = 7", scheme: { answer: "x = 2", marks: [{ label: "M1", marks: 1 }, { label: "A1", marks: 2 }], notes: "" },
      extracted: "2x = 4 so x = 2", workings: "", illegible: false, awarded: [{ label: "M1", marks: 1, got: true }, { label: "A1", marks: 2, got: true }], total: 3, max: 3,
      justification: "M1 for isolating x; A1 correct value.", in_scheme: true, confidence: 0.95, escalated: false, reason: null, queue_id: null, teacher: null },
    { q_id: "1b", label: "1(b)", question_text: "Hence find y", scheme: { answer: "y = 5", marks: [{ label: "B1", marks: 2 }], notes: "" },
      extracted: "", workings: "", illegible: true, awarded: [], total: 0, max: 2,
      justification: "", in_scheme: true, confidence: 0.2, escalated: true, reason: "Unclear handwriting", queue_id: 41, teacher: null },
    { q_id: "2", label: "2", question_text: "Sketch the curve", scheme: { answer: "Parabola through (0, 3)", marks: [{ label: "B1", marks: 2 }, { label: "B2", marks: 2 }], notes: "" },
      extracted: "sketch", workings: "", illegible: false, awarded: [{ label: "B1", marks: 2, got: true }, { label: "B2", marks: 2, got: false }], total: 2, max: 4,
      justification: "Different method", in_scheme: false, confidence: 0.6, escalated: false, reason: null, queue_id: null,
      teacher: { allocations: [{ label: "B1", marks: 2, got: true }, { label: "B2", marks: 2, got: false }], total: 2 } },
  ],
};

describe("SubmissionDetail — per-part marks (v2)", () => {
  it("renders the parts table with scheme answers, chips, the needs-you pill and the teacher's mark", async () => {
    mockFetch({ "/api/submissions/7": () => new Response(JSON.stringify(v2), { status: 200 }) });
    renderDetail();
    const table = await screen.findByRole("table", { name: "Marks by question part" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(4);
    expect(rows[1]).toHaveTextContent("1(a)");
    expect(rows[1]).toHaveTextContent("Solve 2x + 3 = 7");
    expect(rows[1]).toHaveTextContent("x = 2");
    expect(rows[1]).toHaveTextContent("[M1 1 · A1 2]");
    expect(rows[1]).toHaveTextContent("2x = 4 so x = 2");
    expect(rows[1]).toHaveTextContent("M1 ✓");
    expect(rows[1]).toHaveTextContent("A1 ✓");
    expect(rows[1]).toHaveTextContent("3 / 3");
    // Escalated part: amber pill with the human reason and a link into the queue; extracted shows (illegible).
    expect(rows[2]).toHaveTextContent("Needs you");
    expect(rows[2]).toHaveTextContent("Unclear handwriting");
    expect(rows[2]).toHaveTextContent("(illegible)");
    expect(within(rows[2]).getByRole("link", { name: /Resolve in the review queue/ })).toHaveAttribute("href", "/review?item=41");
    // Teacher-resolved part shows the teacher's total, not a pill.
    expect(rows[3]).toHaveTextContent("2 / 4 (teacher)");
    expect(rows[3]).not.toHaveTextContent("Needs you");
    // Header: range total, needs-you notice names the part label, download enabled.
    expect(screen.getByRole("alert")).toHaveTextContent("1 part needs you: 1(b)");
    expect(screen.getByRole("button", { name: "Download marking record" })).toBeEnabled();
    expect(screen.getByRole("img", { name: "Page 1" })).toHaveAttribute("src", "/api/pages/1");
  });

  it("downloads the record as a blob with the server's filename", async () => {
    const saved: string[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/submissions/7") return Promise.resolve(new Response(JSON.stringify(v2), { status: 200 }));
      if (path === "/api/submissions/9/record.docx") return Promise.resolve(new Response(new Blob(["docx"]), { status: 200, headers: { "Content-Disposition": "attachment; filename=\"lim-jun-hao-9.docx\"" } }));
      return Promise.reject(new Error(`Unexpected fetch to ${path}`));
    }));
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:record"), revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { saved.push(this.download); });
    renderDetail();
    await userEvent.click(await screen.findByRole("button", { name: "Download marking record" }));
    await vi.waitFor(() => expect(saved).toEqual(["lim-jun-hao-9.docx"]));
    click.mockRestore();
  });

  it("shows the pages-deleted panel instead of the viewer and disables download while marking", async () => {
    const gone: D = { ...v2, status: "done", pages: v2.pages.map((p) => ({ ...p, deleted: true })), pages_deleted: true, totals: { total: 7, total_upper: 7, total_max: 9 } };
    mockFetch({ "/api/submissions/7": () => new Response(JSON.stringify(gone), { status: 200 }) });
    renderDetail();
    const panel = await screen.findByRole("note", { name: "Pages deleted after marking" });
    expect(panel).toHaveTextContent("The marking record has everything that was read.");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("tablist", { name: "Pages" })).not.toBeInTheDocument();
  });

  it("keeps the download button disabled with a hint until marking finishes", async () => {
    const marking: D = { ...v2, status: "marking", parts: [], totals: null, job: { status: "running", attempts: 1, error: null, started_at: null, finished_at: null } };
    mockFetch({ "/api/submissions/7": () => new Response(JSON.stringify(marking), { status: 200 }) });
    renderDetail();
    expect(await screen.findByRole("button", { name: "Download marking record" })).toBeDisabled();
    expect(screen.getByText("Available once marking finishes.")).toBeInTheDocument();
  });
});

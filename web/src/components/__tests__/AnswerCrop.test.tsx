import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Review } from "../../pages/Review";
import { SubmissionDetail } from "../../pages/SubmissionDetail";

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
afterEach(() => vi.unstubAllGlobals());

const part = (q: string, crop_id: number | null, whole = false) => ({
  q_id: q, label: q, question_text: "", scheme: { answer: "x", marks: [{ label: "B1", marks: 1 }], notes: "" },
  extracted: "x = 3", workings: "", illegible: false, awarded: [{ label: "B1", marks: 1, got: true }], total: 1,
  justification: "B1", in_scheme: true, escalated: false, pending: false, teacher: null, crop_id, crop_whole_page: whole,
});

const detail = {
  id: 5, label: "#1 Tan", subject: "math", context: "", status: "done", created_at: "2026-10-01T00:00:00Z", rubric: { criterion_defs: [] },
  pages: [], pages_deleted: true, input_kind: "pages", files: [], marks: [], marks_version: 2, scheme_kind: "mark_scheme",
  parts: [part("1a", 42), part("1b", 43, true), part("2", null)], run_id: "r", totals: { total: 2, total_upper: 2, total_max: 3 },
  job: null, feedback: null, marked_at: "2026-10-01T00:00:00Z", marked_by: "openrouter · x", assignment_id: 1, assignment_title: "W",
};

describe("answer crops", () => {
  it("shows the cropped answer for a part on request, and says when it is a whole page", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input).startsWith("/api/submissions/5") ? json(detail) : json({ error: { code: "x", message: "x" } }, 404)));
    render(<MemoryRouter initialEntries={["/submissions/5"]}><Routes><Route element={<Outlet context={{ refreshQueue: () => {} }} />}><Route path="/submissions/:id" element={<SubmissionDetail />} /></Route></Routes></MemoryRouter>);
    const buttons = await screen.findAllByRole("button", { name: "Show answer" });
    expect(buttons).toHaveLength(2);                      // part 2 has no crop
    await userEvent.setup().click(buttons[1]);
    const img = screen.getByRole("img", { name: /Student's answer for 1b \(whole page\)/ });
    expect(img).toHaveAttribute("src", "/api/crops/43");
    expect(screen.getByText(/Whole page — the reader could not pin down this part/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide answer" })).toBeInTheDocument();
  });

  it("the review queue shows the crop even after the pages are gone", async () => {
    const item = { id: 9, submission_id: 5, submission_label: "#1 Tan", q_id: "1a", reason: "low confidence", reason_text: "Low confidence",
      created_at: "2026-10-01T00:00:00Z", transcription: "x = 3", workings: "", evidence: "", reviewer_note: "", rationale: "",
      criterion_defs: [], proposed_criterion_scores: [], proposed_total: null, page_ids: [], input_kind: "pages" as const, crop_id: 42,
      marks_version: 2, scheme_kind: "mark_scheme", label: "1(a)", question_text: "Solve",
      scheme_row: { q_id: "1a", answer: "x = 3", marks: [{ label: "B1", marks: 1 }], notes: "" },
      proposed: { q_id: "1a", awarded: [{ label: "B1", marks: 1, got: true }], total: 1, justification: "B1" } };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input) === "/api/queue" ? json([item]) : json([], 200)));
    render(<MemoryRouter initialEntries={["/review"]}><Routes><Route element={<Outlet context={{ refreshQueue: () => {} }} />}><Route path="/review" element={<Review />} /></Route></Routes></MemoryRouter>);
    const img = await screen.findByRole("img", { name: "Student's answer for 1a" });
    expect(img).toHaveAttribute("src", "/api/crops/42");
    expect(screen.getByText(/the answer above is the part that was kept/)).toBeInTheDocument();
  });
});

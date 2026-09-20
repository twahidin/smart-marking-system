import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { QueueItem } from "../../api/types";
import { Review } from "../Review";

const base = { submission_id: 9, submission_label: "Lim Jun Hao", created_at: "2026-09-15T03:04:05Z", workings: "", evidence: "", reviewer_note: "", criterion_defs: [], proposed_criterion_scores: [], proposed_total: null, page_ids: [3], input_kind: "pages" as const };
const partItem: QueueItem = {
  ...base, id: 41, q_id: "1b", reason: "marker/reviewer disagree", reason_text: "Marker and reviewer disagreed", transcription: "y = 2x + 1 = 5", rationale: "M1 for substitution",
  marks_version: 2, scheme_kind: "mark_scheme", label: "1(b)", question_text: "Hence find y",
  scheme_row: { q_id: "1b", answer: "y = 5", marks: [{ label: "M1", marks: 1 }, { label: "A1", marks: 2 }], notes: "Accept 5.0" },
  proposed: { q_id: "1b", awarded: [{ label: "M1", marks: 1, got: true }, { label: "A1", marks: 2, got: false }], total: 1, justification: "M1 for substitution" },
};
const bandItem: QueueItem = {
  ...base, id: 42, q_id: "Organisation", reason: "low confidence", reason_text: "Low confidence", transcription: "Once upon a time…", rationale: "",
  marks_version: 2, scheme_kind: "rubric", label: "Organisation", question_text: "Write a narrative.",
  scheme_row: { criterion: "Organisation", bands: [{ band: "A", marks: 5, descriptor: "Clear structure" }, { band: "B", marks: 3, descriptor: "Some structure" }] },
  proposed: { criterion: "Organisation", band: "B", marks: 3, justification: "" },
};
const v1Item: QueueItem = {
  ...base, id: 43, q_id: "q2", reason: "illegible transcription", reason_text: "Unclear handwriting", transcription: "x = 4", rationale: "", evidence: "x = 4",
  criterion_defs: [{ id: "c1", description: "Method", max_score: 2 }, { id: "c2", description: "Answer", max_score: 1 }], proposed_criterion_scores: [2, 0], proposed_total: 2,
};

afterEach(() => vi.unstubAllGlobals());

function setup(items: QueueItem[]) {
  const posted: { path: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/queue") return Promise.resolve(new Response(JSON.stringify(items), { status: 200 }));
    if (/^\/api\/queue\/\d+\/resolve$/.test(path)) { posted.push({ path, body: JSON.parse(String(init!.body)) }); return Promise.resolve(new Response(JSON.stringify({ id: 1, submission_id: 9, submission_status: "done" }), { status: 200 })); }
    return Promise.reject(new Error(`Unexpected fetch to ${path}`));
  }));
  render(
    <MemoryRouter initialEntries={["/review"]}>
      <Routes><Route element={<Outlet context={{ refreshQueue: () => {} }} />}><Route path="/review" element={<Review />} /></Route></Routes>
    </MemoryRouter>,
  );
  return posted;
}

describe("Review — per-part items (v2)", () => {
  it("shows the question, scheme row and transcription; digits toggle allocations; save posts the allocations", async () => {
    const posted = setup([partItem]);
    expect(await screen.findByText("Question 1(b)")).toBeInTheDocument();
    expect(screen.getByText("Hence find y")).toBeInTheDocument();
    expect(screen.getByLabelText("Scheme answer")).toHaveTextContent("y = 5");
    expect(screen.getByLabelText("Scheme answer")).toHaveTextContent("Accept 5.0");
    expect(screen.getByText("y = 2x + 1 = 5")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Marker and reviewer disagreed");
    expect(screen.getByRole("alert")).not.toHaveTextContent("marker/reviewer disagree");
    const save = screen.getByRole("button", { name: /Save & next/ });
    expect(save).toBeDisabled();
    await userEvent.keyboard("1");
    await userEvent.keyboard("2");
    expect(screen.getByRole("checkbox", { name: "M1 · 1 mark" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "A1 · 2 marks" })).toBeChecked();
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("3 / 3");
    await userEvent.type(screen.getByLabelText("Reason (kept with your correction)"), "Both earned");
    await userEvent.click(save);
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toEqual({ path: "/api/queue/41/resolve", body: { allocations: [{ label: "M1", got: true }, { label: "A1", got: true }], reason: "Both earned" } });
  });

  it("accept proposed [A] fills the allocations from the proposal", async () => {
    const posted = setup([partItem]);
    await screen.findByText("Question 1(b)");
    await userEvent.keyboard("a");
    expect(screen.getByRole("checkbox", { name: "M1 · 1 mark" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "A1 · 2 marks" })).not.toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: /Save & next/ }));
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].body).toEqual({ allocations: [{ label: "M1", got: true }, { label: "A1", got: false }], reason: "" });
  });

  it("a deliberate zero-mark resolve is possible: tick then untick leaves Save enabled and every allocation lost", async () => {
    const posted = setup([partItem]);
    await screen.findByText("Question 1(b)");
    await userEvent.keyboard("1");
    await userEvent.keyboard("1");
    expect(screen.getByRole("checkbox", { name: "M1 · 1 mark" })).not.toBeChecked();
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("0 / 3");
    const save = screen.getByRole("button", { name: /Save & next/ });
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].body).toEqual({ allocations: [{ label: "M1", got: false }, { label: "A1", got: false }], reason: "" });
  });

  it("digits typed into the reason box or a text field do not toggle allocations; from a focused checkbox they do", async () => {
    setup([partItem]);
    await screen.findByText("Question 1(b)");
    const reason = screen.getByLabelText("Reason (kept with your correction)");
    await userEvent.type(reason, "12");
    expect(reason).toHaveValue("12");
    expect(screen.getByRole("checkbox", { name: "M1 · 1 mark" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "A1 · 2 marks" })).not.toBeChecked();
    const m1 = screen.getByRole("checkbox", { name: "M1 · 1 mark" });
    m1.focus();
    await userEvent.keyboard("2");
    expect(screen.getByRole("checkbox", { name: "A1 · 2 marks" })).toBeChecked();
  });

  it("rubric items pick a band and post it", async () => {
    const posted = setup([bandItem]);
    expect(await screen.findByText("Organisation")).toBeInTheDocument();
    expect(screen.getByText("Clear structure")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save & next/ })).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: /Band A/ }));
    await userEvent.click(screen.getByRole("button", { name: /Save & next/ }));
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toEqual({ path: "/api/queue/42/resolve", body: { band: "A", reason: "" } });
  });

  it("a rubric criterion not in the rubric is resolved with the proposed band, or 0 marks", async () => {
    const posted = setup([{ ...bandItem, id: 44, q_id: "Flair", label: "Flair", reason: "not in scheme", reason_text: "Not in the rubric", scheme_row: null, proposed: { criterion: "Flair", band: "B", marks: 3, justification: "" }, proposed_total: 3 }]);
    expect(await screen.findByText(/This criterion is not in the rubric/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save & next/ })).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: /Award 0/ }));
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("0 / 3");
    await userEvent.click(screen.getByRole("button", { name: /Save & next/ }));
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toEqual({ path: "/api/queue/44/resolve", body: { band: "B", marks: 0, reason: "" } });
  });

  it("a mark-scheme part with no allocations is resolved with a typed total", async () => {
    const posted = setup([{ ...partItem, id: 45, q_id: "3", label: "3", reason: "not in scheme", reason_text: "Not in the scheme", scheme_row: null, proposed: { q_id: "3", awarded: [], total: 2, justification: "" }, proposed_total: 2 }]);
    await screen.findByText("Question 3");
    expect(screen.getByRole("button", { name: /Save & next/ })).toBeDisabled();
    const input = screen.getByRole("spinbutton", { name: "Your mark" });
    expect(input).toHaveAttribute("max", "2");
    await userEvent.type(input, "1");
    await userEvent.click(screen.getByRole("button", { name: /Save & next/ }));
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toEqual({ path: "/api/queue/45/resolve", body: { total: 1, reason: "" } });
  });

  it("a files-only item reads from the transcription instead of an empty page crop", async () => {
    setup([{ ...partItem, page_ids: [], input_kind: "files" }]);
    await screen.findByText("Question 1(b)");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("Handed in as files — the transcription below is what was read.")).toBeInTheDocument();
    expect(screen.queryByText(/deleted after marking/i)).not.toBeInTheDocument();
    expect(screen.getByText("y = 2x + 1 = 5")).toBeInTheDocument();
  });

  it("still says so when the pages of a photo script were deleted after marking", async () => {
    setup([{ ...partItem, page_ids: [] }]);
    await screen.findByText("Question 1(b)");
    expect(screen.getByText("Pages deleted after marking — the transcription below is what was read.")).toBeInTheDocument();
  });

  it("v1 items still use the criteria table, show the teacher-facing reason and post criterion_scores", async () => {
    const posted = setup([v1Item]);
    await screen.findByText("Question 2");
    expect(screen.getByRole("alert")).toHaveTextContent("Unclear handwriting");
    await userEvent.keyboard("a");
    await userEvent.click(screen.getByRole("button", { name: /Save & next/ }));
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].body).toEqual({ criterion_scores: [2, 0], reason: "" });
  });
});

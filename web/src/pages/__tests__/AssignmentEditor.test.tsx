import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AssignmentTemplate, ExtractStatus } from "../../api/types";
import { AssignmentEditor } from "../AssignmentEditor";

const settings = { provider: "openai", model: "gpt-5-mini", base_url: null, extractor_model: null, rpm_limit: 60, confidence_threshold: 0, has_key: true, key_hint: "abcd", auto_reflect: true, delete_pages_after_marking: true };
const noExtract: ExtractStatus = { paper: { status: null, error: null, job_id: null }, scheme: { status: null, error: null, job_id: null } };
const template = (over: Partial<AssignmentTemplate> = {}): AssignmentTemplate => ({
  id: 7, title: "Quadratics worksheet", subject: "math", context: "", rubric: { criterion_defs: [{ id: "draft", description: "Draft", max_score: 0 }] },
  criteria_count: 1, total_marks: 0, times_used: 0, created_at: "2026-09-15T03:04:05Z", updated_at: "2026-09-15T03:04:05Z",
  scheme_kind: "mark_scheme", questions: [], scheme: [], paper_page_ids: [], scheme_page_ids: [],
  delete_pages_after_marking: null, effective_delete_pages: true, ...over,
});

type Handler = (init?: RequestInit) => Response | Promise<Response>;
function mockFetch(handlers: Record<string, Handler>) {
  const calls: { path: string; method: string; body: any }[] = [];
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    let body: any = null;
    if (typeof init?.body === "string") { try { body = JSON.parse(init.body); } catch { body = init.body; } }
    else if (init?.body instanceof FormData) body = init.body;
    calls.push({ path, method, body });
    const handler = handlers[`${method} ${path}`];
    if (!handler) return Promise.reject(new Error(`Unexpected fetch to ${method} ${path}`));
    return Promise.resolve(handler(init));
  }));
  return calls;
}
const delay = (ms: number, res: Response) => new Promise<Response>((r) => setTimeout(() => r(res), ms));
const dropFile = (zoneTitle: string, name: string) => {
  const zone = screen.getByText(zoneTitle).closest(".drop")!;
  fireEvent.drop(zone, { dataTransfer: { files: [new File(["x"], name, { type: "image/png" })] } });
};
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });

function Where() { const loc = useLocation(); return <div data-testid="where">{loc.pathname}</div>; }
function renderAt(path: string, pollMs = 5) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Where />
      <Routes><Route path="/assignments/:id" element={<AssignmentEditor pollMs={pollMs} />} /></Routes>
    </MemoryRouter>,
  );
}
const saveButton = () => screen.getByRole("button", { name: /^Save|Saving/ });

afterEach(() => vi.unstubAllGlobals());

describe("AssignmentEditor — new", () => {
  it("gates Save with a reason until the type, title, questions and scheme rows are in place", async () => {
    const calls = mockFetch({
      "GET /api/settings": () => json(settings),
      "POST /api/assignments": (init) => json(template({ ...JSON.parse(String(init?.body)), id: 7 }), 201),
    });
    renderAt("/assignments/new");
    expect(await screen.findByRole("heading", { name: "New assignment" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Title")).not.toBeInTheDocument();
    expect(screen.getByText("Choose the assignment type.")).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();

    await userEvent.click(screen.getByRole("radio", { name: "Maths / Science — mark scheme" }));
    expect(saveButton()).toBeDisabled();
    expect(screen.getByText("Give the assignment a title.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Maths" })).toBeChecked();
    expect(screen.getByLabelText("Question paper")).toBeInTheDocument();
    expect(screen.getByLabelText("Mark scheme")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Title"), "Quadratics worksheet");
    expect(screen.getByText("Add at least one question.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "+ Add question" }));
    await userEvent.type(screen.getByLabelText("Question 1 id"), "1a");
    expect(screen.getByText("Add a scheme row for 1(a).")).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    await userEvent.click(screen.getByRole("button", { name: "Add allocation for 1(a)" }));
    await userEvent.type(screen.getByLabelText("Allocation 1 label for 1(a)"), "B1");
    expect(screen.getByText("Ready to save.")).toBeInTheDocument();
    expect(saveButton()).toBeEnabled();

    await userEvent.click(saveButton());
    expect(await screen.findByText(/^Saved\./)).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/assignments")!;
    expect(post.body.scheme_kind).toBe("mark_scheme");
    expect(post.body.title).toBe("Quadratics worksheet");
    expect(post.body.questions).toEqual([{ q_id: "1a", text: "", max_marks: 1 }]);
    expect(post.body.scheme).toEqual([{ q_id: "1a", answer: "", marks: [{ label: "B1", marks: 1 }], notes: "" }]);
    // The batch-2 rubric the API still needs is derived from the scheme.
    expect(post.body.rubric).toEqual({ criterion_defs: [{ id: "1a", description: "1(a)", max_score: 1 }] });
    expect(post.body.delete_pages_after_marking).toBeNull();
    // The editor now edits the stored assignment.
    expect(screen.getByTestId("where")).toHaveTextContent("/assignments/7");
  });

  it("switching the type swaps the sections: rubric table for essays, criteria table for quick mark", async () => {
    mockFetch({ "GET /api/settings": () => json(settings) });
    renderAt("/assignments/new");
    await screen.findByRole("heading", { name: "New assignment" });
    await userEvent.click(screen.getByRole("radio", { name: "Essay — rubric" }));
    expect(screen.getByRole("radio", { name: "English" })).toBeChecked();
    expect(screen.getByLabelText("Rubric")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mark scheme")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Title"), "Narrative essay");
    expect(screen.getByText("Add at least one question.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "+ Add question" }));
    await userEvent.type(screen.getByLabelText("Question 1 id"), "1");
    expect(screen.getByText("Add at least one criterion.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "+ Add criterion" }));
    await userEvent.type(screen.getByLabelText("Criterion 1 name"), "Organisation");
    expect(screen.getByText("Every band for Organisation needs a name.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Band 1 name for Organisation"), "A");
    expect(screen.getByText("Ready to save.")).toBeInTheDocument();

    // Switching to quick mark would lose the questions and the rubric rows: it asks first, then clears both.
    await userEvent.click(screen.getByRole("radio", { name: "Quick mark" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("The questions and rubric rows you have entered will be cleared");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.getByLabelText("Rubric")).toBeInTheDocument();
    expect(screen.getByLabelText("Question 1 id")).toHaveValue("1");
    await userEvent.click(screen.getByRole("radio", { name: "Quick mark" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Change type" }));
    expect(screen.getByLabelText("Criteria")).toBeInTheDocument();
    expect(screen.queryByLabelText("Question paper")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Rubric")).not.toBeInTheDocument();
    expect(screen.getByText("Add at least one criterion.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "+ Add criterion" }));
    await userEvent.type(screen.getByLabelText("Criterion 1 description"), "Correct method");
    expect(screen.getByText("Ready to save.")).toBeInTheDocument();
    // The subject follows the type until the teacher picks one by hand.
    expect(screen.getByRole("radio", { name: "Maths" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "Science" }));
    // Back to a typed kind: nothing to lose, so no dialog, and the questions were cleared by the quick-mark switch.
    await userEvent.click(screen.getByRole("radio", { name: "Essay — rubric" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Science" })).toBeChecked();
    expect(screen.getByLabelText("Rubric")).toBeInTheDocument();
    expect(screen.queryByLabelText("Question 1 id")).not.toBeInTheDocument();
  });

  it("dropping the paper and the scheme back to back creates the draft once", async () => {
    const calls = mockFetch({
      "GET /api/settings": () => json(settings),
      "POST /api/assignments": (init) => delay(40, json(template({ ...JSON.parse(String(init?.body)), id: 7 }), 201)),
      "POST /api/assignments/7/paper": () => json({ pages: [{ id: 31, page_index: 0, width: 1, height: 1 }] }),
      "POST /api/assignments/7/scheme": () => json({ pages: [{ id: 32, page_index: 0, width: 1, height: 1 }, { id: 33, page_index: 1, width: 1, height: 1 }] }),
    });
    renderAt("/assignments/new");
    await screen.findByRole("heading", { name: "New assignment" });
    await userEvent.click(screen.getByRole("radio", { name: "Maths / Science — mark scheme" }));
    await userEvent.type(screen.getByLabelText("Title"), "Quadratics worksheet");
    dropFile("Drop the question paper here", "paper.png");
    dropFile("Drop the mark scheme here", "scheme.png");
    expect(await screen.findByText("1 page uploaded")).toBeInTheDocument();
    expect(await screen.findByText("2 pages uploaded")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST" && c.path === "/api/assignments")).toHaveLength(1);
    expect(calls.some((c) => c.path === "/api/assignments/7/paper")).toBe(true);
    expect(calls.some((c) => c.path === "/api/assignments/7/scheme")).toBe(true);
    expect(screen.getByTestId("where")).toHaveTextContent("/assignments/7");
  });
});

describe("AssignmentEditor — existing", () => {
  it("loads the assignment, reads the paper and fills the questions table when the job finishes", async () => {
    let extractPolls = 0;
    let stored = template({ paper_page_ids: [31, 32] });
    const read = template({ paper_page_ids: [31, 32], questions: [{ q_id: "1a", text: "Solve 2x + 3 = 7", max_marks: 2 }, { q_id: "1b", text: "Hence find y", max_marks: 3 }] });
    const calls = mockFetch({
      "GET /api/settings": () => json(settings),
      "GET /api/assignments": () => json([stored]),
      "GET /api/assignments/7/extract": () => {
        extractPolls += 1;
        if (extractPolls === 1) return json(noExtract);
        if (extractPolls === 2) return json({ ...noExtract, paper: { status: "running", error: null, job_id: 9 } });
        stored = read;
        return json({ ...noExtract, paper: { status: "done", error: null, job_id: 9 } });
      },
      "POST /api/assignments/7/extract/paper": () => json({ job_id: 9 }, 202),
      "PUT /api/assignments/7": (init) => json({ ...stored, ...JSON.parse(String(init?.body)) }),
    });
    renderAt("/assignments/7");
    expect(await screen.findByRole("heading", { name: "Quadratics worksheet" })).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveValue("Quadratics worksheet");
    expect(screen.getByText("2 pages uploaded")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Follow default (on)" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "+ Add question" }));
    await userEvent.click(screen.getByRole("button", { name: "Read questions" }));
    expect(await screen.findByRole("button", { name: "Reading…" })).toBeDisabled();
    expect(screen.getByText("Wait for the pages to be read.")).toBeInTheDocument();
    expect(screen.getByText(/The table unlocks when it's done/)).toBeInTheDocument();
    // Nothing typed while the job runs can be overwritten: the table is locked until it finishes.
    expect(screen.getByLabelText("Question 1 id")).toBeDisabled();
    expect(screen.getByRole("button", { name: "+ Add question" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove question 1" })).toBeDisabled();
    expect(await screen.findByLabelText("Question 2 id")).toHaveValue("1b");
    expect(screen.getByLabelText("Question 1 id")).toBeEnabled();
    expect(screen.getByRole("button", { name: "+ Add question" })).toBeEnabled();
    expect(screen.getByLabelText("Question 1 text")).toHaveValue("Solve 2x + 3 = 7");
    expect(screen.getByLabelText("Total marks")).toHaveTextContent("5");
    expect(screen.getByRole("button", { name: "Read questions" })).toBeEnabled();
    expect(screen.getByText("Add scheme rows for 1(a) and 1(b).")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/assignments/7/extract/paper")).toBe(true);
    // Nothing was written to the server while the job was running.
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("a failed extraction shows the job's error and lets the teacher try again", async () => {
    let polls = 0;
    const stored = template({ paper_page_ids: [31] });
    mockFetch({
      "GET /api/settings": () => json(settings),
      "GET /api/assignments": () => json([stored]),
      "GET /api/assignments/7/extract": () => {
        polls += 1;
        if (polls === 1) return json(noExtract);
        if (polls === 2) return json({ ...noExtract, paper: { status: "running", error: null, job_id: 9 } });
        return json({ ...noExtract, paper: { status: "failed", error: "No API key configured", job_id: 9 } });
      },
      "POST /api/assignments/7/extract/paper": () => json({ job_id: 9 }, 202),
    });
    renderAt("/assignments/7");
    await screen.findByLabelText("Title");
    await userEvent.click(screen.getByRole("button", { name: "Read questions" }));
    expect(await screen.findByRole("button", { name: "Reading…" })).toBeDisabled();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not read the pages: No API key configured. Try again.");
    expect(screen.getByRole("button", { name: "Read questions" })).toBeEnabled();
    expect(screen.queryByText("Wait for the pages to be read.")).not.toBeInTheDocument();
  });

  it("stops polling when the editor unmounts", async () => {
    let polls = 0;
    const stored = template({ paper_page_ids: [31] });
    mockFetch({
      "GET /api/settings": () => json(settings),
      "GET /api/assignments": () => json([stored]),
      "GET /api/assignments/7/extract": () => { polls += 1; return json(polls === 1 ? noExtract : { ...noExtract, paper: { status: "running", error: null, job_id: 9 } }); },
      "POST /api/assignments/7/extract/paper": () => json({ job_id: 9 }, 202),
    });
    const { unmount } = renderAt("/assignments/7", 10);
    await screen.findByLabelText("Title");
    await userEvent.click(screen.getByRole("button", { name: "Read questions" }));
    await waitFor(() => expect(polls).toBeGreaterThanOrEqual(3));
    unmount();
    const seen = polls;
    await new Promise((r) => setTimeout(r, 60));
    expect(polls).toBe(seen);
  });

  it("autosaves a draft when focus leaves a changed field", async () => {
    const stored = template({ scheme_kind: "rubric", subject: "language" });
    const calls = mockFetch({
      "GET /api/settings": () => json(settings),
      "GET /api/assignments": () => json([stored]),
      "GET /api/assignments/7/extract": () => json(noExtract),
      "PUT /api/assignments/7": (init) => json({ ...stored, ...JSON.parse(String(init?.body)) }),
    });
    renderAt("/assignments/7");
    await screen.findByLabelText("Title");
    await userEvent.type(screen.getByLabelText("Notes (optional)"), "ECF applies");
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    await userEvent.tab();
    await waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.path === "/api/assignments/7")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.body.context).toBe("ECF applies");
    expect(put.body.scheme_kind).toBe("rubric");
    expect(put.body.rubric.criterion_defs).toEqual([{ id: "draft", description: "Draft", max_score: 0 }]);
    expect(await screen.findByRole("status")).toHaveTextContent("Draft saved");
    // Unchanged → no second PUT on the next blur.
    await userEvent.click(screen.getByLabelText("Title"));
    await userEvent.tab();
    expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1);
  });

  it("a change made while a draft save is in flight is saved right after it", async () => {
    const stored = template({ scheme_kind: "rubric", subject: "language" });
    let puts = 0;
    const calls = mockFetch({
      "GET /api/settings": () => json(settings),
      "GET /api/assignments": () => json([stored]),
      "GET /api/assignments/7/extract": () => json(noExtract),
      "PUT /api/assignments/7": (init) => {
        puts += 1;
        const res = json({ ...stored, ...JSON.parse(String(init?.body)) });
        return puts === 1 ? new Promise((r) => setTimeout(() => r(res), 80)) : res;
      },
    });
    renderAt("/assignments/7");
    await screen.findByLabelText("Title");
    await userEvent.type(screen.getByLabelText("Notes (optional)"), "ECF");
    await userEvent.tab();
    await userEvent.type(screen.getByLabelText("Title"), " v2");
    await userEvent.tab();
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(2));
    const bodies = calls.filter((c) => c.method === "PUT").map((c) => c.body);
    expect(bodies[0].title).toBe("Quadratics worksheet");
    expect(bodies[1].title).toBe("Quadratics worksheet v2");
    expect(bodies[1].context).toBe("ECF");
  });

  it("shows a plain message when the assignment is gone", async () => {
    mockFetch({
      "GET /api/settings": () => json(settings),
      "GET /api/assignments": () => json([]),
      "GET /api/assignments/99/extract": () => json({ error: { code: "not_found", message: "No such assignment" } }, 404),
    });
    renderAt("/assignments/99");
    expect(await screen.findByText("This assignment no longer exists.")).toBeInTheDocument();
  });
});

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AssignmentTemplate } from "../../api/types";
import { BulkMark } from "../BulkMark";

const settings = { provider: "openai", model: "gpt-5-mini", base_url: null, extractor_model: null, rpm_limit: 60, confidence_threshold: 0, has_key: true, key_hint: "abcd", auto_reflect: true };
const worksheet: AssignmentTemplate = {
  id: 3, title: "Quadratics — Worksheet 3", subject: "math", context: "Sec 4", rubric: { criterion_defs: [{ id: "m", description: "Method", max_score: 5 }] },
  language: null, criteria_count: 1, total_marks: 5, times_used: 2, created_at: "2026-09-15T03:04:05Z", updated_at: "2026-09-15T03:04:05Z",
  scheme_kind: "mark_scheme", questions: [{ q_id: "1", text: "Solve", max_marks: 5 }], scheme: [{ q_id: "1", answer: "x = 2", marks: 5 }] as never,
  paper_page_ids: [], scheme_page_ids: [], delete_pages_after_marking: null, effective_delete_pages: true,
  provider: null, model: null, extractor_model: null, effective_model: { provider: "openai", model: "gpt-5-mini", extractor_model: null, source: "settings" },
};

afterEach(() => vi.unstubAllGlobals());

function setup(failLabel?: string) {
  const posted: FormData[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/settings") return new Response(JSON.stringify(settings), { status: 200 });
    if (path === "/api/assignments") return new Response(JSON.stringify([worksheet]), { status: 200 });
    if (path === "/api/submissions" && init?.method === "POST") {
      const fd = init.body as FormData; posted.push(fd);
      if (fd.get("label") === failLabel) return new Response(JSON.stringify({ error: { code: "too_many_pages", message: "Too many pages" } }), { status: 400 });
      return new Response(JSON.stringify({ id: posted.length, status: "queued" }), { status: 202 });
    }
    throw new Error(`Unexpected fetch to ${path}`);
  }));
  render(<MemoryRouter initialEntries={["/submissions/bulk"]}><Routes>
    <Route path="/submissions/bulk" element={<BulkMark />} />
    <Route path="/submissions" element={<h1>Submissions list</h1>} />
  </Routes></MemoryRouter>);
  return { posted };
}

const drop = (files: File[]) => {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  fireEvent.change(input, { target: { files } });
};
const page = (name: string) => new File(["x"], name, { type: name.endsWith(".pdf") ? "application/pdf" : "image/png" });

describe("BulkMark", () => {
  it("groups dropped files into labelled scripts, uploads each against the chosen assignment, then returns to Submissions", async () => {
    const { posted } = setup();
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Assignment"), "3");
    drop([page("Tan Wei Ling-2.png"), page("Tan Wei Ling-1.png"), page("Ravi.pdf")]);
    const table = await screen.findByRole("table", { name: "Scripts to mark" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("1");
    expect(screen.getByLabelText("Label for script 1")).toHaveValue("Ravi");
    expect(screen.getByLabelText("Label for script 2")).toHaveValue("Tan Wei Ling");
    expect(rows[1]).toHaveTextContent("2");
    await user.clear(screen.getByLabelText("Label for script 1"));
    await user.type(screen.getByLabelText("Label for script 1"), "Ravi Kumar");
    await user.click(screen.getByRole("button", { name: "Start marking 2 scripts" }));
    await screen.findByText("Submissions list");
    expect(posted).toHaveLength(2);
    const labels = posted.map((fd) => fd.get("label")).sort();
    expect(labels).toEqual(["Ravi Kumar", "Tan Wei Ling"]);
    const tan = posted.find((fd) => fd.get("label") === "Tan Wei Ling")!;
    expect(tan.get("assignment_id")).toBe("3");
    expect(tan.get("subject")).toBe("math");
    expect((tan.getAll("files") as File[]).map((f) => f.name)).toEqual(["Tan Wei Ling-1.png", "Tan Wei Ling-2.png"]);
  });

  it("will not start without an assignment or with two scripts sharing a label, and keeps the failed ones for a retry", async () => {
    const { posted } = setup("Lim Jun Hao");
    const user = userEvent.setup();
    await screen.findByLabelText("Assignment");
    drop([page("Lim Jun Hao.pdf"), page("Nur Aisyah.pdf")]);
    const start = await screen.findByRole("button", { name: "Start marking 2 scripts" });
    expect(start).toBeDisabled();
    expect(start).toHaveAttribute("title", "Choose the assignment these scripts answer.");
    await user.selectOptions(screen.getByLabelText("Assignment"), "3");
    await user.clear(screen.getByLabelText("Label for script 2"));
    await user.type(screen.getByLabelText("Label for script 2"), "lim jun hao");
    expect(start).toHaveAttribute("title", "Two scripts share a label — make them different.");
    await user.clear(screen.getByLabelText("Label for script 2"));
    await user.type(screen.getByLabelText("Label for script 2"), "Nur Aisyah");
    await user.click(start);
    await screen.findByRole("button", { name: "Retry 1 failed" });
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText(/Failed · Too many pages/)).toBeInTheDocument();
    expect(screen.queryByText("Submissions list")).toBeNull();
    expect(posted).toHaveLength(2);
    await user.clear(screen.getByLabelText("Label for script 1"));
    await user.type(screen.getByLabelText("Label for script 1"), "Lim JH");
    await user.click(screen.getByRole("button", { name: "Retry 1 failed" }));
    await waitFor(() => expect(posted).toHaveLength(3));
    expect(posted[2].get("label")).toBe("Lim JH");
    await screen.findByText("Submissions list");
  });
});

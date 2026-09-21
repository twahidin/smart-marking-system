import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AssignmentTemplate } from "../../api/types";
import { NewSubmission } from "../NewSubmission";

// Stands in for the canvas resize jsdom cannot run: a 4000 px photo comes back small, and renamed.
vi.mock("../../lib/image", () => ({
  downscale: vi.fn((f: File) => Promise.resolve(new File(["x".repeat(1234)], f.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" }))),
}));

const settings = { provider: "openai", model: "gpt-5-mini", base_url: null, extractor_model: null, rpm_limit: 60, confidence_threshold: 0, has_key: true, key_hint: "abcd", auto_reflect: true };
const templates: AssignmentTemplate[] = [
  { id: 5, title: "Essay draft", subject: "language", context: "Sec 3 · Narrative", rubric: { criterion_defs: [{ id: "s", description: "Structure", max_score: 5 }, { id: "g", description: "Grammar", max_score: 3 }, { id: "v", description: "Vocabulary", max_score: 2 }] },
    language: null, criteria_count: 3, total_marks: 10, times_used: 1, created_at: "2026-09-15T03:04:05Z", updated_at: "2026-09-15T03:04:05Z",
    scheme_kind: "criteria", questions: [{ q_id: "1", text: "Write a narrative about a journey.", max_marks: 10 }], scheme: [], paper_page_ids: [], scheme_page_ids: [], delete_pages_after_marking: null, effective_delete_pages: true,
    provider: null, model: null, extractor_model: null, effective_model: { provider: "openai", model: "gpt-5-mini", extractor_model: null, source: "settings" } },
];

afterEach(() => vi.unstubAllGlobals());

describe("NewSubmission — saved assignments", () => {
  it("choosing a saved assignment fills subject, context and the criteria table", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/settings") return Promise.resolve(new Response(JSON.stringify(settings), { status: 200 }));
      if (path === "/api/assignments") return Promise.resolve(new Response(JSON.stringify(templates), { status: 200 }));
      return Promise.reject(new Error(`Unexpected fetch to ${path}`));
    }));
    render(<MemoryRouter><NewSubmission /></MemoryRouter>);
    const select = await screen.findByLabelText("Use a saved assignment");
    expect(within(select).getByRole("option", { name: "— none —" })).toBeInTheDocument();
    await userEvent.selectOptions(select, "5");
    expect(screen.getByLabelText("Criterion 1 description")).toHaveValue("Structure");
    expect(screen.getByLabelText("Criterion 3 description")).toHaveValue("Vocabulary");
    expect(screen.getByLabelText("Criterion 1 max marks")).toHaveValue(5);
    expect(screen.getByLabelText("Context (optional)")).toHaveValue("Sec 3 · Narrative");
    expect(screen.getByRole("radio", { name: "English" })).toBeChecked();
    // The label belongs to the student and is left alone.
    expect(screen.getByLabelText("Label")).toHaveValue("");
    // The paper's questions are shown read-only above the criteria table.
    const qs = screen.getByLabelText("Assignment questions");
    expect(qs).toHaveTextContent("1 question · 10 marks");
    expect(qs).toHaveTextContent("Write a narrative about a journey.");
    await userEvent.selectOptions(select, "");
    expect(screen.queryByLabelText("Assignment questions")).not.toBeInTheDocument();
  });
});

const markScheme: AssignmentTemplate = {
  id: 8, title: "Quadratics — Worksheet 3", subject: "math", context: "Sec 4", rubric: { criterion_defs: [{ id: "1a", description: "Solve", max_score: 3 }, { id: "1b", description: "Hence", max_score: 2 }] },
  language: null, criteria_count: 2, total_marks: 5, times_used: 0, created_at: "2026-09-15T03:04:05Z", updated_at: "2026-09-15T03:04:05Z",
  scheme_kind: "mark_scheme", questions: [{ q_id: "1a", text: "Solve 2x + 3 = 7", max_marks: 3 }, { q_id: "1b", text: "Hence find y", max_marks: 2 }],
  scheme: [{ q_id: "1a", answer: "x = 2", marks: [{ label: "M1", marks: 1 }, { label: "A1", marks: 2 }], notes: "" }, { q_id: "1b", answer: "y = 5", marks: [{ label: "B1", marks: 2 }], notes: "" }],
  paper_page_ids: [], scheme_page_ids: [], delete_pages_after_marking: null, effective_delete_pages: true,
  provider: null, model: null, extractor_model: null, effective_model: { provider: "openai", model: "gpt-5-mini", extractor_model: null, source: "settings" },
};

describe("NewSubmission — assignment first", () => {
  it("hides the criteria editor for a mark-scheme assignment and sends its id and rubric", async () => {
    const posted: FormData[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/settings") return Promise.resolve(new Response(JSON.stringify(settings), { status: 200 }));
      if (path === "/api/assignments") return Promise.resolve(new Response(JSON.stringify([...templates, markScheme]), { status: 200 }));
      if (path === "/api/submissions") { posted.push(init!.body as FormData); return Promise.resolve(new Response(JSON.stringify({ id: 12, status: "queued", pages: [] }), { status: 201 })); }
      return Promise.reject(new Error(`Unexpected fetch to ${path}`));
    }));
    render(<MemoryRouter><NewSubmission /></MemoryRouter>);
    const select = await screen.findByLabelText("Use a saved assignment");
    expect(screen.getByLabelText("Criterion 1 description")).toBeInTheDocument();
    await userEvent.selectOptions(select, "8");
    // The criteria table is replaced by a read-only summary of the saved scheme and its questions.
    expect(screen.queryByLabelText("Criterion 1 description")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save as assignment" })).not.toBeInTheDocument();
    const qs = screen.getByLabelText("Assignment questions");
    expect(qs).toHaveTextContent("2 questions · 5 marks · mark scheme");
    expect(qs).toHaveTextContent("1(a)");
    expect(qs).toHaveTextContent("Hence find y");
    expect(screen.getByRole("radio", { name: "Maths" })).toBeChecked();
    // Back to Quick mark: the editor returns.
    await userEvent.selectOptions(select, "");
    expect(screen.getByLabelText("Criterion 1 description")).toBeInTheDocument();
    await userEvent.selectOptions(select, "8");
    await userEvent.type(screen.getByLabelText("Label"), "Lim Jun Hao");
    const drop = document.querySelector('input[type="file"][multiple]') as HTMLInputElement;
    await userEvent.upload(drop, new File(["x"], "p1.jpg", { type: "image/jpeg" }));
    await userEvent.click(screen.getByRole("button", { name: "Start marking" }));
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].get("assignment_id")).toBe("8");
    expect(JSON.parse(String(posted[0].get("rubric")))).toEqual(markScheme.rubric);
  });
});

const computing: AssignmentTemplate = { ...markScheme, id: 9, title: "Loops — Task 2", subject: "computing" };

function stub(posted: FormData[], list: AssignmentTemplate[]) {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/settings") return Promise.resolve(new Response(JSON.stringify(settings), { status: 200 }));
    if (path === "/api/assignments") return Promise.resolve(new Response(JSON.stringify(list), { status: 200 }));
    if (path === "/api/submissions") { posted.push(init!.body as FormData); return Promise.resolve(new Response(JSON.stringify({ id: 12, status: "queued", pages: [] }), { status: 201 })); }
    return Promise.reject(new Error(`Unexpected fetch to ${path}`));
  }));
}

const dropInput = () => document.querySelector('input[type="file"][multiple]') as HTMLInputElement;

describe("NewSubmission — pages and files", () => {
  it("offers all five subjects, shrinks the photos, and asks for a page or a file", async () => {
    const posted: FormData[] = [];
    stub(posted, templates);
    render(<MemoryRouter><NewSubmission /></MemoryRouter>);
    await screen.findByLabelText("Use a saved assignment");
    for (const name of ["Maths", "English", "Science", "MT", "Computing"]) {
      expect(screen.getByRole("radio", { name })).toBeInTheDocument();
    }
    await userEvent.type(screen.getByLabelText("Label"), "Tan Wei Ling");
    expect(screen.getByText("Add at least one page or file.")).toBeInTheDocument();
    // Without a Computing assignment chosen, the drop zone still takes pages only.
    expect(dropInput().accept).not.toMatch(/\.py/);
    await userEvent.upload(dropInput(), new File(["x".repeat(4000)], "big.png", { type: "image/png" }));
    expect(screen.queryByText("Add at least one page or file.")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start marking" }));
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].getAll("files").map((f) => (f as File).name)).toEqual(["big.jpg"]);
  });

  it("takes program files once a Computing assignment is chosen", async () => {
    const posted: FormData[] = [];
    stub(posted, [...templates, computing]);
    render(<MemoryRouter><NewSubmission /></MemoryRouter>);
    const select = await screen.findByLabelText("Use a saved assignment");
    await userEvent.selectOptions(select, "9");
    expect(screen.getByRole("radio", { name: "Computing" })).toBeChecked();
    expect(dropInput().accept).toContain(".py,.sb3,.xlsx,.zip");
    await userEvent.type(screen.getByLabelText("Label"), "Tan Wei Ling");
    await userEvent.upload(dropInput(), new File(["print(1)"], "prog.py", { type: "text/x-python" }));
    await userEvent.click(screen.getByRole("button", { name: "Start marking" }));
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    // A program file goes up byte for byte, under its own name.
    expect(posted[0].getAll("files").map((f) => (f as File).name)).toEqual(["prog.py"]);
  });

  it("names what the server skipped out of a zip before moving on", async () => {
    const posted: FormData[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/settings") return Promise.resolve(new Response(JSON.stringify(settings), { status: 200 }));
      if (path === "/api/assignments") return Promise.resolve(new Response(JSON.stringify([...templates, computing]), { status: 200 }));
      if (path === "/api/submissions") {
        posted.push(init!.body as FormData);
        return Promise.resolve(new Response(JSON.stringify({ id: 12, status: "queued", pages: [], ignored: ["notes.txt", "data.csv"] }), { status: 201 }));
      }
      return Promise.reject(new Error(`Unexpected fetch to ${path}`));
    }));
    render(<MemoryRouter><NewSubmission /></MemoryRouter>);
    await userEvent.selectOptions(await screen.findByLabelText("Use a saved assignment"), "9");
    await userEvent.type(screen.getByLabelText("Label"), "Tan Wei Ling");
    await userEvent.upload(dropInput(), new File(["zip"], "work.zip", { type: "application/zip" }));
    await userEvent.click(screen.getByRole("button", { name: "Start marking" }));
    expect(await screen.findByText("Skipped: notes.txt, data.csv")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open the script" })).toBeInTheDocument();
  });
});

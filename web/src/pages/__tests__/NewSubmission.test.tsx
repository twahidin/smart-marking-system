import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AssignmentTemplate } from "../../api/types";
import { NewSubmission } from "../NewSubmission";

const settings = { provider: "openai", model: "gpt-5-mini", base_url: null, extractor_model: null, rpm_limit: 60, confidence_threshold: 0, has_key: true, key_hint: "abcd", auto_reflect: true };
const templates: AssignmentTemplate[] = [
  { id: 5, title: "Essay draft", subject: "language", context: "Sec 3 · Narrative", rubric: { criterion_defs: [{ id: "s", description: "Structure", max_score: 5 }, { id: "g", description: "Grammar", max_score: 3 }, { id: "v", description: "Vocabulary", max_score: 2 }] },
    criteria_count: 3, total_marks: 10, times_used: 1, created_at: "2026-09-15T03:04:05Z", updated_at: "2026-09-15T03:04:05Z",
    scheme_kind: "criteria", questions: [{ q_id: "1", text: "Write a narrative about a journey.", max_marks: 10 }], scheme: [], paper_page_ids: [], scheme_page_ids: [], delete_pages_after_marking: null, effective_delete_pages: true },
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

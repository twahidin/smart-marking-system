import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { StudentAssignmentDetail, StudentFeedback, StudentMe } from "../../api/types";
import { AssignmentView } from "../AssignmentView";
import { StudentLayout } from "../StudentLayout";

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
      try { return Promise.resolve(handler(init)); } catch (e) { return Promise.reject(e); }
    }),
  );
  return calls;
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const me: StudentMe = { class_name: "4E2", code: "CE4R", student_name: "Tan Wei Ling", reg_no: 1 };
const ok = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const detail = (over: Partial<StudentAssignmentDetail>): StudentAssignmentDetail =>
  ({ id: 1, title: "Worksheet 3", due_at: null, status: "handed_in", handed_in_at: "2026-09-09T07:12:00Z", pages: 4, allow_student_uploads: true, feedback: null, ...over });

function app(path: string) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/s" element={<StudentLayout />}>
          <Route index element={<p>home page</p>} />
          <Route path="a/:caid" element={<AssignmentView />} />
          <Route path="a/:caid/hand-in" element={<p>hand-in page</p>} />
        </Route>
        <Route path="/join" element={<p>join page</p>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("AssignmentView", () => {
  it("shows the calm waiting state", async () => {
    mockFetch({ "GET /api/student/me": () => ok(me), "GET /api/student/assignments/1": () => ok({ id: 1, title: "Worksheet 3", due_at: null, status: "handed_in", handed_in_at: "2026-09-09T07:12:00Z", pages: 4, allow_student_uploads: true, feedback: null }) });
    render(app("/s/a/1"));
    expect(await screen.findByText(/Marking usually takes a day/)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("renders released feedback in order and expands a question", async () => {
    const fb = { summary: "You factorise confidently.", strengths: ["Q1 both factors correct"], improvement_plan: ["Check signs"], next_steps: ["Redo Q3"], total: 18, max: 25,
      questions: [{ label: "1(a)", mark: 4, max: 4, comment: "Clear.", try_next: "Keep going.", transcription: "x = 3" }, { label: "3", mark: 3, max: 5, comment: "Sign slip.", try_next: "Try the formula again.", transcription: "x = -2" }], pages: [7] };
    mockFetch({ "GET /api/student/me": () => ok(me), "GET /api/student/assignments/1": () => ok({ id: 1, title: "Worksheet 3", due_at: null, status: "feedback_ready", handed_in_at: "2026-09-09T07:12:00Z", pages: 1, allow_student_uploads: true, feedback: fb }) });
    render(app("/s/a/1"));
    expect(await screen.findByText("18")).toBeInTheDocument();
    expect(screen.getByText("/ 25")).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["What you did well", "Question by question", "Work on next", "Next steps"]);
    await userEvent.click(screen.getByRole("button", { name: /3 · 3 \/ 5/ }));
    expect(screen.getByText("Sign slip.")).toBeInTheDocument();
    expect(screen.getByText(/Try next: Try the formula again/)).toBeInTheDocument();
    expect(screen.getByText("x = -2")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Your page 1" })).toHaveAttribute("src", "/api/student/pages/7");
  });

  it("waits calmly while the teacher checks, with a way back", async () => {
    mockFetch({ "GET /api/student/me": () => ok(me), "GET /api/student/assignments/1": () => ok(detail({ status: "checking" })) });
    render(app("/s/a/1"));
    expect(await screen.findByText(/your teacher is checking/)).toBeInTheDocument();
    expect(screen.getByText(/Come back when your teacher releases the feedback/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to assignments" })).toHaveAttribute("href", "/s");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("sends a to-hand-in assignment to the hand-in screen", async () => {
    mockFetch({ "GET /api/student/me": () => ok(me), "GET /api/student/assignments/1": () => ok(detail({ status: "to_hand_in", handed_in_at: null, pages: 0 })) });
    render(app("/s/a/1"));
    expect(await screen.findByText("hand-in page")).toBeInTheDocument();
  });

  it("marks a question with no comment and keeps the aria-expanded state per question", async () => {
    const fb: StudentFeedback = { summary: "", strengths: [], improvement_plan: [], next_steps: [], total: 2, max: 4,
      questions: [{ label: "1", mark: 2, max: 4, comment: "", try_next: "", transcription: "" }], pages: [] };
    mockFetch({ "GET /api/student/me": () => ok(me), "GET /api/student/assignments/1": () => ok(detail({ status: "feedback_ready", feedback: fb })) });
    render(app("/s/a/1"));
    const row = await screen.findByRole("button", { name: /1 · 2 \/ 4/ });
    expect(row).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("No comment for this question.")).toBeInTheDocument();
    expect(screen.queryByText(/Try next:/)).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    // empty lists don't leave empty headings behind
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Question by question"]);
  });

  it("offers a retry when the assignment can't be loaded", async () => {
    let fail = true;
    mockFetch({ "GET /api/student/me": () => ok(me), "GET /api/student/assignments/1": () => { if (fail) throw new TypeError("Failed to fetch"); return ok(detail({})); } });
    render(app("/s/a/1"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach Smart Marking — check your signal and try again.");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/Marking usually takes a day/)).toBeInTheDocument();
  });
});

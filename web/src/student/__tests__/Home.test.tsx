import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { StudentAssignment, StudentMe } from "../../api/types";
import { Home } from "../Home";
import { StudentLayout } from "../StudentLayout";

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

const me: StudentMe = { class_name: "4E2", code: "CE4R", student_name: "Tan Wei Ling", reg_no: 1 };
const base = { due_at: "2026-09-20T08:00:00Z", handed_in_at: null, pages: 0, allow_student_uploads: true };
const assignments: StudentAssignment[] = [
  { ...base, id: 1, title: "Algebra worksheet", status: "to_hand_in" },
  { ...base, id: 2, title: "Fractions quiz", status: "handed_in", handed_in_at: "2026-09-18T08:00:00Z", pages: 2 },
  { ...base, id: 3, title: "Graphs homework", status: "checking", pages: 3 },
  { ...base, id: 4, title: "Ratios test", status: "feedback_ready", pages: 4 },
  { ...base, id: 5, title: "Closed one", status: "to_hand_in", allow_student_uploads: false },
];

function renderHome(entry = "/s") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/s" element={<StudentLayout />}>
          <Route index element={<Home />} />
        </Route>
        <Route path="/join" element={<p>join page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Home", () => {
  it("lists each assignment with its status control and shows who is signed in", async () => {
    mockFetch({
      "GET /api/student/me": () => new Response(JSON.stringify(me), { status: 200 }),
      "GET /api/student/assignments": () => new Response(JSON.stringify(assignments), { status: 200 }),
    });
    renderHome();
    expect(await screen.findByText("Tan Wei Ling · #1")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Submissions" })).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "To hand in" })).toHaveAttribute("href", "/s/a/1/hand-in");
    expect(screen.getByRole("link", { name: "Handed in · marking" })).toHaveAttribute("href", "/s/a/2");
    expect(screen.getByText("Marked — your teacher is checking")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Feedback ready" })).toHaveAttribute("href", "/s/a/4");
    expect(screen.getByText("Hand-ins closed")).toBeInTheDocument();
    expect(screen.getByText("Algebra worksheet")).toBeInTheDocument();
    expect(screen.getAllByText(/^Due /).length).toBe(5);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/escalation|confidence|reviewer/i);
  });

  it("shows the empty state", async () => {
    mockFetch({
      "GET /api/student/me": () => new Response(JSON.stringify(me), { status: 200 }),
      "GET /api/student/assignments": () => new Response("[]", { status: 200 }),
    });
    renderHome();
    expect(await screen.findByText("No assignments yet — check back when your teacher sets one.")).toBeInTheDocument();
  });

  it("sends the student to /join when there is no session", async () => {
    mockFetch({
      "GET /api/student/me": () => new Response(JSON.stringify({ error: { code: "student_session", message: "Enter your number first" } }), { status: 401 }),
    });
    renderHome();
    expect(await screen.findByText("join page")).toBeInTheDocument();
  });

  it("Not me? ends the session and goes to /join", async () => {
    const calls = mockFetch({
      "GET /api/student/me": () => new Response(JSON.stringify(me), { status: 200 }),
      "GET /api/student/assignments": () => new Response("[]", { status: 200 }),
      "DELETE /api/student/session": () => new Response(null, { status: 204 }),
    });
    renderHome();
    await userEvent.click(await screen.findByRole("button", { name: "Not me?" }));
    expect(await screen.findByText("join page")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/student/session")).toBe(true);
  });
});

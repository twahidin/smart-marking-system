import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Reflect } from "../Reflect";

const detail = { id: 7, title: "Quadratics", status: "feedback_ready", handed_in_at: "2026-10-01T00:00:00Z", due_at: null, pages: 1, allow_student_uploads: true, subject: "math", accepts_files: false,
  feedback: { summary: "", strengths: [], improvement_plan: [], next_steps: [], total: 3, max: 6, pages: [],
    questions: [{ q_id: "1b", label: "1(b)", mark: 0, max: 1, comment: "6 not 9", try_next: "", transcription: "6", crop_id: 55 }] },
  reflection: { window_ends_at: "2026-10-15T00:00:00Z", days_left: 5, parts: { "1b": { can_correct: true, status: null, new_mark: null } } } };

afterEach(() => vi.unstubAllGlobals());

describe("Reflect", () => {
  it("shows the original crop and comment, sends the correction, and confirms", async () => {
    const sent: FormData[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/student/assignments/7") return Promise.resolve(new Response(JSON.stringify(detail), { status: 200 }));
      if (path === "/api/student/assignments/7/corrections") { sent.push(init!.body as FormData); return Promise.resolve(new Response(JSON.stringify({ id: 1, q_id: "1b", status: "submitted" }), { status: 201 })); }
      return Promise.reject(new Error(`Unexpected fetch to ${path}`));
    }));
    render(<MemoryRouter initialEntries={["/s/a/7/reflect/1b"]}><Routes><Route path="/s/a/:caid/reflect/:qid" element={<Reflect />} /></Routes></MemoryRouter>);
    await screen.findByText("1(b) · Reflect and correct");
    expect(screen.getByRole("img", { name: "Your first try" })).toHaveAttribute("src", "/api/student/crops/55");
    expect(screen.getByText("6 not 9")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign slip" }));
    await userEvent.type(screen.getByLabelText("Your corrected working"), "x^2 = 3^2 = 9");
    await userEvent.click(screen.getByRole("button", { name: "Send my correction" }));
    await waitFor(() => expect(screen.getByText("Sent to the Marker. Your teacher checks it before you see the new mark.")).toBeInTheDocument());
    expect(sent[0].get("q_id")).toBe("1b"); expect(sent[0].get("reason")).toBe("sign"); expect(sent[0].get("text")).toBe("x^2 = 3^2 = 9");
  });
});

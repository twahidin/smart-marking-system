import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Correction } from "../../api/types";
import { CorrectionsTab } from "../CorrectionsTab";

const row: Correction = { id: 5, submission_id: 9, submission_label: "#1 Tan", reg_no: 1, student_name: "Tan", q_id: "1b", reason: "sign", text: "x^2 = 9", page_id: null,
  status: "remarked", remark_total: 1, remark_max: 1, remark_note: "Marker: B1 earned\nChecker: APPROVE: agree", teacher_total: null, teacher_reason: null, error: null, submitted_at: "2026-10-08T01:00:00Z", released_at: null,
  original_total: 0, original_max: 1, crop_id: 7 };

afterEach(() => vi.unstubAllGlobals());

describe("CorrectionsTab", () => {
  it("lists corrections with the Marker's re-mark and posts accept, override and release", async () => {
    const posted: { path: string; body: unknown }[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/review/corrections?class_assignment_id=3") return Promise.resolve(new Response(JSON.stringify([row]), { status: 200 }));
      posted.push({ path, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (path.endsWith("/release-corrections")) return Promise.resolve(new Response(JSON.stringify({ released: 1 }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify({ ...row, status: "accepted" }), { status: 200 }));
    }));
    render(<MemoryRouter><CorrectionsTab classAssignmentId={3} /></MemoryRouter>);
    await screen.findByText("#1 Tan · 1b");
    expect(screen.getByText("Marker: B1 earned")).toBeInTheDocument();
    expect(screen.getByText("Re-marked 1 / 1")).toBeInTheDocument();
    expect(screen.getByText("First try: 0 / 1")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "The student's first answer" })).toHaveAttribute("src", "/api/crops/7");
    await userEvent.click(screen.getByRole("button", { name: "Accept 1 / 1" }));
    await userEvent.type(screen.getByLabelText("Override mark"), "0.5");
    await userEvent.click(screen.getByRole("button", { name: "Override" }));
    await userEvent.click(screen.getByRole("button", { name: "Release corrections" }));
    await waitFor(() => expect(posted.map((p) => p.path)).toEqual(["/api/corrections/5/accept", "/api/corrections/5/override", "/api/class-assignments/3/release-corrections"]));
    expect(posted[1].body).toEqual({ total: 0.5 });
  });

  it("tells the teacher the reject reason stays with them", async () => {
    const posted: { path: string; body: unknown }[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith("/api/review/corrections")) return Promise.resolve(new Response(JSON.stringify([{ ...row, crop_id: null }]), { status: 200 }));
      posted.push({ path, body: init?.body ? JSON.parse(String(init.body)) : null });
      return Promise.resolve(new Response(JSON.stringify({ ...row, status: "rejected" }), { status: 200 }));
    }));
    const prompt = vi.fn(() => "Copied");
    vi.stubGlobal("prompt", prompt);
    render(<MemoryRouter><CorrectionsTab classAssignmentId={3} /></MemoryRouter>);
    await screen.findByText("#1 Tan · 1b");
    expect(screen.queryByRole("img", { name: "The student's first answer" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(prompt).toHaveBeenCalledWith("Why is this not accepted? (kept for your records — the student sees \"Not accepted — ask your teacher\")");
    await waitFor(() => expect(posted).toEqual([{ path: "/api/corrections/5/reject", body: { reason: "Copied" } }]));
  });

  it("drops a slow answer for a set the teacher has already left", async () => {
    const slow: { resolve: (r: Response) => void } = { resolve: () => {} };
    const other: Correction = { ...row, id: 6, submission_label: "#2 Lim" };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("=3")) return new Promise<Response>((resolve) => { slow.resolve = resolve; });
      if (path.endsWith("=4")) return Promise.resolve(new Response(JSON.stringify([other]), { status: 200 }));
      return Promise.reject(new Error(`Unexpected fetch to ${path}`));
    }));
    const { rerender } = render(<MemoryRouter><CorrectionsTab classAssignmentId={3} /></MemoryRouter>);
    rerender(<MemoryRouter><CorrectionsTab classAssignmentId={4} /></MemoryRouter>);
    await screen.findByText("#2 Lim · 1b");
    await act(async () => { slow.resolve(new Response(JSON.stringify([row]), { status: 200 })); });
    expect(screen.getByText("#2 Lim · 1b")).toBeInTheDocument();
    expect(screen.queryByText("#1 Tan · 1b")).not.toBeInTheDocument();
  });

  it("shows no maximum and bounds nothing when the re-mark failed", async () => {
    const failed: Correction = { ...row, status: "submitted", remark_total: null, remark_max: null, remark_note: null, error: "timed out", teacher_total: 2 };
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify([failed]), { status: 200 }))));
    render(<MemoryRouter><CorrectionsTab classAssignmentId={3} /></MemoryRouter>);
    expect(await screen.findByText("Re-mark failed · mark it yourself: timed out")).toBeInTheDocument();
    expect(screen.getByText("Your mark: 2")).toBeInTheDocument();
    expect(screen.queryByText(/\/ 0/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Override mark")).not.toHaveAttribute("max");
  });
});

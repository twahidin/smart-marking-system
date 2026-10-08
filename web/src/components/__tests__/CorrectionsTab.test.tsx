import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Correction } from "../../api/types";
import { CorrectionsTab } from "../CorrectionsTab";

const row: Correction = { id: 5, submission_id: 9, submission_label: "#1 Tan", reg_no: 1, student_name: "Tan", q_id: "1b", reason: "sign", text: "x^2 = 9", page_id: null,
  status: "remarked", remark_total: 1, remark_max: 1, remark_note: "Marker: B1 earned\nChecker: APPROVE: agree", teacher_total: null, teacher_reason: null, error: null, submitted_at: "2026-10-08T01:00:00Z", released_at: null };

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
    await userEvent.click(screen.getByRole("button", { name: "Accept 1 / 1" }));
    await userEvent.type(screen.getByLabelText("Override mark"), "0.5");
    await userEvent.click(screen.getByRole("button", { name: "Override" }));
    await userEvent.click(screen.getByRole("button", { name: "Release corrections" }));
    await waitFor(() => expect(posted.map((p) => p.path)).toEqual(["/api/corrections/5/accept", "/api/corrections/5/override", "/api/class-assignments/3/release-corrections"]));
    expect(posted[1].body).toEqual({ total: 0.5 });
  });
});

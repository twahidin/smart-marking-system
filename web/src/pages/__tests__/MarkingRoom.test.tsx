import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarkingRoom } from "../MarkingRoom";

const snapshot = {
  counts: { queued: 19, read: 1, mark: 1, check: 1, feedback: 0, done: 9, needs_you: 3, failed: 0 }, started_at: "2026-10-08T01:00:00Z", last_event_id: 40,
  desks: [
    { stage: "read", submission_id: 23, label: "#23 Tan Wei Jie", reg_no: 23, since: "2026-10-08T01:05:00Z" },
    { stage: "mark", submission_id: 17, label: "#17 Nur Aisyah", reg_no: 17, since: "2026-10-08T01:04:00Z" },
    { stage: "check", submission_id: 8, label: "#08 Arjun Pillai", reg_no: 8, since: "2026-10-08T01:06:00Z" },
  ],
};
const thoughts = { reader: [{ at: "2026-10-08T01:05:10Z", q_id: "1b", note: "Hard to read" }], marker: [], checker: [{ at: "2026-10-08T01:06:01Z", q_id: "2a", note: "ESCALATE: crossed-out answer was right" }] };

afterEach(() => vi.unstubAllGlobals());

function setup() {
  vi.stubGlobal("EventSource", undefined);
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })));
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path.startsWith("/api/room")) return Promise.resolve(new Response(JSON.stringify(snapshot), { status: 200 }));
    if (path === "/api/submissions/8/thoughts") return Promise.resolve(new Response(JSON.stringify(thoughts), { status: 200 }));
    return Promise.reject(new Error(`Unexpected fetch to ${path}`));
  }));
  render(<MemoryRouter initialEntries={["/room"]}><Routes><Route element={<Outlet context={{ refreshQueue: () => {} }} />}><Route path="/room" element={<MarkingRoom />} /></Route></Routes></MemoryRouter>);
}

describe("MarkingRoom", () => {
  it("shows the counts, one name tag per desk, and opens the Checker's thoughts", async () => {
    setup();
    await waitFor(() => expect(screen.getByText("The Marking Room")).toBeInTheDocument());
    expect(screen.getByLabelText("Done")).toHaveTextContent("9");
    expect(screen.getByLabelText("Needs you")).toHaveTextContent("3");
    expect(screen.getByRole("button", { name: /Reader · #23 Tan Wei Jie/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Checker · #08 Arjun Pillai/ }));
    await waitFor(() => expect(screen.getByText("ESCALATE: crossed-out answer was right")).toBeInTheDocument());
    expect(screen.getByText("Teachers only")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open script" })).toHaveAttribute("href", "/submissions/8");
  });
});

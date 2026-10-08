import { render, screen, waitFor, within } from "@testing-library/react";
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

interface Options { snapshots?: object[]; reduceMotion?: boolean; eventSource?: unknown }

function setup({ snapshots = [snapshot], reduceMotion = false, eventSource = undefined }: Options = {}) {
  vi.stubGlobal("EventSource", eventSource);
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: reduceMotion, addEventListener() {}, removeEventListener() {} })));
  let roomCalls = 0;
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path.startsWith("/api/room")) return Promise.resolve(new Response(JSON.stringify(snapshots[Math.min(roomCalls++, snapshots.length - 1)]), { status: 200 }));
    if (path === "/api/submissions/8/thoughts") return Promise.resolve(new Response(JSON.stringify(thoughts), { status: 200 }));
    return Promise.reject(new Error(`Unexpected fetch to ${path}`));
  });
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<MemoryRouter initialEntries={["/room"]}><Routes><Route element={<Outlet context={{ refreshQueue: () => {} }} />}><Route path="/room" element={<MarkingRoom />} /></Route></Routes></MemoryRouter>);
  return { fetchMock, ...view };
}

const thoughtCalls = (fetchMock: ReturnType<typeof vi.fn>) => fetchMock.mock.calls.filter((c) => String(c[0]) === "/api/submissions/8/thoughts").length;

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

  it("tags the oldest script at a shared stage with +N and keeps every script reachable in the list", async () => {
    const newer = { stage: "read", submission_id: 31, label: "#31 Mei Lin", reg_no: 31, since: "2026-10-08T01:09:00Z" };
    // newest first in the payload: the tag must still pick the oldest
    setup({ snapshots: [{ ...snapshot, desks: [newer, ...snapshot.desks] }] });
    const tag = await screen.findByRole("button", { name: /^Reader · #23 Tan Wei Jie \+1$/ });
    expect(tag).toHaveTextContent(/\+1$/);
    const list = screen.getByRole("list", { name: "On the desks right now" });
    expect(within(list).getByText("#23 Tan Wei Jie")).toBeInTheDocument();
    expect(within(list).getByText("#31 Mei Lin")).toBeInTheDocument();
    await userEvent.click(within(list).getByRole("button", { name: /#08 Arjun Pillai/ }));
    await waitFor(() => expect(screen.getByText("ESCALATE: crossed-out answer was right")).toBeInTheDocument());
    // the list stays visible under the open panel
    expect(screen.getByRole("list", { name: "On the desks right now" })).toBeInTheDocument();
  });

  it("refetches the open thought panel when the room's last event moves on", async () => {
    let fire: () => void = () => {};
    class FakeSource {
      onerror: (() => void) | null = null;
      constructor() { fire = () => this.listener?.(); }
      listener: (() => void) | null = null;
      addEventListener(_: string, fn: () => void) { this.listener = fn; }
      close() {}
    }
    const { fetchMock } = setup({ snapshots: [snapshot, { ...snapshot, last_event_id: 41 }], eventSource: FakeSource });
    await userEvent.click(await screen.findByRole("button", { name: /Checker · #08 Arjun Pillai/ }));
    await waitFor(() => expect(thoughtCalls(fetchMock)).toBe(1));
    await waitFor(() => expect(typeof fire).toBe("function"));
    fire();
    await waitFor(() => expect(thoughtCalls(fetchMock)).toBe(2));
  });

  it("drops the bobbing and sliding animation classes under reduced motion", async () => {
    const { container } = setup({ reduceMotion: true });
    await screen.findByRole("button", { name: /Reader · #23 Tan Wei Jie/ });
    expect(container.querySelector(".bob")).toBeNull();
    expect(container.querySelector(".slide")).toBeNull();
  });

  it("animates the tags and the paper on the 2d tier", async () => {
    const { container } = setup();
    await screen.findByRole("button", { name: /Reader · #23 Tan Wei Jie/ });
    expect(container.querySelector(".bob")).not.toBeNull();
    expect(container.querySelector(".slide")).not.toBeNull();
  });
});

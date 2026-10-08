import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRoomEvents } from "../useRoomEvents";

class FakeSource {
  static last: FakeSource | null = null;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onerror: null | (() => void) = null;
  closed = false;
  constructor(public url: string) { FakeSource.last = this; }
  addEventListener(type: string, fn: (e: MessageEvent) => void) { (this.listeners[type] ??= []).push(fn); }
  close() { this.closed = true; }
  emit(type: string, data: unknown) { this.listeners[type]?.forEach((f) => f({ data: JSON.stringify(data) } as MessageEvent)); }
}
const snap = (n: number) => ({ counts: { queued: n, read: 0, mark: 0, check: 0, feedback: 0, done: 0, needs_you: 0, failed: 0 }, started_at: null, desks: [], last_event_id: 7 });

afterEach(() => vi.unstubAllGlobals());

describe("useRoomEvents", () => {
  it("loads the snapshot, subscribes after the last event, and reloads on a stage event", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(snap(++calls)), { status: 200 }))));
    vi.stubGlobal("EventSource", FakeSource);
    const { result } = renderHook(() => useRoomEvents(null));
    await waitFor(() => expect(result.current.snapshot?.counts.queued).toBe(1));
    expect(FakeSource.last!.url).toBe("/api/room/events?after=7");
    act(() => FakeSource.last!.emit("stage", { id: 8, submission_id: 1, stage: "read", kind: "started", created_at: "" }));
    await waitFor(() => expect(result.current.snapshot?.counts.queued).toBe(2));
    expect(result.current.live).toBe(true);
  });

  it("falls back to polling after three stream errors", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(snap(1)), { status: 200 }))));
    vi.stubGlobal("EventSource", FakeSource);
    const { result } = renderHook(() => useRoomEvents(3));
    await act(async () => { await Promise.resolve(); });
    expect(FakeSource.last!.url).toContain("class_assignment_id=3");
    act(() => { for (let i = 0; i < 3; i++) FakeSource.last!.onerror?.(); });
    expect(FakeSource.last!.closed).toBe(true);
    await act(async () => { vi.advanceTimersByTime(5000); await Promise.resolve(); });
    expect(result.current.live).toBe(false);
    expect((fetch as unknown as { mock: { calls: unknown[] } }).mock.calls.length).toBeGreaterThanOrEqual(2);
    vi.useRealTimers();
  });
});

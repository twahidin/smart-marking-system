import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRoomEvents } from "../useRoomEvents";

class FakeSource {
  static last: FakeSource | null = null;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onerror: null | (() => void) = null;
  onopen: null | (() => void) = null;
  closed = false;
  constructor(public url: string) { FakeSource.last = this; }
  addEventListener(type: string, fn: (e: MessageEvent) => void) { (this.listeners[type] ??= []).push(fn); }
  close() { this.closed = true; }
  emit(type: string, data: unknown) { this.listeners[type]?.forEach((f) => f({ data: JSON.stringify(data) } as MessageEvent)); }
}
const snap = (n: number) => ({ counts: { queued: n, read: 0, mark: 0, check: 0, feedback: 0, done: 0, needs_you: 0, failed: 0 }, started_at: null, desks: [], last_event_id: 7 });

beforeEach(() => { FakeSource.last = null; });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
const okResponse = (n: number) => new Response(JSON.stringify(snap(n)), { status: 200 });

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
  });

  it("counts only consecutive errors: an open or a stage message resets the count", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(okResponse(1))));
    vi.stubGlobal("EventSource", FakeSource);
    const { result } = renderHook(() => useRoomEvents(null));
    await waitFor(() => expect(FakeSource.last).not.toBeNull());
    const source = FakeSource.last!;
    act(() => { source.onerror?.(); source.onerror?.(); source.onopen?.(); source.onerror?.(); source.onerror?.(); });
    expect(source.closed).toBe(false);
    act(() => { source.emit("stage", {}); source.onerror?.(); source.onerror?.(); });
    expect(source.closed).toBe(false);
    expect(result.current.live).toBe(true);
    act(() => { source.onerror?.(); });
    expect(source.closed).toBe(true);
  });

  it("closes the source and clears its timers on unmount", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => Promise.resolve(okResponse(1)));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("EventSource", FakeSource);
    const { unmount } = renderHook(() => useRoomEvents(null));
    await act(async () => { await Promise.resolve(); });
    const source = FakeSource.last!;
    act(() => source.emit("stage", {}));   // arms the debounce
    unmount();
    expect(source.closed).toBe(true);
    await act(async () => { vi.advanceTimersByTime(10_000); await Promise.resolve(); });
    expect(fetchMock).toHaveBeenCalledTimes(1);   // the pending debounce never fired
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears the poll timer on unmount", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(okResponse(1))));
    vi.stubGlobal("EventSource", FakeSource);
    const { unmount } = renderHook(() => useRoomEvents(null));
    await act(async () => { await Promise.resolve(); });
    act(() => { for (let i = 0; i < 3; i++) FakeSource.last!.onerror?.(); });
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("on a scope change closes the old source, opens a new one, and ignores a stale fetch", async () => {
    let resolveStale!: (r: Response) => void;
    const fetchMock = vi.fn((url: string) => url.includes("class_assignment_id=1")
      ? new Promise<Response>((res) => { resolveStale = res; })
      : Promise.resolve(okResponse(2)));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("EventSource", FakeSource);
    const { result, rerender } = renderHook(({ id }) => useRoomEvents(id), { initialProps: { id: 1 as number | null } });
    rerender({ id: 2 });
    await waitFor(() => expect(result.current.snapshot?.counts.queued).toBe(2));
    expect(FakeSource.last!.url).toBe("/api/room/events?after=7&class_assignment_id=2");
    await act(async () => { resolveStale(okResponse(99)); await Promise.resolve(); });
    expect(result.current.snapshot?.counts.queued).toBe(2);
    expect(FakeSource.last!.url).toContain("class_assignment_id=2");   // the stale load opened no source
  });

  it("closes the old source when the scope changes after it was open", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(okResponse(1))));
    vi.stubGlobal("EventSource", FakeSource);
    const { result, rerender } = renderHook(({ id }) => useRoomEvents(id), { initialProps: { id: 1 as number | null } });
    await waitFor(() => expect(FakeSource.last).not.toBeNull());
    const first = FakeSource.last!;
    rerender({ id: 2 });
    expect(first.closed).toBe(true);
    await waitFor(() => expect(FakeSource.last).not.toBe(first));
    expect(FakeSource.last!.url).toContain("class_assignment_id=2");
    expect(result.current.live).toBe(true);
  });

  it("debounces two stage events within 300 ms into one reload", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => Promise.resolve(okResponse(1)));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("EventSource", FakeSource);
    renderHook(() => useRoomEvents(null));
    await act(async () => { await Promise.resolve(); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    act(() => FakeSource.last!.emit("stage", {}));
    await act(async () => { vi.advanceTimersByTime(100); });
    act(() => FakeSource.last!.emit("stage", {}));
    await act(async () => { vi.advanceTimersByTime(299); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(1); await Promise.resolve(); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("polls (live false) when the first load fails, and recovers when the server returns", async () => {
    vi.useFakeTimers();
    let up = false;
    const fetchMock = vi.fn(() => Promise.resolve(up ? okResponse(5) : new Response("boom", { status: 500 })));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("EventSource", FakeSource);
    const { result } = renderHook(() => useRoomEvents(null));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(result.current.live).toBe(false);
    expect(result.current.error).toBeTruthy();
    expect(result.current.snapshot).toBeNull();
    expect(FakeSource.last).toBeNull();
    up = true;
    await act(async () => { vi.advanceTimersByTime(5000); await Promise.resolve(); await Promise.resolve(); });
    expect(result.current.snapshot?.counts.queued).toBe(5);
    expect(result.current.error).toBeNull();
  });
});

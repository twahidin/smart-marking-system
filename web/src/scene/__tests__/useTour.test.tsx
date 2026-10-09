import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTour } from "../useTour";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useTour", () => {
  it("walks every hotspot once at 3 s each, then stops", () => {
    const { result } = renderHook(() => useTour(3));
    expect(result.current.running).toBe(false);
    act(() => result.current.toggle());
    expect(result.current).toMatchObject({ running: true, index: 0 });
    act(() => { vi.advanceTimersByTime(3000); });
    expect(result.current.index).toBe(1);
    act(() => { vi.advanceTimersByTime(3000); });
    expect(result.current.index).toBe(2);
    act(() => { vi.advanceTimersByTime(3000); });
    expect(result.current).toMatchObject({ running: false, index: -1 });
  });

  it("stops early on a second toggle and clears its timer on unmount", () => {
    const { result, unmount } = renderHook(() => useTour(4));
    act(() => result.current.toggle());
    act(() => result.current.toggle());
    expect(result.current.running).toBe(false);
    act(() => result.current.toggle());
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});

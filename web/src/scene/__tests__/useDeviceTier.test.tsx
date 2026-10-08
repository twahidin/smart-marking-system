import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useDeviceTier } from "../useDeviceTier";

afterEach(() => vi.unstubAllGlobals());
const mm = (reduce: boolean) => vi.stubGlobal("matchMedia", vi.fn((q: string) => ({ matches: q.includes("reduce") && reduce, addEventListener() {}, removeEventListener() {} })));

describe("useDeviceTier", () => {
  it("is 2d by default and static under reduced motion", () => {
    mm(false); expect(renderHook(() => useDeviceTier()).result.current).toBe("2d");
    mm(true); expect(renderHook(() => useDeviceTier()).result.current).toBe("static");
  });
});

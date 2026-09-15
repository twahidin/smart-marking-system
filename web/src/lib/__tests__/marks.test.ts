import { describe, expect, it } from "vitest";
import { statusLabel, totalLabel } from "../marks";

describe("marks", () => {
  it("formats totals and ranges", () => {
    expect(totalLabel({ total: 18, total_upper: 18, total_max: 25 })).toBe("18 / 25");
    expect(totalLabel({ total: 15, total_upper: 17, total_max: 25 })).toBe("15–17 / 25");
    expect(totalLabel(null)).toBe("—");
  });
  it("labels statuses in plain words", () => {
    expect(statusLabel("needs_you", ["q3"])).toBe("Needs you · Q3");
    expect(statusLabel("marking", [])).toBe("Marking");
    expect(statusLabel("done", [])).toBe("Done");
  });
});

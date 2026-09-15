import { describe, expect, it } from "vitest";
import { emptyRow, jsonToRows, rowsToRubricJson, rubricTotal, validateRows } from "../rubric";

describe("rubric", () => {
  it("round-trips rows and json", () => {
    const rows = [{ id: "c1", description: "Method", max_score: 2 }, { id: "c2", description: "Answer", max_score: 3 }];
    const json = rowsToRubricJson(rows);
    expect(JSON.parse(json)).toEqual({ criterion_defs: rows });
    expect(jsonToRows(json)).toEqual(rows);
  });
  it("assigns ids when blank and totals", () => {
    const rows = [{ ...emptyRow(), description: "A", max_score: 4 }, { ...emptyRow(), description: "B", max_score: 1 }];
    expect(JSON.parse(rowsToRubricJson(rows)).criterion_defs.map((c: any) => c.id)).toEqual(["c1", "c2"]);
    expect(rubricTotal(rows)).toBe(5);
  });
  it("validates", () => {
    expect(validateRows([])).toMatch(/at least one/);
    expect(validateRows([{ id: "", description: "", max_score: 1 }])).toMatch(/description/i);
    expect(validateRows([{ id: "", description: "x", max_score: 0 }])).toMatch(/marks/i);
    expect(validateRows([{ id: "", description: "x", max_score: 2 }])).toBeNull();
  });
  it("rejects bad json", () => {
    expect(() => jsonToRows("{}")).toThrow();
  });
});

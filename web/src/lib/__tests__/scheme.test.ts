import { describe, expect, it } from "vitest";
import type { MarkSchemeEntry, Question, RubricBands } from "../../api/types";
import {
  bestBand, orphanRows, placeholderRubric, qLabel, rowTotal, schemeTotal, unmatchedQuestions, validateTemplate,
} from "../scheme";

const q = (q_id: string, max_marks = 2, text = ""): Question => ({ q_id, text, max_marks });
const row = (q_id: string, marks: [string, number][] = [["M1", 1], ["A1", 1]]): MarkSchemeEntry =>
  ({ q_id, answer: "x = 2", marks: marks.map(([label, m]) => ({ label, marks: m })), notes: "" });
const crit = (criterion: string, bands: [string, number][] = [["A", 5], ["B", 3]]): RubricBands =>
  ({ criterion, bands: bands.map(([band, marks]) => ({ band, marks, descriptor: "" })) });
const criteria = [{ id: "c1", description: "Method", max_score: 2 }];

describe("qLabel", () => {
  it("formats question ids the way the paper prints them", () => {
    expect(qLabel("1a")).toBe("1(a)");
    expect(qLabel("2bii")).toBe("2(b)(ii)");
    expect(qLabel("4iii")).toBe("4(iii)");
    expect(qLabel("q1")).toBe("Q1");
    expect(qLabel("7")).toBe("7");
    expect(qLabel(" 3(c) ")).toBe("3(c)");
    expect(qLabel("")).toBe("");
  });
});

describe("totals", () => {
  it("adds a row's allocations and a criterion's best band", () => {
    expect(rowTotal(row("1a", [["M1", 1], ["A1", 2]]))).toBe(3);
    expect(rowTotal(row("1a", []))).toBe(0);
    expect(bestBand(crit("Organisation", [["A", 5], ["B", 3]]))).toBe(5);
    expect(bestBand(crit("Organisation", []))).toBe(0);
  });

  it("mark scheme total uses each question's row, falling back to the paper's marks", () => {
    expect(schemeTotal("mark_scheme", [q("1a", 2), q("1b", 4)], [row("1a", [["M1", 1], ["A1", 2]])])).toBe(3 + 4);
    expect(schemeTotal("mark_scheme", [], [row("1a"), row("1b")])).toBe(4);
  });

  it("rubric total is the best band of every criterion; criteria total is the paper's marks", () => {
    expect(schemeTotal("rubric", [], [crit("A", [["1", 1], ["2", 6]]), crit("B", [["x", 4]])])).toBe(10);
    expect(schemeTotal("criteria", [q("1", 3), q("2", 5)], [])).toBe(8);
  });
});

describe("matching", () => {
  it("lists questions without a scheme row and rows without a question", () => {
    const qs = [q("1a"), q("1b"), q("2")];
    const rows = [row("1a"), row("2"), row("3c")];
    expect(unmatchedQuestions(qs, rows)).toEqual(["1b"]);
    expect(orphanRows(qs, rows)).toEqual([2]);
  });

  it("ignores surrounding whitespace in ids", () => {
    expect(unmatchedQuestions([q(" 1a ")], [row("1a")])).toEqual([]);
  });
});

describe("validateTemplate", () => {
  it("mark scheme: needs a question, unique ids, whole-number marks and a row for every question", () => {
    expect(validateTemplate("mark_scheme", [], [], criteria)).toBe("Add at least one question.");
    expect(validateTemplate("mark_scheme", [q("")], [], criteria)).toBe("Every question needs an id, like 1a.");
    expect(validateTemplate("mark_scheme", [q("1a"), q("1a")], [], criteria)).toBe("Question ids must be unique — 1(a) appears twice.");
    expect(validateTemplate("mark_scheme", [q("1a", 1.5)], [], criteria)).toBe("Marks for 1(a) must be a whole number of 0 or more.");
    expect(validateTemplate("mark_scheme", [q("1a"), q("1b")], [row("1a")], criteria)).toBe("Add a scheme row for 1(b).");
    expect(validateTemplate("mark_scheme", [q("1a"), q("1b"), q("2")], [], criteria)).toBe("Add scheme rows for 1(a), 1(b) and 2.");
    expect(validateTemplate("mark_scheme", [q("1"), q("2"), q("3"), q("4"), q("5")], [], criteria)).toBe("Add scheme rows for 1, 2, 3 and 2 more.");
    expect(validateTemplate("mark_scheme", [q("1a")], [row("1a", [["", 1]])], criteria)).toBe("Every allocation for 1(a) needs a label, like M1.");
    expect(validateTemplate("mark_scheme", [q("1a")], [row("1a", [["M1", -1]])], criteria)).toBe("Allocation marks for 1(a) must be a whole number of 0 or more.");
    expect(validateTemplate("mark_scheme", [q("1a")], [row("1a"), row("")], criteria)).toBe("Every scheme row needs a question id.");
    expect(validateTemplate("mark_scheme", [q("1a")], [row("1a")], criteria)).toBeNull();
    // A row for a question that is not on the paper is flagged in the table but does not block saving.
    expect(validateTemplate("mark_scheme", [q("1a")], [row("1a"), row("9")], criteria)).toBeNull();
  });

  it("rubric: needs a criterion with a named band; questions are optional but checked when present", () => {
    expect(validateTemplate("rubric", [], [], criteria)).toBe("Add at least one criterion.");
    expect(validateTemplate("rubric", [], [crit("  ")], criteria)).toBe("Every criterion needs a name.");
    expect(validateTemplate("rubric", [], [crit("Organisation", [])], criteria)).toBe("Add at least one band to Organisation.");
    expect(validateTemplate("rubric", [], [crit("Organisation", [["", 3]])], criteria)).toBe("Every band for Organisation needs a name.");
    expect(validateTemplate("rubric", [], [crit("Organisation", [["A", 2.5]])], criteria)).toBe("Band marks for Organisation must be a whole number of 0 or more.");
    expect(validateTemplate("rubric", [q("")], [crit("Organisation")], criteria)).toBe("Every question needs an id, like 1a.");
    expect(validateTemplate("rubric", [q("1")], [crit("Organisation")], criteria)).toBeNull();
    expect(validateTemplate("rubric", [], [crit("Organisation")], criteria)).toBeNull();
  });

  it("quick mark: uses the criteria table rules", () => {
    expect(validateTemplate("criteria", [], [], [])).toBe("Add at least one criterion.");
    expect(validateTemplate("criteria", [], [], [{ id: "c1", description: " ", max_score: 2 }])).toBe("Every criterion needs a description.");
    expect(validateTemplate("criteria", [], [], criteria)).toBeNull();
  });
});

describe("placeholderRubric", () => {
  it("mark scheme: one criterion per question worth its scheme row (or the paper's marks)", () => {
    const r = placeholderRubric("mark_scheme", [q("1a", 2, "Solve for x"), q("1b", 4)], [row("1a", [["M1", 1], ["A1", 2]])], criteria);
    expect(r.criterion_defs).toEqual([
      { id: "1a", description: "Solve for x", max_score: 3 },
      { id: "1b", description: "1(b)", max_score: 4 },
    ]);
  });

  it("rubric: one criterion per rubric criterion worth its best band", () => {
    const r = placeholderRubric("rubric", [], [crit("Organisation", [["A", 5], ["B", 3]]), crit("Grammar", [["A", 4]])], criteria);
    expect(r.criterion_defs).toEqual([
      { id: "organisation", description: "Organisation", max_score: 5 },
      { id: "grammar", description: "Grammar", max_score: 4 },
    ]);
  });

  it("quick mark keeps the criteria as typed; an empty scheme yields a zero-mark draft criterion", () => {
    expect(placeholderRubric("criteria", [], [], [{ id: "", description: "Method", max_score: 2 }]).criterion_defs)
      .toEqual([{ id: "c1", description: "Method", max_score: 2 }]);
    expect(placeholderRubric("mark_scheme", [], [], []).criterion_defs).toEqual([{ id: "draft", description: "Draft", max_score: 0 }]);
  });

  it("keeps ids unique when two criteria share a name", () => {
    const r = placeholderRubric("rubric", [], [crit("Style"), crit("Style")], criteria);
    expect(r.criterion_defs.map((c) => c.id)).toEqual(["style", "style-2"]);
  });
});

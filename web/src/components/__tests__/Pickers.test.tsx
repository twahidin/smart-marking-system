import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { Band, MarkPoint } from "../../api/types";
import { AllocationPicker, toggleAllocation } from "../AllocationPicker";
import { BandPicker } from "../BandPicker";

const marks: MarkPoint[] = [{ label: "M1", marks: 1 }, { label: "A1", marks: 2 }, { label: "B1", marks: 1 }];
const bands: Band[] = [{ band: "A", marks: 5, descriptor: "Fluent and precise" }, { band: "B", marks: 3, descriptor: "Mostly clear" }, { band: "C", marks: 1, descriptor: "Hard to follow" }];

function Alloc({ initial = [] as string[] }) {
  const [got, setGot] = useState<string[]>(initial);
  return <AllocationPicker marks={marks} got={got} onChange={setGot} />;
}
function Bands({ initial = null as string | null }) {
  const [band, setBand] = useState<string | null>(initial);
  return <BandPicker bands={bands} value={band} onChange={setBand} />;
}

describe("AllocationPicker", () => {
  it("gives each allocation a mark box and keeps a running total against the row's max", async () => {
    render(<Alloc />);
    const total = screen.getByLabelText("Your mark");
    expect(total).toHaveTextContent("0 / 4");
    const m1 = screen.getByRole("spinbutton", { name: "M1 · your mark out of 1" });
    const a1 = screen.getByRole("spinbutton", { name: "A1 · your mark out of 2" });
    expect(m1).toHaveValue(0);
    await userEvent.type(m1, "1");
    await userEvent.type(a1, "2");
    expect(total).toHaveTextContent("3 / 4");
    await userEvent.type(m1, "0");
    expect(total).toHaveTextContent("2 / 4");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("caps a box at its allocation and refuses a part-mark on an all-or-nothing allocation", async () => {
    render(<Alloc />);
    const m1 = screen.getByRole("spinbutton", { name: "M1 · your mark out of 1" });
    await userEvent.type(m1, "5");
    expect(m1).toHaveValue(1);
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("1 / 4");
    const a1 = screen.getByRole("spinbutton", { name: "A1 · your mark out of 2" });
    await userEvent.type(a1, "1");
    expect(screen.getByRole("alert")).toHaveTextContent("A1 is all or nothing — give 0 or 2.");
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("1 / 4");
    await userEvent.tab();
    expect(a1).toHaveValue(0);
  });

  it("toggleAllocation flips the nth allocation for the digit keys", () => {
    expect(toggleAllocation(marks, [], 1)).toEqual(["M1"]);
    expect(toggleAllocation(marks, ["M1"], 1)).toEqual([]);
    expect(toggleAllocation(marks, ["M1"], 3)).toEqual(["M1", "B1"]);
    // A digit past the last allocation changes nothing.
    expect(toggleAllocation(marks, ["M1"], 4)).toEqual(["M1"]);
  });

  it("with nothing to tick, takes the mark as a number capped at the part's max", async () => {
    const seen: number[] = [];
    render(<AllocationPicker marks={[]} got={[]} onChange={() => {}} total={null} onTotal={(n) => seen.push(n)} max={2} />);
    expect(screen.getByText(/no allocations/i)).toBeInTheDocument();
    const input = screen.getByRole("spinbutton", { name: "Your mark" });
    expect(input).toHaveAttribute("max", "2");
    await userEvent.type(input, "1");
    expect(seen.at(-1)).toBe(1);
  });

  it("shows the proposed mark per allocation and marks the rows where yours differs", () => {
    render(<AllocationPicker marks={marks} got={["M1", "A1"]} onChange={() => {}} proposed={[{ label: "M1", marks: 1, got: true }, { label: "A1", marks: 2, got: false }]} />);
    expect(screen.getByRole("note")).toHaveTextContent("Each mark starts at the marker’s proposal");
    const rows = screen.getAllByRole("row");
    expect(rows[1].children[1]).toHaveTextContent("1");
    expect(rows[2].children[1]).toHaveTextContent("0");
    expect(rows[1]).not.toHaveClass("changed");
    expect(rows[2]).toHaveClass("changed");
    expect(screen.getByRole("spinbutton", { name: "A1 · your mark out of 2" })).toHaveValue(2);
  });
});

describe("BandPicker", () => {
  it("with no bands (criterion not in the rubric) offers the proposed band or 0 and says why", async () => {
    const seen: [string, number | undefined][] = [];
    render(<BandPicker bands={[]} value={null} onChange={(b, m) => seen.push([b, m])} proposed="B" proposedMarks={3} />);
    expect(screen.getByText(/This criterion is not in the rubric/)).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    await userEvent.click(screen.getByRole("radio", { name: /Band B · 3 marks/ }));
    await userEvent.click(screen.getByRole("radio", { name: /Award 0/ }));
    expect(seen).toEqual([["B", undefined], ["B", 0]]);
  });

  it("picks one band by radio, showing marks and descriptors, and totals it", async () => {
    render(<Bands />);
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("— / 5");
    expect(screen.getByText("Fluent and precise")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Band B/ }));
    expect(screen.getByRole("radio", { name: /Band B/ })).toBeChecked();
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("3 / 5");
    await userEvent.click(screen.getByRole("radio", { name: /Band C/ }));
    expect(screen.getByRole("radio", { name: /Band B/ })).not.toBeChecked();
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("1 / 5");
  });
});

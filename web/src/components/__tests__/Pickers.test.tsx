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
  it("toggles allocations by click and keeps a running total against the row's max", async () => {
    render(<Alloc />);
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("0 / 4");
    await userEvent.click(screen.getByRole("checkbox", { name: "M1 · 1 mark" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "A1 · 2 marks" }));
    expect(screen.getByRole("checkbox", { name: "M1 · 1 mark" })).toBeChecked();
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("3 / 4");
    await userEvent.click(screen.getByRole("checkbox", { name: "M1 · 1 mark" }));
    expect(screen.getByLabelText("Your mark")).toHaveTextContent("2 / 4");
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
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText(/no allocations to tick/i)).toBeInTheDocument();
    const input = screen.getByRole("spinbutton", { name: "Your mark" });
    expect(input).toHaveAttribute("max", "2");
    await userEvent.type(input, "1");
    expect(seen).toEqual([1]);
  });

  it("shows the proposed decision per allocation", () => {
    render(<AllocationPicker marks={marks} got={["M1"]} onChange={() => {}} proposed={[{ label: "M1", marks: 1, got: true }, { label: "A1", marks: 2, got: false }]} />);
    const rows = screen.getAllByRole("row");
    expect(rows[1]).toHaveTextContent("✓");
    expect(rows[2]).toHaveTextContent("✗");
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

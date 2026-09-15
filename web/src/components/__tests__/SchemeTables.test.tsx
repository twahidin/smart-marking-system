import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { MarkSchemeEntry, Question, RubricBands } from "../../api/types";
import { MarkSchemeTable } from "../MarkSchemeTable";
import { QuestionsTable } from "../QuestionsTable";
import { RubricTable } from "../RubricTable";

const questions: Question[] = [{ q_id: "1a", text: "Solve 2x + 3 = 7", max_marks: 2 }, { q_id: "1b", text: "Hence find y", max_marks: 3 }];

function Questions({ initial }: { initial: Question[] }) {
  const [rows, setRows] = useState(initial);
  return <QuestionsTable rows={rows} onChange={setRows} />;
}
function Scheme({ initial, qs = questions }: { initial: MarkSchemeEntry[]; qs?: Question[] }) {
  const [rows, setRows] = useState(initial);
  return <MarkSchemeTable questions={qs} rows={rows} onChange={setRows} />;
}
function Rubric({ initial }: { initial: RubricBands[] }) {
  const [rows, setRows] = useState(initial);
  return <RubricTable rows={rows} onChange={setRows} />;
}

describe("QuestionsTable", () => {
  it("shows labels and the total, and adds, moves and removes questions", async () => {
    render(<Questions initial={questions} />);
    expect(screen.getByText("1(a)")).toBeInTheDocument();
    expect(screen.getByLabelText("Total marks")).toHaveTextContent("5");
    await userEvent.click(screen.getByRole("button", { name: "+ Add question" }));
    expect(screen.getAllByLabelText(/Question \d id/)).toHaveLength(3);
    await userEvent.type(screen.getByLabelText("Question 3 id"), "2");
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByLabelText("Total marks")).toHaveTextContent("6");
    await userEvent.click(screen.getByRole("button", { name: "Move question 3 up" }));
    expect(screen.getByLabelText("Question 2 id")).toHaveValue("2");
    await userEvent.click(screen.getByRole("button", { name: "Remove question 1" }));
    expect(screen.getAllByLabelText(/Question \d id/)).toHaveLength(2);
    expect(screen.getByLabelText("Question 1 id")).toHaveValue("2");
  });
});

describe("MarkSchemeTable", () => {
  it("flags questions without a row and rows without a question; adds and removes rows and allocations", async () => {
    render(<Scheme initial={[{ q_id: "1a", answer: "x = 2", marks: [{ label: "M1", marks: 1 }, { label: "A1", marks: 1 }], notes: "" }, { q_id: "9", answer: "", marks: [], notes: "" }]} />);
    expect(screen.getByText("No scheme row for 1(b)")).toBeInTheDocument();
    expect(screen.getByText("No question 9 on the paper")).toBeInTheDocument();
    expect(screen.getByLabelText("Total for 1(a)")).toHaveTextContent("2");
    // total = row for 1(a) + the paper's marks for 1(b); the orphan row does not count
    expect(screen.getByLabelText("Scheme total")).toHaveTextContent("5");

    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    expect(screen.queryByText("No scheme row for 1(b)")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Scheme row 2 question id")).toHaveValue("1b");

    await userEvent.click(screen.getByRole("button", { name: "Add allocation for 1(b)" }));
    const chips = screen.getByLabelText("Allocations for 1(b)");
    await userEvent.type(within(chips).getByLabelText("Allocation 1 label for 1(b)"), "B1");
    await userEvent.clear(within(chips).getByLabelText("Allocation 1 marks for 1(b)"));
    await userEvent.type(within(chips).getByLabelText("Allocation 1 marks for 1(b)"), "3");
    expect(screen.getByLabelText("Total for 1(b)")).toHaveTextContent("3");
    expect(screen.getByLabelText("Scheme total")).toHaveTextContent("5");

    await userEvent.click(screen.getByRole("button", { name: "Remove allocation 2 for 1(a)" }));
    expect(screen.getByLabelText("Total for 1(a)")).toHaveTextContent("1");

    await userEvent.click(screen.getByRole("button", { name: "Remove scheme row 3" }));
    expect(screen.queryByText("No question 9 on the paper")).not.toBeInTheDocument();
  });
});

describe("disabled tables", () => {
  it("lock every input and button while the pages are being read", () => {
    render(
      <>
        <QuestionsTable rows={questions} onChange={() => {}} disabled />
        <MarkSchemeTable questions={questions} rows={[{ q_id: "1a", answer: "", marks: [{ label: "M1", marks: 1 }], notes: "" }]} onChange={() => {}} disabled />
        <RubricTable rows={[{ criterion: "Organisation", bands: [{ band: "A", marks: 5, descriptor: "" }] }]} onChange={() => {}} disabled />
      </>,
    );
    for (const el of [...screen.getAllByRole("textbox"), ...screen.getAllByRole("spinbutton"), ...screen.getAllByRole("button")]) expect(el).toBeDisabled();
    expect(screen.getAllByRole("table", { busy: true }).length).toBeGreaterThanOrEqual(3);
  });

  it("MarkSchemeTable names a second blank-id row plainly", () => {
    render(<MarkSchemeTable questions={[{ q_id: "", text: "", max_marks: 1 }]} rows={[{ q_id: "", answer: "", marks: [], notes: "" }, { q_id: " ", answer: "", marks: [], notes: "" }]} onChange={() => {}} />);
    expect(screen.getByText("Second row with no question id")).toBeInTheDocument();
  });
});

describe("RubricTable", () => {
  it("adds and removes criteria and bands, and totals the best band of each criterion", async () => {
    render(<Rubric initial={[{ criterion: "Organisation", bands: [{ band: "A", marks: 5, descriptor: "" }, { band: "B", marks: 3, descriptor: "" }] }]} />);
    expect(screen.getByLabelText("Max marks for Organisation")).toHaveTextContent("5");
    expect(screen.getByLabelText("Rubric total")).toHaveTextContent("5");
    await userEvent.click(screen.getByRole("button", { name: "+ Add criterion" }));
    await userEvent.type(screen.getByLabelText("Criterion 2 name"), "Grammar");
    await userEvent.clear(screen.getByLabelText("Band 1 marks for Grammar"));
    await userEvent.type(screen.getByLabelText("Band 1 marks for Grammar"), "4");
    expect(screen.getByLabelText("Rubric total")).toHaveTextContent("9");
    await userEvent.click(screen.getByRole("button", { name: "Add band for Grammar" }));
    expect(within(screen.getByLabelText("Bands for Grammar")).getAllByLabelText(/Band \d name/)).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Remove band 1 for Organisation" }));
    expect(screen.getByLabelText("Max marks for Organisation")).toHaveTextContent("3");
    await userEvent.click(screen.getByRole("button", { name: "Remove criterion 1" }));
    expect(screen.queryByLabelText("Bands for Organisation")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Rubric total")).toHaveTextContent("4");
  });
});

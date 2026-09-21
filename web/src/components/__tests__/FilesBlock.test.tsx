import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { SubmissionFile } from "../../api/types";
import { FilesBlock } from "../FilesBlock";

const file = (over: Partial<SubmissionFile> = {}): SubmissionFile => ({
  id: 1, name: "prog.py", kind: "py", size: 1234, text_rendered: null, deleted: false, matched: true, ...over,
});

describe("FilesBlock", () => {
  it("names every file with its kind and size", () => {
    render(<FilesBlock files={[file(), file({ id: 2, name: "game.sb3", kind: "sb3", size: 2 * 1024 * 1024 }), file({ id: 3, name: "budget.xlsx", kind: "xlsx", size: 512 })]} />);
    const rows = within(screen.getByRole("list", { name: "Files" })).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("prog.py");
    expect(rows[0]).toHaveTextContent("Python");
    expect(rows[0]).toHaveTextContent("1.2 KB");
    expect(rows[1]).toHaveTextContent("Scratch");
    expect(rows[1]).toHaveTextContent("2.0 MB");
    expect(rows[2]).toHaveTextContent("Excel");
    expect(rows[2]).toHaveTextContent("512 B");
  });

  it("expands what the marker read, and only where there is something to read", async () => {
    render(<FilesBlock files={[file({ text_rendered: "1  print(1)\n2  print(2)" }), file({ id: 2, name: "game.sb3", kind: "sb3" })]} />);
    expect(screen.getAllByRole("button", { name: "Show text" })).toHaveLength(1);
    expect(screen.queryByText(/print\(1\)/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show text" }));
    const pre = document.querySelector("pre");
    expect(pre).toHaveTextContent("print(1)");
    await userEvent.click(screen.getByRole("button", { name: "Hide text" }));
    expect(document.querySelector("pre")).toBeNull();
  });

  it("says when a file was never used and when its bytes are gone", () => {
    render(<FilesBlock files={[file({ matched: false }), file({ id: 2, name: "game.sb3", kind: "sb3", deleted: true })]} />);
    const rows = within(screen.getByRole("list", { name: "Files" })).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Not used for any part");
    expect(rows[0]).not.toHaveTextContent("Deleted after marking");
    expect(rows[1]).toHaveTextContent("Deleted after marking");
  });

  it("stays quiet about a file nothing has decided on yet", () => {
    // `matched: null` is "no marking run yet", which is not the same as "not used for any part".
    render(<FilesBlock files={[file({ matched: null })]} />);
    expect(screen.queryByText("Not used for any part")).not.toBeInTheDocument();
  });

  it("separates the note from the size instead of running them together", () => {
    render(<FilesBlock files={[file({ size: 95, matched: false })]} />);
    const row = within(screen.getByRole("list", { name: "Files" })).getAllByRole("listitem")[0];
    expect(row.textContent).toContain("95 B · Not used for any part");
  });
});

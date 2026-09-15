import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SubmissionRow } from "../../api/types";
import { Submissions } from "../Submissions";

const row = (id: number, label: string, status: SubmissionRow["status"]): SubmissionRow => ({
  id, label, subject: "math", page_count: 2, status, created_at: "2026-09-15T03:04:05Z",
  total: status === "done" ? 7 : null, total_upper: status === "done" ? 7 : null, total_max: status === "done" ? 9 : null,
  needs_you_qids: status === "needs_you" ? ["1b"] : [], assignment_id: 3, assignment_title: "Quadratics — Worksheet 3",
});
const rows = [row(1, "Tan Wei Ling", "done"), row(2, "Lim Jun Hao", "needs_you"), row(3, "Nur Aisyah", "marking"), row(4, "Ravi", "failed")];

afterEach(() => vi.unstubAllGlobals());

function setup() {
  const zips: { ids: number[] }[] = [];
  const saved: string[] = [];
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/submissions") return Promise.resolve(new Response(JSON.stringify(rows), { status: 200 }));
    if (path === "/api/submissions/records.zip") { zips.push(JSON.parse(String(init!.body))); return Promise.resolve(new Response(new Blob(["zip"]), { status: 200 })); }
    return Promise.reject(new Error(`Unexpected fetch to ${path}`));
  }));
  vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:zip"), revokeObjectURL: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { saved.push(this.download); });
  render(<MemoryRouter><Submissions /></MemoryRouter>);
  return { zips, saved, click };
}

describe("Submissions — download marking records", () => {
  it("with nothing ticked downloads every marked script shown and names how many were skipped", async () => {
    const { zips, saved, click } = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Download marking records" }));
    await vi.waitFor(() => expect(zips).toHaveLength(1));
    expect(zips[0]).toEqual({ ids: [1, 2] });
    expect(saved).toEqual(["marking-records.zip"]);
    expect(await screen.findByRole("alert")).toHaveTextContent("2 scripts were skipped — not marked yet.");
    click.mockRestore();
  });

  it("with scripts ticked downloads only those, skipping unmarked ones", async () => {
    const { zips, click } = setup();
    await userEvent.click(await screen.findByRole("checkbox", { name: "Select Lim Jun Hao" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Select Nur Aisyah" }));
    await userEvent.click(screen.getByRole("button", { name: "Download marking records (1 of 2)" }));
    await vi.waitFor(() => expect(zips).toHaveLength(1));
    expect(zips[0]).toEqual({ ids: [2] });
    expect(await screen.findByRole("alert")).toHaveTextContent("1 script was skipped — not marked yet.");
    click.mockRestore();
  });

  it("disables the button when only unmarked scripts are ticked", async () => {
    const { click } = setup();
    await userEvent.click(await screen.findByRole("checkbox", { name: "Select Ravi" }));
    expect(screen.getByRole("button", { name: "Download marking records (0 of 1)" })).toBeDisabled();
    expect(screen.getAllByText("Quadratics — Worksheet 3")).toHaveLength(4);
    click.mockRestore();
  });
});

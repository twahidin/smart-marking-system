import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { InsightsPayload } from "../../api/types";
import { InsightsPanel } from "../InsightsPanel";

function mockFetch(handlers: Record<string, (init?: RequestInit) => Response>) {
  const calls: { path: string; method: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      calls.push({ path, method });
      const handler = handlers[`${method} ${path}`];
      if (!handler) return Promise.reject(new Error(`Unexpected fetch to ${method} ${path}`));
      return Promise.resolve(handler(init));
    }),
  );
  return calls;
}

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

const INSIGHTS = "/api/classes/1/assignments/3/insights";
const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status });

const stats: InsightsPayload["stats"] = {
  n_students: 40, n_marked: 38, n_pending: 3,
  totals: { mean: 5.2, median: 5, max: 9, buckets: [{ from: 0, to: 1, n: 2 }, { from: 2, to: 3, n: 5 }, { from: 4, to: 5, n: 9 }, { from: 6, to: 7, n: 14 }, { from: 8, to: 9, n: 8 }] },
  parts: [
    { q_id: "8a", label: "8(a)", max: 3, attempted: 4, mean_pct: 86.0, full: 3, zero: 0, allocations: [{ label: "M1", lost: 1 }], not_in_scheme: 0, illegible: 0, pending: 0 },
    { q_id: "9b", label: "9(b)", max: 2, attempted: 38, mean_pct: 41.0, full: 9, zero: 18, allocations: [{ label: "M1", lost: 21 }, { label: "A1", lost: 27 }], not_in_scheme: 3, illegible: 1, pending: 2 },
    { q_id: "10", label: "10", max: 4, attempted: 30, mean_pct: null, full: 0, zero: 0, allocations: [], not_in_scheme: 0, illegible: 0, pending: 30 },
  ],
  weakest: ["9b"],
  most_lost: [{ q_id: "9b", label: "A1", lost: 27, of: 38 }, { q_id: "8a", label: "M1", lost: 1, of: 4 }],
  students: [
    { student_id: 1, reg_no: 1, name: "Tan Wei Ling", total: 4, max: 9, weak_parts: ["9b", "10"] },
    { student_id: 2, reg_no: 2, name: "Muhammad Danish", total: 8, max: 9, weak_parts: [] },
    { student_id: 4, reg_no: 4, name: "Lim Jun Hao", total: 3, max: 9, weak_parts: ["9b"] },
  ],
};

const report: NonNullable<InsightsPayload["report"]> = {
  summary: "The class rearranged confidently; the follow-through into 9(b) is where the marks went.",
  strengths: ["Rearranging is secure", "Units are carried through"],
  gaps: [{ part_ids: ["9b"], title: "Hence questions", what_went_wrong: "Started again instead of reusing 9(a)", students_affected: 21 }],
  recommendations: [{ title: "Reteach follow-through", detail: "Work 9(b) from 9(a) on the board", part_ids: ["9b"] }],
  students_to_support: [{ reg_nos: [1, 4], focus: "follow-through from a previous part" }],
};

const payload: InsightsPayload = { stats, report, n_marked: 38, provider: "openai", model: "gpt-5-mini", generated_at: "2026-09-12T09:00:00Z", error: null, job: null };
const panel = () => <InsightsPanel classId={1} caId={3} />;

describe("InsightsPanel", () => {
  it("renders the marks-by-part bars, the most-lost allocations and the narrative in order", async () => {
    mockFetch({ [`GET ${INSIGHTS}`]: json(payload) });
    render(panel());

    expect(await screen.findByText(/38 of 40 marked/)).toBeInTheDocument();
    expect(screen.getByText(/mean 5\.2 \/ 9/)).toBeInTheDocument();
    expect(screen.getByText(/gpt-5-mini/)).toBeInTheDocument();

    const bars = within(screen.getByRole("list", { name: "Marks by part" })).getAllByRole("listitem");
    expect(bars).toHaveLength(3);
    expect(bars[1]).toHaveTextContent("9(b)");
    expect(bars[1]).toHaveTextContent("41%");
    expect(bars[1]).toHaveClass("weak");
    // a part nobody's mark has settled yet shows a dash rather than a bar, and never ranks as weakest
    expect(bars[2]).toHaveTextContent("—");
    expect(bars[0]).not.toHaveClass("weak");

    expect(screen.getByText("9(b) · A1 — 27 of 38")).toBeInTheDocument();

    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Marks by part", "Most-lost allocations", "Summary", "Strengths", "Gaps", "Recommended next steps",
      "Students to support", "Score distribution",
    ]);
    expect(screen.getByText(/the follow-through into 9\(b\) is where the marks went/)).toBeInTheDocument();
    expect(screen.getByText("Rearranging is secure")).toBeInTheDocument();
    expect(screen.getByText(/Started again instead of reusing 9\(a\)/)).toBeInTheDocument();
    expect(screen.getByText(/Work 9\(b\) from 9\(a\) on the board/)).toBeInTheDocument();

    // names are joined back onto the register numbers the model wrote, with each student's weak parts
    const support = screen.getByRole("table", { name: "Students to support" });
    const rows = within(support).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Tan Wei Ling");
    expect(rows[1]).toHaveTextContent("9(b), 10");
    expect(rows[1]).toHaveTextContent("follow-through from a previous part");
    expect(rows[2]).toHaveTextContent("Lim Jun Hao");

    const dist = within(screen.getByRole("list", { name: "Score distribution" })).getAllByRole("listitem");
    expect(dist).toHaveLength(5);
    expect(dist[0]).toHaveTextContent("0–1");
    expect(dist[3]).toHaveTextContent("14");
  });

  it("regenerates and polls every 5 seconds while the job runs", async () => {
    // shouldAdvanceTime keeps findBy*/waitFor working on their own clock while the 5 s poll stays under
    // this test's control (nothing else here waits anywhere near 5 s of real time).
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
    let live: InsightsPayload = { ...payload, report: null, generated_at: null };
    const calls = mockFetch({
      [`GET ${INSIGHTS}`]: () => new Response(JSON.stringify(live), { status: 200 }),
      [`POST ${INSIGHTS}/regenerate`]: json({ job_id: 5 }, 202),
    });
    render(panel());
    expect(await screen.findByText(/38 of 40 marked/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Regenerate" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/insights/regenerate"))).toBe(true));
    expect(await screen.findByRole("button", { name: "Generating…" })).toBeDisabled();

    live = { ...live, job: { status: "running" } };
    const before = calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(calls.length).toBe(before + 1);
    expect(screen.getByRole("button", { name: "Generating…" })).toBeInTheDocument();

    live = { ...payload };
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    await waitFor(() => expect(screen.getByRole("button", { name: "Regenerate" })).toBeEnabled());
    expect(screen.getByText(/the follow-through into 9\(b\) is where the marks went/)).toBeInTheDocument();
    // ...and the polling stops once the job is gone
    const settled = calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(calls.length).toBe(settled);
  });

  it("shows the server's reason when a regenerate is refused", async () => {
    mockFetch({
      [`GET ${INSIGHTS}`]: json(payload),
      [`POST ${INSIGHTS}/regenerate`]: json({ error: { code: "already_running", message: "Insights are already being generated" } }, 409),
    });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Regenerate" }));
    expect(await screen.findByText("Insights are already being generated")).toBeInTheDocument();
  });

  it("downloads the insights PDF under the server's filename", async () => {
    const saved: string[] = [];
    mockFetch({
      [`GET ${INSIGHTS}`]: json(payload),
      [`GET ${INSIGHTS}.pdf`]: () => new Response(new Blob(["%PDF"]), { status: 200, headers: { "Content-Disposition": 'attachment; filename="quadratics-worksheet-3-insights.pdf"' } }),
    });
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:insights"), revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { saved.push(this.download); });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Download PDF" }));
    await vi.waitFor(() => expect(saved).toEqual(["quadratics-worksheet-3-insights.pdf"]));
    click.mockRestore();
  });

  it("shows the numbers with why the narrative is missing when the last generate failed", async () => {
    mockFetch({ [`GET ${INSIGHTS}`]: json({ ...payload, report: null, generated_at: null, error: "No API key saved for openai — add one under Settings." }) });
    render(panel());
    expect(await screen.findByText(/The AI summary hasn't been generated yet/)).toBeInTheDocument();
    expect(screen.getByText(/No API key saved for openai/)).toBeInTheDocument();
    // the numbers are still there, and nothing pretends there is a narrative
    expect(within(screen.getByRole("list", { name: "Marks by part" })).getAllByRole("listitem")[1]).toHaveTextContent("41%");
    expect(screen.queryByRole("heading", { name: "Recommended next steps" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Students to support" })).not.toBeInTheDocument();
  });

  it("says nothing is marked yet instead of drawing an empty chart", async () => {
    const empty: InsightsPayload = {
      ...payload, report: null, generated_at: null,
      stats: { ...stats, n_marked: 0, n_pending: 0, parts: [], weakest: [], most_lost: [], students: [], totals: { mean: null, median: null, max: 9, buckets: [] } },
    };
    mockFetch({ [`GET ${INSIGHTS}`]: json(empty) });
    render(panel());
    expect(await screen.findByText(/Nothing marked yet/)).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Marks by part" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Regenerate" })).toBeDisabled();
  });

  it("shows the error when the insights can't be loaded", async () => {
    mockFetch({ [`GET ${INSIGHTS}`]: json({ error: { code: "not_found", message: "Assignment not found" } }, 404) });
    render(panel());
    expect(await screen.findByText("Assignment not found")).toBeInTheDocument();
  });
});

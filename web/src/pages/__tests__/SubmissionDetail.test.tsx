import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SubmissionDetail as D } from "../../api/types";
import { SubmissionDetail } from "../SubmissionDetail";

const failed: D = {
  id: 7, label: "Tan Wei Ling", subject: "math", context: "", status: "failed", created_at: "2026-09-15T03:04:05Z",
  rubric: { criterion_defs: [{ id: "c1", description: "method", max_score: 2 }] },
  pages: [{ id: 1, page_index: 0, width: 100, height: 100 }], marks: [], totals: null, feedback: null,
  job: { status: "failed", attempts: 5, error: "Provider returned HTTP 401", started_at: null, finished_at: null },
  assignment_id: null, assignment_title: null,
};

function mockFetch(handlers: Record<string, () => Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      const handler = handlers[path];
      if (!handler) return Promise.reject(new Error(`Unexpected fetch to ${path}`));
      return Promise.resolve(handler());
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/submissions/7"]}>
      <Routes>
        <Route path="/submissions/:id" element={<SubmissionDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SubmissionDetail retry", () => {
  it("shows the API error inside the failed notice when retry is rejected", async () => {
    mockFetch({
      "/api/submissions/7": () => new Response(JSON.stringify(failed), { status: 200 }),
      "/api/submissions/7/retry": () => new Response(JSON.stringify({ error: { code: "not_failed", message: "Only failed submissions can be retried" } }), { status: 409 }),
    });
    renderDetail();
    await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Only failed submissions can be retried", { exact: false })).toBeInTheDocument();
    // The error sits inside the failed-state notice; the original failure is still shown and the page did not flip to "queued".
    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent("Marking failed. Provider returned HTTP 401");
    expect(notice).toHaveTextContent("Retry failed. Only failed submissions can be retried");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("falls back to a generic message when retry throws a network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/api/submissions/7") return Promise.resolve(new Response(JSON.stringify(failed), { status: 200 }));
        return Promise.reject(new TypeError("Failed to fetch"));
      }),
    );
    renderDetail();
    await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/Could not retry/)).toBeInTheDocument();
  });
});

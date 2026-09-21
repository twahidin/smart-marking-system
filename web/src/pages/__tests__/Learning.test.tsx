import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Learning } from "../Learning";

const noRuns = () => new Response(JSON.stringify({ runs: [], pending: [] }), { status: 200 });

function mockFetch(handlers: Record<string, (init?: RequestInit) => Response>) {
  const calls: { path: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const handler = handlers[`${method} ${path}`] ?? (method === "GET" ? handlers[path] : undefined);
      if (!handler) return Promise.reject(new Error(`Unexpected fetch to ${method} ${path}`));
      return Promise.resolve(handler(init));
    }),
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Learning", () => {
  it("shows an error notice (not the empty state) when the GETs fail", async () => {
    const fail = () => new Response(JSON.stringify({ error: { code: "server_error", message: "Could not reach the server" } }), { status: 500 });
    mockFetch({ "/api/notes": fail, "/api/exemplars": fail, "/api/stats": fail, "/api/reflect/runs": fail });
    render(
      <MemoryRouter>
        <Learning />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Could not reach the server")).toBeInTheDocument();
    expect(screen.queryByText("No notes yet")).not.toBeInTheDocument();
  });

  it("renders a draft note with an Approve button when the GETs succeed", async () => {
    mockFetch({
      "/api/notes": () => new Response(JSON.stringify([{ id: 1, subject: "math", note: "Accept equivalent fractions.", status: "draft" }]), { status: 200 }),
      "/api/exemplars": () => new Response(JSON.stringify([]), { status: 200 }),
      "/api/stats": () => new Response(JSON.stringify({}), { status: 200 }),
      "/api/reflect/runs": noRuns,
    });
    render(
      <MemoryRouter>
        <Learning />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Accept equivalent fractions.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("empty state does not tell a hosted user to run a CLI command", async () => {
    const empty = () => new Response(JSON.stringify([]), { status: 200 });
    mockFetch({ "/api/notes": empty, "/api/exemplars": empty, "/api/stats": () => new Response(JSON.stringify({}), { status: 200 }), "/api/reflect/runs": noRuns });
    render(
      <MemoryRouter>
        <Learning />
      </MemoryRouter>,
    );
    expect(await screen.findByText("No notes yet.")).toBeInTheDocument();
    expect(screen.getByText(/then run reflection \(or leave it to run nightly\)/)).toBeInTheDocument();
    expect(screen.queryByText(/sms reflect/)).not.toBeInTheDocument();
  });

  it("Run reflection posts the chosen subject and shows the queued notice", async () => {
    const empty = () => new Response(JSON.stringify([]), { status: 200 });
    let pending: string[] = [];
    const calls = mockFetch({
      "/api/notes": empty, "/api/exemplars": empty, "/api/stats": () => new Response(JSON.stringify({}), { status: 200 }),
      "/api/reflect/runs": () => new Response(JSON.stringify({ runs: [{ id: 1, subject: "science", lookback_days: 7, proposed_notes: 2, started_at: "2026-09-15T03:04:05Z", finished_at: "2026-09-15T03:05:05Z", error: null }], pending }), { status: 200 }),
      "POST /api/reflect": () => { pending = ["language"]; return new Response(JSON.stringify({ job_id: 9 }), { status: 202 }); },
    });
    render(
      <MemoryRouter>
        <Learning />
      </MemoryRouter>,
    );
    const button = await screen.findByRole("button", { name: "Run reflection" });
    await userEvent.selectOptions(screen.getByLabelText("Subject"), "language");
    await userEvent.click(button);
    expect(await screen.findByText(/Reflection queued — notes appear below when it finishes/)).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST");
    expect(post?.path).toBe("/api/reflect");
    expect(post?.body).toEqual({ subject: "language", lookback_days: 7 });
    // disabled while that subject is pending; recent runs list shows the earlier run
    expect(await screen.findByRole("button", { name: "Reflection queued…" })).toBeDisabled();
    expect(screen.getByText("Recent runs")).toBeInTheDocument();
    expect(screen.getByText(/2 notes proposed/)).toBeInTheDocument();
  });

  it("lists a running subject once, not as both running and queued", async () => {
    const empty = () => new Response(JSON.stringify([]), { status: 200 });
    mockFetch({
      "/api/notes": empty, "/api/exemplars": empty, "/api/stats": () => new Response(JSON.stringify({}), { status: 200 }),
      "/api/reflect/runs": () => new Response(JSON.stringify({
        runs: [{ id: 2, subject: "math", lookback_days: 7, proposed_notes: 0, started_at: "2026-09-15T03:04:05Z", finished_at: null, error: null }],
        pending: ["math", "science"],
      }), { status: 200 }),
    });
    render(
      <MemoryRouter>
        <Learning />
      </MemoryRouter>,
    );
    const list = (await screen.findByText("Recent runs")).nextElementSibling!;
    const items = Array.from(list.querySelectorAll("li")).map((li) => li.textContent);
    expect(items).toHaveLength(2);
    expect(items[0]).toContain("Science");
    expect(items[0]).toContain("queued");
    expect(items[1]).toContain("Maths");
    expect(items[1]).toContain("running");
  });

  it("shows the API error when Run reflection is rejected", async () => {
    const empty = () => new Response(JSON.stringify([]), { status: 200 });
    mockFetch({
      "/api/notes": empty, "/api/exemplars": empty, "/api/stats": () => new Response(JSON.stringify({}), { status: 200 }), "/api/reflect/runs": noRuns,
      "POST /api/reflect": () => new Response(JSON.stringify({ error: { code: "already_running", message: "Reflection is already queued for this subject" } }), { status: 409 }),
    });
    render(
      <MemoryRouter>
        <Learning />
      </MemoryRouter>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Run reflection" }));
    expect(await screen.findByText("Reflection is already queued for this subject")).toBeInTheDocument();
  });

  it("offers every subject to reflect on, MT and Computing included", async () => {
    const empty = () => new Response(JSON.stringify([]), { status: 200 });
    const calls = mockFetch({
      "/api/notes": empty, "/api/exemplars": empty, "/api/stats": () => new Response(JSON.stringify({}), { status: 200 }),
      "/api/reflect/runs": noRuns,
      "POST /api/reflect": () => new Response(JSON.stringify({ job_id: 1 }), { status: 202 }),
    });
    render(
      <MemoryRouter>
        <Learning />
      </MemoryRouter>,
    );
    const select = await screen.findByLabelText("Subject");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent))
      .toEqual(["Maths", "English", "Science", "MT", "Computing"]);
    await userEvent.selectOptions(select, "computing");
    await userEvent.click(screen.getByRole("button", { name: "Run reflection" }));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ subject: "computing" });
  });
});

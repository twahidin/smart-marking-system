import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Learning } from "../Learning";

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

describe("Learning", () => {
  it("shows an error notice (not the empty state) when the GETs fail", async () => {
    const fail = () => new Response(JSON.stringify({ error: { code: "server_error", message: "Could not reach the server" } }), { status: 500 });
    mockFetch({ "/api/notes": fail, "/api/exemplars": fail, "/api/stats": fail });
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
    });
    render(
      <MemoryRouter>
        <Learning />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Accept equivalent fractions.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { StudentAssignmentDetail, StudentMe } from "../../api/types";
import { HandIn } from "../HandIn";
import { StudentLayout } from "../StudentLayout";

function mockFetch(handlers: Record<string, (init?: RequestInit) => Response>) {
  const calls: { path: string; method: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      calls.push({ path, method, init });
      const handler = handlers[`${method} ${path}`];
      if (!handler) return Promise.reject(new Error(`Unexpected fetch to ${method} ${path}`));
      try { return Promise.resolve(handler(init)); } catch (e) { return Promise.reject(e); }
    }),
  );
  return calls;
}

beforeEach(() => {
  // jsdom has no canvas — downscale must fall back to the original file without decoding anything.
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => null);
  vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:x", revokeObjectURL: () => {} });
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const me: StudentMe = { class_name: "4E2", code: "CE4R", student_name: "Tan Wei Ling", reg_no: 1 };
const detail: StudentAssignmentDetail = { id: 1, title: "Worksheet 3", due_at: null, status: "to_hand_in", handed_in_at: null, pages: 0, allow_student_uploads: true, feedback: null };
const ok = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function app(path: string) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/s" element={<StudentLayout />}>
          <Route index element={<p>home page</p>} />
          <Route path="a/:caid" element={<p>detail page</p>} />
          <Route path="a/:caid/hand-in" element={<HandIn />} />
        </Route>
        <Route path="/join" element={<p>join page</p>} />
      </Routes>
    </MemoryRouter>
  );
}

const jpg = (name: string) => new File([name], name, { type: "image/jpeg" });

describe("HandIn", () => {
  it("orders pages, hands them in, and keeps them when the upload fails", async () => {
    let fail = true;
    const calls = mockFetch({
      "GET /api/student/me": () => ok(me),
      "GET /api/student/assignments/1": () => ok(detail),
      "POST /api/student/assignments/1/hand-in": () => { if (fail) throw new TypeError("Failed to fetch"); return ok({ id: 5, status: "queued", pages: [] }, 202); },
    });
    render(app("/s/a/1/hand-in"));
    expect(await screen.findByRole("heading", { name: "Worksheet 3" })).toBeInTheDocument();
    expect(screen.getByLabelText("Take photo")).toHaveAttribute("capture", "environment");
    const gallery = screen.getByLabelText("Choose from gallery");
    expect(gallery).toHaveAttribute("multiple");
    await userEvent.upload(gallery, [jpg("a.jpg"), jpg("b.jpg")]);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("a.jpg");
    await userEvent.click(screen.getAllByRole("button", { name: "Move up" })[1]);
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("b.jpg");
    await userEvent.click(screen.getByRole("button", { name: "Hand in 2 pages" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't hand in — check your signal and try again.");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/Handed in/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to assignments" })).toHaveAttribute("href", "/s");
    const posts = calls.filter((c) => c.method === "POST");
    expect(posts.length).toBe(2);
    const form = posts[1].init?.body as FormData;
    expect(form.getAll("files").map((f) => (f as File).name)).toEqual(["b.jpg", "a.jpg"]);
    expect(document.body.textContent ?? "").not.toMatch(/escalation|confidence|reviewer/i);
  });

  it("deletes a page, uses the singular label, and shows the server's reason when it refuses", async () => {
    mockFetch({
      "GET /api/student/me": () => ok(me),
      "GET /api/student/assignments/1": () => ok(detail),
      "POST /api/student/assignments/1/hand-in": () => ok({ error: { code: "uploads_closed", message: "Hand-ins for this assignment are closed." } }, 403),
    });
    render(app("/s/a/1/hand-in"));
    const gallery = await screen.findByLabelText("Choose from gallery");
    await userEvent.upload(gallery, [jpg("a.jpg"), jpg("b.jpg")]);
    expect(screen.getByRole("button", { name: "Hand in 2 pages" })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("b.jpg");
    await userEvent.click(screen.getByRole("button", { name: "Hand in 1 page" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Hand-ins for this assignment are closed.");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("shows the filename instead of a broken thumbnail for PDFs", async () => {
    mockFetch({
      "GET /api/student/me": () => ok(me),
      "GET /api/student/assignments/1": () => ok(detail),
    });
    render(app("/s/a/1/hand-in"));
    const gallery = await screen.findByLabelText("Choose from gallery");
    await userEvent.upload(gallery, [new File(["%PDF"], "scan.pdf", { type: "application/pdf" }), jpg("a.jpg")]);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0].querySelector("img")).toBeNull();
    expect(items[0]).toHaveTextContent("scan.pdf");
    expect(items[1].querySelector("img")).toHaveAttribute("src", "blob:x");
  });

  it("keeps at most 20 pages and says so", async () => {
    mockFetch({
      "GET /api/student/me": () => ok(me),
      "GET /api/student/assignments/1": () => ok(detail),
    });
    render(app("/s/a/1/hand-in"));
    const gallery = await screen.findByLabelText("Choose from gallery");
    await userEvent.upload(gallery, Array.from({ length: 21 }, (_, i) => jpg(`p${i + 1}.jpg`)));
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
    expect(screen.getByRole("status")).toHaveTextContent("You can hand in at most 20 pages.");
    expect(screen.getByRole("button", { name: "Hand in 20 pages" })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Delete" })[19]);
    expect(screen.getAllByRole("listitem")).toHaveLength(19);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("redirects to the assignment page when it is no longer waiting to be handed in", async () => {
    mockFetch({
      "GET /api/student/me": () => ok(me),
      "GET /api/student/assignments/1": () => ok({ ...detail, status: "handed_in", handed_in_at: "2026-09-18T08:00:00Z", pages: 2 }),
    });
    render(app("/s/a/1/hand-in"));
    expect(await screen.findByText("detail page")).toBeInTheDocument();
  });
});

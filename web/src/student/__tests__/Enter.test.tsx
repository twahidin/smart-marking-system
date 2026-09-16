import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Enter } from "../Enter";
import { parseStudentId } from "../api";

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

afterEach(() => vi.unstubAllGlobals());

describe("parseStudentId", () => {
  it("accepts the ways a student might type it", () => {
    expect(parseStudentId("CE4R-12")).toEqual({ code: "CE4R", reg_no: 12 });
    expect(parseStudentId("ce4r 12")).toEqual({ code: "CE4R", reg_no: 12 });
    expect(parseStudentId("CE4R–12")).toEqual({ code: "CE4R", reg_no: 12 });
    expect(parseStudentId("  ce4r-07 ")).toEqual({ code: "CE4R", reg_no: 7 });
  });
  it("rejects what is not an ID", () => {
    expect(parseStudentId("")).toBeNull();
    expect(parseStudentId("CE4R-")).toBeNull();
    expect(parseStudentId("CE4R-0")).toBeNull();
    expect(parseStudentId("CE4R-x")).toBeNull();
    expect(parseStudentId("CE1R-12")).toBeNull(); // 1 is not in the code alphabet
    expect(parseStudentId("CE4RR-12")).toBeNull();
  });
});

describe("Enter", () => {
  it("pre-fills the code from the link and looks the number up", async () => {
    const calls = mockFetch({ "POST /api/student/lookup": () => new Response(JSON.stringify({ class_name: "4E2", code: "CE4R", student_name: "Tan Wei Ling", reg_no: 1 }), { status: 200 }) });
    render(<MemoryRouter initialEntries={["/c/ce4r"]}><Routes><Route path="/c/:code" element={<Enter />} /><Route path="/s/confirm" element={<p>confirm page</p>} /></Routes></MemoryRouter>);
    expect(screen.getByText("CE4R-")).toBeInTheDocument();
    const input = screen.getByLabelText("Your register number");
    expect(input).toHaveAttribute("inputmode", "numeric");
    await userEvent.type(input, "1");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("confirm page")).toBeInTheDocument();
    expect(calls[0]).toEqual({ path: "/api/student/lookup", method: "POST" });
  });

  it("shows the server's plain-words error", async () => {
    mockFetch({ "POST /api/student/lookup": () => new Response(JSON.stringify({ error: { code: "no_such_student", message: "No student #37 in this class — check the number on your class list" } }), { status: 404 }) });
    render(<MemoryRouter initialEntries={["/c/CE4R"]}><Routes><Route path="/c/:code" element={<Enter />} /></Routes></MemoryRouter>);
    await userEvent.type(screen.getByLabelText("Your register number"), "37");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No student #37 in this class");
  });

  it("/join takes the whole ID", async () => {
    mockFetch({ "POST /api/student/lookup": (init) => { expect(JSON.parse(String(init?.body))).toEqual({ code: "CE4R", reg_no: 12 }); return new Response(JSON.stringify({ class_name: "4E2", code: "CE4R", student_name: "Lim", reg_no: 12 }), { status: 200 }); } });
    render(<MemoryRouter initialEntries={["/join"]}><Routes><Route path="/join" element={<Enter />} /><Route path="/s/confirm" element={<p>confirm page</p>} /></Routes></MemoryRouter>);
    await userEvent.type(screen.getByLabelText("Your student ID"), "ce4r-12");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("confirm page")).toBeInTheDocument();
  });

  it("/join explains the format when the ID does not parse, without calling the server", async () => {
    const calls = mockFetch({});
    render(<MemoryRouter initialEntries={["/join"]}><Routes><Route path="/join" element={<Enter />} /></Routes></MemoryRouter>);
    await userEvent.type(screen.getByLabelText("Your student ID"), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Type your ID like CE4R-12.");
    expect(calls).toHaveLength(0);
  });
});

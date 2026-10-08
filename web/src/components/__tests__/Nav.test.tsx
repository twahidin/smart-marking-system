import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Nav } from "../Nav";

describe("Nav", () => {
  it("leads with the Marking Room and keeps the queue count on Review", () => {
    render(<MemoryRouter><Nav needsYou={3} /></MemoryRouter>);
    const links = screen.getAllByRole("link").map((a) => a.textContent);
    expect(links[1]).toBe("Marking Room");
    expect(screen.getByRole("link", { name: /Marking Room/ })).toHaveAttribute("href", "/room");
    expect(screen.getByRole("link", { name: /Review/ })).toHaveTextContent("3");
  });

  it("takes the brand home to the Marking Room", () => {
    render(<MemoryRouter><Nav needsYou={0} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Smart Marking" })).toHaveAttribute("href", "/room");
  });
});

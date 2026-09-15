import { render, screen } from "@testing-library/react";
import { StatusPill } from "../StatusPill";

it("renders the plain-words label and amber class for needs_you", () => {
  render(<StatusPill status="needs_you" needsYou={["q2", "q5"]} />);
  const el = screen.getByText("Needs you · Q2, Q5");
  expect(el.closest(".pill")).toHaveClass("pill-amber");
});

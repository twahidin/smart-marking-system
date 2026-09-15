import { render, screen } from "@testing-library/react";
import { MarkDisplay } from "../MarkDisplay";

it("shows a range and an accessible label", () => {
  render(<MarkDisplay earned={15} max={25} upper={17} />);
  expect(screen.getByLabelText("15 to 17 out of 25")).toBeInTheDocument();
  expect(document.querySelectorAll(".sq i.on")).toHaveLength(15);
});

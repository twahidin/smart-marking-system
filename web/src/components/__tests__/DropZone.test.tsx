import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DropZone } from "../DropZone";

describe("DropZone", () => {
  it("shows the sorter and hands picked files up", async () => {
    const onFiles = vi.fn();
    render(<DropZone onFiles={onFiles} title="Feed the sorter" />);
    expect(screen.getByRole("img", { name: /paper sorter/ })).toHaveAttribute("src", "/art/sorter.jpg");
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "p1.jpg", { type: "image/jpeg" }));
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: "p1.jpg" })]);
  });
});

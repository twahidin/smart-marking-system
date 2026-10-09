import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Frames } from "../Frames";

describe("Frames", () => {
  it("renders nothing without frames and one hidden image per frame, placed by percent and offset by its delay", () => {
    const { container, rerender } = render(<Frames />);
    expect(container.querySelectorAll(".fx-frame")).toHaveLength(0);
    rerender(<Frames frames={[{ src: "/art/frames/a.png", left: "10%", top: "20%", width: "30%", delay: 0 }, { src: "/art/frames/b.png", left: "40%", top: "50%", width: "6%", delay: 3 }]} />);
    const imgs = container.querySelectorAll<HTMLImageElement>(".fx-frame");
    expect(imgs).toHaveLength(2);
    expect(imgs[0]).toHaveAttribute("aria-hidden", "true");
    expect(imgs[1]).toHaveAttribute("src", "/art/frames/b.png");
    expect(imgs[1].style.left).toBe("40%");
    expect(imgs[1].style.width).toBe("6%");
    expect(imgs[1].style.animationDelay).toBe("3s");
  });
});

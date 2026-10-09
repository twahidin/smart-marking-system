import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RoomScene2D } from "../RoomScene2D";

describe("RoomScene2D frames", () => {
  beforeEach(() => { sessionStorage.clear(); });

  it("cycles the room's frames on the 2d tier, none on the static tier, and none when film is switched off", () => {
    const { container, unmount } = render(<RoomScene2D desks={[]} tier="2d" onPick={vi.fn()} />);
    expect(container.querySelectorAll(".fx-frame").length).toBeGreaterThan(0);
    unmount();
    const r2 = render(<RoomScene2D desks={[]} tier="static" onPick={vi.fn()} />);
    expect(r2.container.querySelectorAll(".fx-frame")).toHaveLength(0);
    r2.unmount();
    sessionStorage.setItem("sms.scene.film", "off");
    const r3 = render(<RoomScene2D desks={[]} tier="2d" onPick={vi.fn()} />);
    expect(r3.container.querySelectorAll(".fx-frame")).toHaveLength(0);
  });
});

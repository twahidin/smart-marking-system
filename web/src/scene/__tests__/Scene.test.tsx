import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Glow } from "../effects";
import { Scene, type Hotspot } from "../Scene";

const spots: Hotspot[] = [
  { id: "a", left: "20%", top: "30%", label: "4E2 Mathematics", sub: "4KEF · 4 students", onPick: () => {} },
  { id: "b", left: "60%", top: "30%", label: "3N1 English", href: "/classes/2" },
];
const tag = (name: string) => screen.getByTestId(`tag-${name}`);
function mount(extra: Partial<React.ComponentProps<typeof Scene>> = {}) {
  return render(<MemoryRouter><Scene name="The school" art="/art/school.jpg" alt="school" hotspots={spots} tier="2d" effects={<Glow left="10%" top="10%" />} {...extra} /></MemoryRouter>);
}
function pointer(coarse: boolean) {
  vi.stubGlobal("matchMedia", vi.fn((q: string) => ({ matches: q.includes("coarse") && coarse, addEventListener() {}, removeEventListener() {} })));
}

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); pointer(false); });
afterEach(() => vi.unstubAllGlobals());

describe("Scene", () => {
  it("hides labels until a hotspot is hovered or focused, and pins on tap", async () => {
    mount();
    expect(tag("a")).toHaveClass("off");
    await userEvent.hover(screen.getByRole("button", { name: "4E2 Mathematics" }));
    expect(tag("a")).toHaveClass("on");
    await userEvent.unhover(screen.getByRole("button", { name: "4E2 Mathematics" }));
    expect(tag("a")).toHaveClass("off");
    await userEvent.click(screen.getByRole("button", { name: "4E2 Mathematics" }));
    await userEvent.unhover(screen.getByRole("button", { name: "4E2 Mathematics" }));
    expect(tag("a")).toHaveClass("on");
    expect(screen.getByRole("link", { name: "3N1 English" })).toHaveAttribute("href", "/classes/2");
    act(() => screen.getByRole("link", { name: "3N1 English" }).focus());
    expect(tag("b")).toHaveClass("on");
  });

  it("Show labels opens every tag, is remembered, and defaults on for a coarse pointer", async () => {
    mount();
    await userEvent.click(screen.getByRole("button", { name: "Show labels" }));
    expect(tag("a")).toHaveClass("on"); expect(tag("b")).toHaveClass("on");
    expect(localStorage.getItem("sms.scene.labels")).toBe("on");
    localStorage.clear(); pointer(true);
    mount();
    expect(screen.getAllByTestId(/^tag-/).every((el) => el.classList.contains("on"))).toBe(true);
  });

  it("defaults labels on for the static tier, where nothing can be hovered, unless a preference is saved", () => {
    const { unmount } = mount({ tier: "static" });
    expect(screen.getAllByTestId(/^tag-/).every((el) => el.classList.contains("on"))).toBe(true);
    unmount();
    localStorage.setItem("sms.scene.labels", "off");
    mount({ tier: "static" });
    expect(tag("a")).toHaveClass("off");
  });

  it("describes each hotspot with its sub text for assistive tech", () => {
    mount();
    expect(screen.getByRole("button", { name: "4E2 Mathematics" })).toHaveAttribute("aria-description", "4KEF · 4 students");
  });

  it("renders no effects and no film on the static tier, and the film gate obeys the switch", () => {
    const { unmount } = mount({ tier: "static", film: "/art/film/school.mp4" });
    expect(screen.queryByTestId("fx")).toBeNull();
    expect(document.querySelector("video")).toBeNull();
    unmount();
    mount({ film: "/art/film/school.mp4" });
    expect(screen.getByTestId("fx")).toBeInTheDocument();
    expect(document.querySelector("video")).toHaveAttribute("src", "/art/film/school.mp4");
  });

  it("cycles regenerated frames on the live tier only, under the same Film switch", () => {
    const frames = [{ src: "/art/frames/desk-b.png", left: "44%", top: "34%", width: "7%", delay: 0 }, { src: "/art/frames/desk-c.png", left: "28%", top: "35%", width: "29%", delay: 3 }];
    const { unmount } = mount({ tier: "static", frames });
    expect(document.querySelectorAll(".fx-frame")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Film" })).toBeNull();
    unmount();
    mount({ frames });
    const imgs = document.querySelectorAll<HTMLImageElement>(".fx-frame");
    expect(imgs).toHaveLength(2);
    expect(imgs[1]).toHaveAttribute("src", "/art/frames/desk-c.png");
    expect(imgs[1].style.animationDelay).toBe("3s");
    expect(imgs[1].style.width).toBe("29%");
    fireEvent.click(screen.getByRole("button", { name: "Film" }));
    expect(document.querySelectorAll(".fx-frame")).toHaveLength(0);
  });

  it("plays a cue as a class for a moment", () => {
    vi.useFakeTimers();
    const { container } = mount({ cue: { name: "settle", key: 1 } });
    expect(container.querySelector(".scene-box")).toHaveClass("cue-settle");
    vi.advanceTimersByTime(1500);
    vi.useRealTimers();
  });
});

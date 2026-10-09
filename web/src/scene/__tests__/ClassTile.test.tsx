import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { ClassRow } from "../../api/types";
import { ClassTile } from "../ClassTile";

const base: ClassRow = { id: 1, name: "4E2 Mathematics", code: "4KEF", student_count: 4, open_assignments: 0, subject: "math", marking: 0, needs_you: 0, archived_at: null, created_at: "", updated_at: "" };
const mount = (c: Partial<ClassRow>, tier: "2d" | "static" = "2d", labels = false, film = false) =>
  render(<MemoryRouter><ClassTile c={{ ...base, ...c }} tier={tier} labels={labels} film={film} /></MemoryRouter>);

describe("ClassTile", () => {
  it("paints the subject's classroom, falls back to the plain one, and links to the class", () => {
    const first = mount({});
    expect(first.container.querySelector("img")).toHaveAttribute("src", "/art/tile-math.jpg");
    expect(screen.getByRole("link", { name: /4E2 Mathematics/ })).toHaveAttribute("href", "/classes/1");
    const second = mount({ subject: null, name: "Form 1" });
    expect(second.container.querySelector("img")).toHaveAttribute("src", "/art/tile-general.jpg");
    const legacy = mount({ subject: "english" as ClassRow["subject"], name: "Old template" });
    expect(legacy.container.querySelector("img")).toHaveAttribute("src", "/art/tile-general.jpg");
  });

  it("shows state as effects on the 2d tier only, and the detail line when labels are on", () => {
    const { container } = mount({ open_assignments: 2, marking: 1, needs_you: 3 });
    expect(container.querySelector(".fx-glow")).not.toBeNull();
    expect(container.querySelector(".fx-dots")).not.toBeNull();
    expect(container.querySelector(".fx-flag")).not.toBeNull();
    expect(screen.getByRole("link", { name: /3 need you/ })).toBeInTheDocument();
    expect(within(container).getByTestId("tile-sub")).toHaveClass("off");
    const quiet = mount({}, "static", true);
    expect(quiet.container.querySelector(".fx")).toBeNull();
    expect(within(quiet.container).getByTestId("tile-sub")).toHaveClass("on");
  });

  it("lazy-loads its still and plays the subject's film on the 2d tier only", () => {
    const live = mount({}, "2d", false, true);
    expect(live.container.querySelector("img")).toHaveAttribute("loading", "lazy");
    const video = live.container.querySelector("video");
    expect(video).not.toBeNull();
    expect(video).toHaveAttribute("src", "/art/film/tile-math.mp4");
    expect(video).toHaveAttribute("preload", "metadata");
    live.unmount();
    const still = mount({}, "static", false, true);
    expect(still.container.querySelector("video")).toBeNull();
  });

  it("plays at most six tile films at once; the rest keep their still", () => {
    const tiles = [1, 2, 3, 4, 5, 6, 7].map((id) => <ClassTile key={id} c={{ ...base, id, name: `Class ${id}` }} tier="2d" labels={false} film />);
    const { container } = render(<MemoryRouter>{tiles}</MemoryRouter>);
    const boxes = Array.from(container.querySelectorAll(".tile-box"));
    expect(boxes).toHaveLength(7);
    expect(boxes.slice(0, 6).every((b) => b.querySelector("video") !== null)).toBe(true);
    expect(boxes[6].querySelector("video")).toBeNull();
  });
});

import { describe, expect, it, vi } from "vitest";
import { canThumbnail, fmtSize, isProgramFile, PROGRAM_ACCEPT, prepareUploads } from "../files";

vi.mock("../image", () => ({
  // A stand-in for the real canvas resize: the name says the photo went through it.
  downscale: vi.fn((f: File) => Promise.resolve(new File(["small"], f.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" }))),
}));

describe("canThumbnail", () => {
  it("allows only browser-renderable raster formats", () => {
    expect(canThumbnail({ type: "image/jpeg" })).toBe(true);
    expect(canThumbnail({ type: "image/png" })).toBe(true);
    expect(canThumbnail({ type: "image/webp" })).toBe(true);
  });

  it("gives HEIC, PDF and unknown types the filename card instead", () => {
    expect(canThumbnail({ type: "image/heic" })).toBe(false);
    expect(canThumbnail({ type: "image/heif" })).toBe(false);
    expect(canThumbnail({ type: "application/pdf" })).toBe(false);
    expect(canThumbnail({ type: "" })).toBe(false);
  });
});

describe("isProgramFile", () => {
  it("recognises the four the marker can read, whatever the case", () => {
    expect(PROGRAM_ACCEPT).toBe(".py,.sb3,.xlsx,.zip");
    for (const name of ["prog.py", "game.sb3", "budget.xlsx", "work.zip", "PROG.PY"]) {
      expect(isProgramFile({ name })).toBe(true);
    }
  });

  it("leaves photos, PDFs and anything else alone", () => {
    for (const name of ["p1.jpg", "p1.png", "scan.pdf", "notes.txt", "noextension"]) {
      expect(isProgramFile({ name })).toBe(false);
    }
  });
});

describe("fmtSize", () => {
  it("reads as a size a teacher would say out loud", () => {
    expect(fmtSize(0)).toBe("0 B");
    expect(fmtSize(512)).toBe("512 B");
    expect(fmtSize(1234)).toBe("1.2 KB");
    expect(fmtSize(1024 * 1024)).toBe("1.0 MB");
    expect(fmtSize(3.5 * 1024 * 1024)).toBe("3.5 MB");
  });
});

describe("prepareUploads", () => {
  it("shrinks the photos and passes PDFs and program files through untouched", async () => {
    const photo = new File(["x"], "p1.png", { type: "image/png" });
    const pdf = new File(["%PDF"], "scan.pdf", { type: "application/pdf" });
    const prog = new File(["print(1)"], "prog.py", { type: "text/x-python" });
    const out = await prepareUploads([photo, pdf, prog]);
    expect(out.map((f) => f.name)).toEqual(["p1.jpg", "scan.pdf", "prog.py"]);
    // Only the photo was handed to the resizer; the other two are the very same File objects.
    const { downscale } = await import("../image");
    expect(vi.mocked(downscale)).toHaveBeenCalledTimes(1);
    expect(out[1]).toBe(pdf);
    expect(out[2]).toBe(prog);
  });
});

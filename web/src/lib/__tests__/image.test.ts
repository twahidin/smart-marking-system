import { afterEach, describe, expect, it, vi } from "vitest";
import { downscale } from "../image";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("downscale", () => {
  it("returns PDFs and other non-raster files unchanged", async () => {
    const pdf = new File(["%PDF"], "a.pdf", { type: "application/pdf" });
    await expect(downscale(pdf)).resolves.toBe(pdf);
    const heic = new File(["x"], "a.heic", { type: "image/heic" });
    await expect(downscale(heic)).resolves.toBe(heic);
    const unknown = new File(["x"], "a.bin", { type: "" });
    await expect(downscale(unknown)).resolves.toBe(unknown);
  });

  it("falls back to the original file when the browser cannot draw it (jsdom has no canvas)", async () => {
    const png = new File(["png"], "a.png", { type: "image/png" });
    const out = await downscale(png);
    expect(out).toBeInstanceOf(File);
    expect(out).toBe(png);
  });

  it("falls back to the original file when decoding fails", async () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => ({ drawImage: () => {} }) as unknown as CanvasRenderingContext2D);
    vi.stubGlobal("createImageBitmap", () => Promise.reject(new Error("decode failed")));
    const jpg = new File(["jpg"], "a.jpg", { type: "image/jpeg" });
    await expect(downscale(jpg)).resolves.toBe(jpg);
  });
});

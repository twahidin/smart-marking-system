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

  it("draws the photo at 2000px on the long edge, returns a JPEG, and releases the bitmap and canvas", async () => {
    const close = vi.fn();
    const createImageBitmap = vi.fn(() => Promise.resolve({ width: 4000, height: 3000, close }));
    vi.stubGlobal("createImageBitmap", createImageBitmap);
    const drawImage = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => ({ drawImage }) as unknown as CanvasRenderingContext2D);
    // The canvas is zeroed after toBlob resolves, so record its size at draw time.
    const drawn: { width: number; height: number }[] = [];
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (this: HTMLCanvasElement, cb: BlobCallback) {
      drawn.push({ width: this.width, height: this.height });
      cb(new Blob(["x"], { type: "image/jpeg" }));
    });
    const create = document.createElement.bind(document);
    const canvases: HTMLCanvasElement[] = [];
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => { const el = create(tag); if (tag === "canvas") canvases.push(el as HTMLCanvasElement); return el; });

    const out = await downscale(new File(["jpg"], "photo.jpeg", { type: "image/jpeg" }));

    expect(createImageBitmap).toHaveBeenCalledWith(expect.any(File), { imageOrientation: "from-image" });
    expect(canvases).toHaveLength(1);
    expect(drawn).toEqual([{ width: 2000, height: 1500 }]);
    expect(drawImage).toHaveBeenCalledWith(expect.objectContaining({ width: 4000 }), 0, 0, 2000, 1500);
    expect(close).toHaveBeenCalledTimes(1);
    expect(canvases[0].width).toBe(0);
    expect(canvases[0].height).toBe(0);
    expect(out.name).toBe("photo.jpg");
    expect(out.type).toBe("image/jpeg");
  });

  it("falls back to the original file when decoding fails", async () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => ({ drawImage: () => {} }) as unknown as CanvasRenderingContext2D);
    vi.stubGlobal("createImageBitmap", () => Promise.reject(new Error("decode failed")));
    const jpg = new File(["jpg"], "a.jpg", { type: "image/jpeg" });
    await expect(downscale(jpg)).resolves.toBe(jpg);
  });
});

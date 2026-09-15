import { describe, expect, it } from "vitest";
import { canThumbnail } from "../files";

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

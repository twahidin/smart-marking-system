import { zipSync } from "fflate";
import { describe, expect, it, vi } from "vitest";
import { expandZips, groupScripts, splitPage, uploadScripts } from "../bulk";

const f = (name: string, type = "image/jpeg") => new File(["x"], name, { type });

describe("splitPage", () => {
  it("takes a trailing page marker off the stem and keeps a bare name whole", () => {
    expect(splitPage("Tan Wei Ling-2.jpg")).toEqual({ label: "Tan Wei Ling", page: 2 });
    expect(splitPage("lim jun hao p3.png")).toEqual({ label: "lim jun hao", page: 3 });
    expect(splitPage("Nur Aisyah (1).jpeg")).toEqual({ label: "Nur Aisyah", page: 1 });
    expect(splitPage("Ravi_page10.jpg")).toEqual({ label: "Ravi", page: 10 });
    expect(splitPage("Ravi.jpg")).toEqual({ label: "Ravi", page: null });
    expect(splitPage("12.jpg")).toEqual({ label: "12", page: null });
  });
});

describe("groupScripts", () => {
  it("makes a script per PDF, groups images by label in page order, and grows existing scripts", () => {
    const first = groupScripts([f("Tan Wei Ling-2.jpg"), f("Ravi.pdf", "application/pdf"), f("Tan Wei Ling-1.jpg"), f("Lim Jun Hao.png", "image/png")]);
    expect(first.map((s) => [s.label, s.files.map((x) => x.name)])).toEqual([
      ["Lim Jun Hao", ["Lim Jun Hao.png"]],
      ["Ravi", ["Ravi.pdf"]],
      ["Tan Wei Ling", ["Tan Wei Ling-1.jpg", "Tan Wei Ling-2.jpg"]],
    ]);
    const grown = groupScripts([f("tan wei ling-3.jpg")], first);
    expect(grown.find((s) => s.label === "Tan Wei Ling")!.files.map((x) => x.name)).toEqual(["Tan Wei Ling-1.jpg", "Tan Wei Ling-2.jpg", "tan wei ling-3.jpg"]);
    expect(first.find((s) => s.label === "Tan Wei Ling")!.files).toHaveLength(2);
  });
});

describe("expandZips", () => {
  it("unpacks pages and program files from a zip, skipping folders, Finder copies, dotfiles and nested zips", async () => {
    const bytes = zipSync({
      "class/Tan Wei Ling-1.jpg": new Uint8Array([1]), "class/Tan Wei Ling-2.jpg": new Uint8Array([2]), "class/Ravi.pdf": new Uint8Array([3]),
      "class/notes.txt": new Uint8Array([4]), "__MACOSX/class/._Ravi.pdf": new Uint8Array([5]), "class/.DS_Store": new Uint8Array([6]),
      "class/inner.zip": new Uint8Array([7]), "class/prog.py": new Uint8Array([8]),
    });
    const zip = new File([bytes as BlobPart], "class.zip", { type: "application/zip" });
    const out = await expandZips([zip, f("extra.png", "image/png")]);
    expect(out.map((x) => x.name)).toEqual(["class/Tan Wei Ling-1.jpg", "class/Tan Wei Ling-2.jpg", "class/Ravi.pdf", "class/prog.py", "extra.png"]);
    expect(out[2].type).toBe("application/pdf");
    const scripts = groupScripts(out);
    expect(scripts.map((s) => s.label)).toEqual(["prog", "Ravi", "Tan Wei Ling", "extra"]);
  });
});

describe("uploadScripts", () => {
  it("posts every script at most two at a time, keeps going past a failure, and reports each result", async () => {
    const scripts = [1, 2, 3, 4].map((n) => ({ label: `S${n}`, files: [f(`S${n}.pdf`, "application/pdf")] }));
    let inFlight = 0, peak = 0;
    const post = vi.fn(async (form: FormData) => {
      inFlight++; peak = Math.max(peak, inFlight);
      await new Promise((r) => setTimeout(r, 5));
      inFlight--;
      if (form.get("label") === "S3") throw new Error("Too many pages");
      return { id: Number(String(form.get("label")).slice(1)) };
    });
    const seen: number[] = [];
    const results = await uploadScripts(scripts, { assignment_id: 7, subject: "math", context: "", rubric: "[]" }, post, (i) => seen.push(i));
    expect(peak).toBe(2);
    expect(results).toEqual([{ ok: true, id: 1 }, { ok: true, id: 2 }, { ok: false, error: "Too many pages" }, { ok: true, id: 4 }]);
    expect(seen.sort()).toEqual([0, 1, 2, 3]);
    const first = post.mock.calls[0][0];
    expect(first.get("assignment_id")).toBe("7");
    expect(first.getAll("files")).toHaveLength(1);
  });
});

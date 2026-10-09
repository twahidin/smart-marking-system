"""Cut the changed region of a regenerated scene frame into a feathered RGBA patch for FRAMES in web/src/scene/art.ts.

Regenerate the painting with Artlist image-to-image (modelGroupId 604, prompt "same illustration, identical in every
detail, except <one change>; everything else unchanged", settings {"aspect_ratio": "4:3"} or the model recomposes
the whole scene at 16:9), then:
    python3 scripts/scene-frame.py <base.png> <frame.png> <out-name> [x0,y0,x1,y1]
(the optional region, in base pixels, ignores changes outside it, for a render that also drifted elsewhere) writes web/public/art/frames/<out-name>.png scaled to the 1400 px still and prints the left/top/width percentages.
Needs Pillow."""
import json, sys, PIL.Image as I, PIL.ImageChops as C, PIL.ImageFilter as F
import os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "public", "art", "frames") + os.sep
base, frame, name = sys.argv[1:4]; region = [int(v) for v in sys.argv[4].split(",")] if len(sys.argv) > 4 else None
a = I.open(base).convert("RGB"); b = I.open(frame).convert("RGB").resize(a.size, I.LANCZOS); W, H = a.size
d = C.difference(a, b).convert("L").point(lambda v: 255 if v > 24 else 0)
d = d.filter(F.MinFilter(5)).filter(F.MaxFilter(41))          # drop specks, grow the real change
if region:
    keep = I.new("L", d.size, 0); keep.paste(255, tuple(region)); d = C.multiply(d, keep)
bbox = d.getbbox(); assert bbox, "no change found"
pad = 40; x0, y0, x1, y1 = max(0, bbox[0]-pad), max(0, bbox[1]-pad), min(W, bbox[2]+pad), min(H, bbox[3]+pad)
alpha = d.filter(F.GaussianBlur(14)).crop((x0, y0, x1, y1))
patch = b.crop((x0, y0, x1, y1)).convert("RGBA"); patch.putalpha(alpha)
scale = 1400 / W
patch = patch.resize((round((x1-x0)*scale), round((y1-y0)*scale)), I.LANCZOS)
os.makedirs(OUT, exist_ok=True); patch.save(f"{OUT}{name}.png", optimize=True)
print(json.dumps({"src": f"/art/frames/{name}.png", "left": round(100*x0/W, 2), "top": round(100*y0/H, 2), "width": round(100*(x1-x0)/W, 2), "kb": os.path.getsize(f"{OUT}{name}.png")//1024}))

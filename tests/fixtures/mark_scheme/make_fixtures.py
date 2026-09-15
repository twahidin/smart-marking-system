"""Regenerate the mark-scheme live-test fixtures (paper.png, scheme.png, script.png).

Renders plain, legible A4-ish page images with Pillow's default font at a large size so a vision
model can transcribe them reliably. Run with:

    uv run python tests/fixtures/mark_scheme/make_fixtures.py

Commit the resulting PNGs (each should stay well under 200 KB — plain black-on-white text
compresses tightly).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
SIZE = (1240, 1754)  # ~A4 at 150dpi
FONT_SIZE = 48
LINE_GAP = 22
MARGIN = 80


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def render(filename: str, title: str, lines: list[str]) -> None:
    img = Image.new("RGB", SIZE, "white")
    draw = ImageDraw.Draw(img)
    title_font = _font(FONT_SIZE + 8)
    body_font = _font(FONT_SIZE)
    y = MARGIN
    draw.text((MARGIN, y), title, fill="black", font=title_font)
    y += FONT_SIZE + 8 + LINE_GAP * 2
    for line in lines:
        draw.text((MARGIN, y), line, fill="black", font=body_font)
        y += FONT_SIZE + LINE_GAP
    path = OUT / filename
    img.save(path, format="PNG", optimize=True)
    print(f"{path} ({path.stat().st_size} bytes)")


def main() -> None:
    render("paper.png", "Mathematics - Question Paper", [
        "",
        "1(a) Solve 2x + 3 = 11. [2]",
        "",
        "1(b) Hence find x^2. [1]",
    ])
    render("scheme.png", "Mathematics - Mark Scheme", [
        "",
        "1(a) M1 for 2x = 8, A1 for x = 4",
        "",
        "1(b) B1 for 16",
    ])
    render("script.png", "Student Answer Script", [
        "",
        "1(a) 2x = 8, x = 4",
        "",
        "1(b) x^2 = 16",
    ])


if __name__ == "__main__":
    main()

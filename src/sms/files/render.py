from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

KIND_BY_EXT = {".py": "py", ".sb3": "sb3", ".xlsx": "xlsx"}
TEXT_BUDGET = 200_000


class RenderError(ValueError):
    def __init__(self, name: str, msg: str):
        super().__init__(f"{name}: {msg}"); self.name = name; self.msg = msg


@dataclass
class Rendered:
    name: str
    kind: str
    text: str
    summary: str
    truncated: bool = False


# Imported after RenderError/Rendered are defined: python/scratch/excel each import
# RenderError from this module, so importing them any earlier would be circular.
from sms.files import python as _py, scratch as _sb3, excel as _xlsx  # noqa: E402


def render_one(name: str, data: bytes) -> Rendered:
    ext = Path(name).suffix.lower()
    kind = KIND_BY_EXT.get(ext)
    if kind is None:
        raise RenderError(name, "unsupported file type (use .py, .sb3 or .xlsx)")
    fn = {"py": _py.render, "sb3": _sb3.render, "xlsx": _xlsx.render}[kind]
    try:
        text, summary = fn(data)
    except RenderError as e:
        # Sub-renderers don't know the submitted filename (they raise with a
        # placeholder like "project"/"workbook"); re-tag with the real name.
        raise RenderError(name, e.msg) from e
    except Exception as e:  # noqa: BLE001 - any parser failure is a bad file, never a crash
        raise RenderError(name, f"could not read ({e.__class__.__name__})") from e
    return Rendered(name=name, kind=kind, text=text, summary=summary)


def render_all(files: List[Tuple[str, bytes]], budget: int = TEXT_BUDGET) -> List[Rendered]:
    out = [render_one(n, b) for n, b in files]
    total = sum(len(r.text) for r in out)
    # Largest first: one huge file should not starve the small ones the marker also needs.
    for r in sorted(out, key=lambda r: -len(r.text)):
        if total <= budget:
            break
        over = total - budget
        keep = max(0, len(r.text) - over - 64)
        lines = r.text[:keep].rsplit("\n", 1)[0]
        dropped = r.text.count("\n") - lines.count("\n")
        r.text = lines + f"\n… truncated: {dropped} more lines\n"
        r.truncated = True
        total = sum(len(x.text) for x in out)
    return out

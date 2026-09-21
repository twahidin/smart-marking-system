import io, json, zipfile
from typing import Dict, List

from sms.files.render import MAX_DECOMPRESSED, RenderError

# opcode -> template; {NAME} = input or field value
OPCODES: Dict[str, str] = {
    "event_whenflagclicked": "when green flag clicked", "event_whenkeypressed": "when [{KEY_OPTION}] key pressed",
    "event_whenthisspriteclicked": "when this sprite clicked", "event_whenbroadcastreceived": "when I receive [{BROADCAST_OPTION}]",
    "event_broadcast": "broadcast [{BROADCAST_INPUT}]", "event_broadcastandwait": "broadcast [{BROADCAST_INPUT}] and wait",
    "control_repeat": "repeat ({TIMES})", "control_forever": "forever", "control_if": "if <{CONDITION}> then",
    "control_if_else": "if <{CONDITION}> then … else", "control_wait": "wait ({DURATION}) seconds",
    "control_repeat_until": "repeat until <{CONDITION}>", "control_stop": "stop [{STOP_OPTION}]",
    "motion_movesteps": "move ({STEPS}) steps", "motion_turnright": "turn right ({DEGREES}) degrees",
    "motion_turnleft": "turn left ({DEGREES}) degrees", "motion_gotoxy": "go to x: ({X}) y: ({Y})",
    "motion_changexby": "change x by ({DX})", "motion_changeyby": "change y by ({DY})", "motion_ifonedgebounce": "if on edge, bounce",
    "looks_say": "say ({MESSAGE})", "looks_sayforsecs": "say ({MESSAGE}) for ({SECS}) seconds", "looks_switchcostumeto": "switch costume to ({COSTUME})",
    "looks_show": "show", "looks_hide": "hide", "sound_play": "start sound ({SOUND_MENU})",
    "sensing_touchingobject": "touching [{TOUCHINGOBJECTMENU}]?", "sensing_keypressed": "key [{KEY_OPTION}] pressed?", "sensing_askandwait": "ask ({QUESTION}) and wait",
    "operator_add": "({NUM1}) + ({NUM2})", "operator_subtract": "({NUM1}) - ({NUM2})", "operator_multiply": "({NUM1}) * ({NUM2})",
    "operator_divide": "({NUM1}) / ({NUM2})", "operator_lt": "({OPERAND1}) < ({OPERAND2})", "operator_gt": "({OPERAND1}) > ({OPERAND2})",
    "operator_equals": "({OPERAND1}) = ({OPERAND2})", "operator_and": "<{OPERAND1}> and <{OPERAND2}>", "operator_or": "<{OPERAND1}> or <{OPERAND2}>",
    "operator_not": "not <{OPERAND}>", "operator_random": "pick random ({FROM}) to ({TO})", "operator_join": "join ({STRING1}) ({STRING2})",
    "data_setvariableto": "set [{VARIABLE}] to ({VALUE})", "data_changevariableby": "change [{VARIABLE}] by ({VALUE})",
    "data_addtolist": "add ({ITEM}) to [{LIST}]", "data_showvariable": "show variable [{VARIABLE}]",
    "procedures_definition": "define {custom_block}", "procedures_call": "call {custom_block}",
}
SUBSTACKS = ("SUBSTACK", "SUBSTACK2")


def _value(blocks, v, visited) -> str:
    """An input is [shadow, value]; value is a block id (string) or a literal array [type, text, ...]."""
    if isinstance(v, list) and len(v) >= 2:
        inner = v[1]
        if isinstance(inner, list) and len(inner) >= 2:
            return str(inner[1])
        if isinstance(inner, str) and inner in blocks:
            if inner in visited:
                return "[cycle]"
            return _render_block(blocks, inner, 0, visited, inline=True).strip()
    return "?"


def _render_block(blocks, bid, depth, visited, inline=False) -> str:
    # Guarded by callers (they check `bid in visited` before recursing in), but
    # checked again here too so this function is never the one thing standing
    # between a malformed project and infinite recursion.
    if bid in visited:
        return "[cycle]" if inline else "  " * depth + "[cycle]"
    visited.add(bid)
    b = blocks[bid]
    vals = {k: _value(blocks, v, visited) for k, v in (b.get("inputs") or {}).items() if k not in SUBSTACKS}
    vals.update({k: (v[0] if isinstance(v, list) and v else str(v)) for k, v in (b.get("fields") or {}).items()})
    if b.get("opcode") in ("procedures_definition", "procedures_call"):
        vals["custom_block"] = (b.get("mutation") or {}).get("proccode", "?")
    tmpl = OPCODES.get(b.get("opcode"), f"[{b.get('opcode')}]")
    try:
        line = tmpl.format(**{k: vals.get(k, "?") for k in _names(tmpl)})
    except (KeyError, IndexError):
        line = tmpl
    if inline:
        return line
    out = ["  " * depth + line]
    for key in SUBSTACKS:
        sub = (b.get("inputs") or {}).get(key)
        if sub and isinstance(sub, list) and len(sub) >= 2 and isinstance(sub[1], str) and sub[1] in blocks:
            if key == "SUBSTACK2":
                out.append("  " * depth + "else")
            out.extend(_render_chain(blocks, sub[1], depth + 1, visited))
    return "\n".join(out)


def _names(tmpl: str) -> List[str]:
    import string
    return [f for _, f, _, _ in string.Formatter().parse(tmpl) if f]


def _render_chain(blocks, bid, depth, visited) -> List[str]:
    """visited is shared across the whole current script's traversal (the top-level
    `next` chain, every substack, and every inline reporter block it embeds) so a
    block whose SUBSTACK/SUBSTACK2 points back at itself or an ancestor is rendered
    once and then prints a single `[cycle]` line instead of recursing forever."""
    out = []
    while bid and bid in blocks:
        if bid in visited:
            out.append("  " * depth + "[cycle]")
            break
        out.append(_render_block(blocks, bid, depth, visited))
        bid = blocks[bid].get("next")
    return out


def render(data: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_DECOMPRESSED:
                raise RenderError("project", "zip expands past 20 MB")
            project = json.loads(z.read("project.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as e:
        raise RenderError("project", "not a Scratch 3 project (.sb3)") from e
    lines, scripts = [], 0
    for t in project.get("targets", []):
        name = t.get("name", "?")
        lines.append(("stage " if t.get("isStage") else "sprite ") + name)
        for label, key in (("variables", "variables"), ("lists", "lists"), ("broadcasts", "broadcasts")):
            names = [v[0] if isinstance(v, list) else str(v) for v in (t.get(key) or {}).values()]
            if names:
                lines.append(f"  {label}: " + ", ".join(names))
        lines.append(f"  costumes: {len(t.get('costumes') or [])}, sounds: {len(t.get('sounds') or [])}")
        blocks = t.get("blocks") or {}
        tops = [bid for bid, b in blocks.items() if isinstance(b, dict) and b.get("topLevel") and b.get("opcode")]
        for bid in tops:
            scripts += 1
            lines.append("")
            visited: set = set()
            for l in _render_chain(blocks, bid, 0, visited):
                # A rendered block can itself be multi-line (a substack), so indent
                # every line it produced, not just the first.
                lines.extend("  " + x for x in l.split("\n"))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", f"{len(project.get('targets', []))} targets, {scripts} script{'s' if scripts != 1 else ''}"

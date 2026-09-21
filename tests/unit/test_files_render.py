import io, json, pathlib, zipfile, pytest

from sms.files.render import render_one, render_all, RenderError

FX = pathlib.Path(__file__).parent.parent / "fixtures" / "files"


def _b(n): return (FX / n).read_bytes()


def _sb3(blocks, target_name="Cat"):
    """Build an in-memory .sb3 (a zip with a project.json) from a raw `blocks` dict,
    for exercising edge cases that make_fixtures.py's committed fixtures don't cover."""
    project = {"targets": [
        {"isStage": False, "name": target_name, "variables": {}, "lists": {}, "broadcasts": {},
         "costumes": [{}], "sounds": [], "blocks": blocks},
    ]}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("project.json", json.dumps(project))
    return buf.getvalue()


def test_python_renders_with_line_numbers_and_syntax_ok():
    r = render_one("ok.py", _b("ok.py"))
    assert r.kind == "py" and r.text.startswith("syntax: ok\n") and "   4 |         s += x" in r.text
    assert r.summary == "7 lines, syntax ok"


def test_python_syntax_error_is_noted_not_raised():
    r = render_one("bad_syntax.py", _b("bad_syntax.py"))
    assert r.text.startswith("syntax: error at line 1") and "   1 | def broken(:" in r.text


def test_python_syntax_error_with_no_lineno_omits_line_none():
    # A null byte makes CPython raise SyntaxError with lineno=None.
    r = render_one("null_byte.py", b"a = 1\x00\n")
    assert r.text.startswith("syntax: error: ") and "line None" not in r.text


def test_scratch_blocks_become_indented_pseudo_code():
    r = render_one("two_sprites.sb3", _b("two_sprites.sb3"))
    assert "sprite Cat" in r.text and "when green flag clicked" in r.text
    assert "  repeat (10)" in r.text and "    move (10) steps" in r.text and "  broadcast [go]" in r.text
    assert "variables: score" in r.text and "costumes: 2" in r.text
    assert r.summary == "2 targets, 1 script"


def test_self_referencing_substack_terminates():
    # A block whose own SUBSTACK points at itself.
    self_ref = {
        "x": {"opcode": "control_forever", "next": None, "parent": None,
              "inputs": {"SUBSTACK": [2, "x"]}, "fields": {}, "topLevel": True},
    }
    r = render_one("self_ref.sb3", _sb3(self_ref))
    assert "[cycle]" in r.text

    # A nested block's SUBSTACK points back at an ancestor (the top-level block).
    ancestor_ref = {
        "p": {"opcode": "control_repeat", "next": None, "parent": None,
              "inputs": {"TIMES": [1, [6, "10"]], "SUBSTACK": [2, "q"]}, "fields": {}, "topLevel": True},
        "q": {"opcode": "control_repeat", "next": None, "parent": "p",
              "inputs": {"TIMES": [1, [6, "10"]], "SUBSTACK": [2, "p"]}, "fields": {}, "topLevel": False},
    }
    r2 = render_one("ancestor_ref.sb3", _sb3(ancestor_ref))
    assert "[cycle]" in r2.text


def test_broken_sb3_raises_render_error():
    with pytest.raises(RenderError) as e:
        render_one("broken.sb3", _b("broken.sb3"))
    assert "broken.sb3" in str(e.value)


def test_excel_shows_formulas_values_and_names():
    r = render_one("formulas.xlsx", _b("formulas.xlsx"))
    assert "sheet Marks" in r.text and "B2 = 20" in r.text
    assert "B4 = =SUM(B1:B3) → (not calculated)" in r.text
    assert "named ranges: Total = Marks!$B$4" in r.text
    assert r.summary == "1 sheet, 5 cells, 1 formula"


def test_oversized_xlsx_is_refused_before_openpyxl_opens_it():
    """An .xlsx is a zip and openpyxl inflates it without a budget, so the central directory's
    declared sizes are checked first — the same 20 MB pre-check a .sb3 gets."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", b"<Types/>")
        z.writestr("xl/worksheets/sheet1.xml", b"0" * (21 * 1024 * 1024))
    bomb = buf.getvalue()
    assert len(bomb) < 100 * 1024  # tiny on disk, 21 MB by its own central directory
    with pytest.raises(RenderError) as e:
        render_one("bomb.xlsx", bomb)
    assert e.value.name == "bomb.xlsx" and "expands past 20 MB" in e.value.msg


def test_xlsm_rejected():
    with pytest.raises(RenderError):
        render_one("macros.xlsm", b"")


def test_budget_truncates_largest_first():
    big = ("x = 1\n" * 60_000).encode()          # ~360 KB
    out = render_all([("small.py", b"y = 2\n"), ("big.py", big)], budget=50_000)
    small, large = out[0], out[1]
    assert not small.truncated and large.truncated
    assert "… truncated:" in large.text and len(large.text) <= 50_000

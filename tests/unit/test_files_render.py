import pathlib, pytest

from sms.files.render import render_one, render_all, RenderError

FX = pathlib.Path(__file__).parent.parent / "fixtures" / "files"


def _b(n): return (FX / n).read_bytes()


def test_python_renders_with_line_numbers_and_syntax_ok():
    r = render_one("ok.py", _b("ok.py"))
    assert r.kind == "py" and r.text.startswith("syntax: ok\n") and "   4 |         s += x" in r.text
    assert r.summary == "7 lines, syntax ok"


def test_python_syntax_error_is_noted_not_raised():
    r = render_one("bad_syntax.py", _b("bad_syntax.py"))
    assert r.text.startswith("syntax: error at line 1") and "   1 | def broken(:" in r.text


def test_scratch_blocks_become_indented_pseudo_code():
    r = render_one("two_sprites.sb3", _b("two_sprites.sb3"))
    assert "sprite Cat" in r.text and "when green flag clicked" in r.text
    assert "  repeat (10)" in r.text and "    move (10) steps" in r.text and "  broadcast [go]" in r.text
    assert "variables: score" in r.text and "costumes: 2" in r.text
    assert r.summary == "2 targets, 1 script"


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


def test_xlsm_rejected():
    with pytest.raises(RenderError):
        render_one("macros.xlsm", b"")


def test_budget_truncates_largest_first():
    big = ("x = 1\n" * 60_000).encode()          # ~360 KB
    out = render_all([("small.py", b"y = 2\n"), ("big.py", big)], budget=50_000)
    small, large = out[0], out[1]
    assert not small.truncated and large.truncated
    assert "… truncated:" in large.text and len(large.text) <= 50_000

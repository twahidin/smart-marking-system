from sms.memory.db import Database
from sms.web.services.classes import CODE_ALPHABET, new_code, normalise_code, unique_code


def test_alphabet_has_no_ambiguous_glyphs():
    assert set("0O1IL").isdisjoint(CODE_ALPHABET) and len(CODE_ALPHABET) == 31


def test_new_code_is_four_chars_from_the_alphabet():
    for _ in range(200):
        c = new_code()
        assert len(c) == 4 and all(ch in CODE_ALPHABET for ch in c)


def test_normalise_code_uppercases_and_strips():
    assert normalise_code(" ce4r ") == "CE4R" and normalise_code(None) == ""


def test_unique_code_retries_on_collision(tmp_path, monkeypatch):
    db = Database(path=str(tmp_path / "c.db"))
    db.execute("INSERT INTO classes (name, code) VALUES ('4E2', 'AAAA')")
    codes = iter(["AAAA", "BBBB"])
    monkeypatch.setattr("sms.web.services.classes.new_code", lambda: next(codes))
    assert unique_code(db) == "BBBB"

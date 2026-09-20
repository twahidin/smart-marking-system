import io, zipfile, pytest
from sms.files.intake import classify_uploads, input_kind, IntakeError


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in entries: z.writestr(n, b)
    return buf.getvalue()


def test_pages_only():
    it = classify_uploads([("p1.jpg", b"x"), ("p2.pdf", b"y")])
    assert [n for n, _ in it.pages] == ["p1.jpg", "p2.pdf"] and it.files == [] and input_kind(it) == "pages"


def test_files_and_pages_are_mixed():
    it = classify_uploads([("a.py", b"print(1)"), ("scan.png", b"z")])
    assert input_kind(it) == "mixed" and [n for n, _ in it.files] == ["a.py"]


def test_zip_is_expanded_and_junk_listed():
    z = _zip([("prog.py", b"x=1"), ("notes.txt", b"hi"), ("__MACOSX/._prog.py", b"junk"), ("sheet.xlsx", b"PK..")])
    it = classify_uploads([("work.zip", z)])
    assert sorted(n for n, _ in it.files) == ["prog.py", "sheet.xlsx"] and it.ignored == ["notes.txt"] and input_kind(it) == "files"


def test_zip_with_nothing_usable_rejected():
    with pytest.raises(IntakeError) as e:
        classify_uploads([("work.zip", _zip([("a.txt", b"")]))])
    assert e.value.code == "zip_nothing_usable" and "work.zip" in e.value.message


def test_bad_type_too_large_too_many():
    with pytest.raises(IntakeError) as e: classify_uploads([("a.exe", b"")])
    assert e.value.code == "bad_file" and "a.exe" in e.value.message
    with pytest.raises(IntakeError) as e: classify_uploads([("big.py", b"x" * (2 * 1024 * 1024 + 1))])
    assert e.value.code == "too_large"
    with pytest.raises(IntakeError) as e: classify_uploads([(f"f{i}.py", b"x") for i in range(13)])
    assert e.value.code == "too_many_files"


def test_zip_bomb_cap():
    big = _zip([("a.py", b"0" * (21 * 1024 * 1024))])
    with pytest.raises(IntakeError) as e: classify_uploads([("bomb.zip", big)])
    assert e.value.code == "zip_bomb"


# --- beyond the brief: the caps live here, so prove they hold inside a zip too ----------------

def test_zip_entries_obey_the_per_file_and_count_caps():
    with pytest.raises(IntakeError) as e:
        classify_uploads([("z.zip", _zip([("big.py", b"x" * (2 * 1024 * 1024 + 1))]))])
    assert e.value.code == "too_large" and "big.py" in e.value.message
    with pytest.raises(IntakeError) as e:
        classify_uploads([("z.zip", _zip([(f"f{i}.py", b"x") for i in range(13)]))])
    assert e.value.code == "too_many_files"


def test_caps_are_overridable():
    it = classify_uploads([("a.py", b"xxx")], max_files=1, max_file_bytes=3)
    assert [n for n, _ in it.files] == ["a.py"]
    with pytest.raises(IntakeError) as e:
        classify_uploads([("a.py", b"xxxx")], max_file_bytes=3)
    assert e.value.code == "too_large"
    with pytest.raises(IntakeError) as e:
        classify_uploads([("a.py", b"x"), ("b.py", b"x")], max_files=1)
    assert e.value.code == "too_many_files"


def test_zip_of_pages_is_expanded_and_nested_paths_are_flattened():
    it = classify_uploads([("z.zip", _zip([("scans/p1.png", b"x"), ("scans/p2.jpg", b"y")]))])
    assert [n for n, _ in it.pages] == ["p1.png", "p2.jpg"] and input_kind(it) == "pages"


def test_not_a_zip_is_a_bad_file():
    with pytest.raises(IntakeError) as e:
        classify_uploads([("broken.zip", b"not a zip at all")])
    assert e.value.code == "bad_file" and "broken.zip" in e.value.message


def test_extensions_are_case_insensitive():
    it = classify_uploads([("A.PY", b"x"), ("P.JPG", b"y")])
    assert [n for n, _ in it.files] == ["A.PY"] and [n for n, _ in it.pages] == ["P.JPG"]

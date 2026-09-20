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


# --- fix round 1 ------------------------------------------------------------------------------

def _zip_unreadable_method(inner="prog.py", body=b"x=1"):
    """A zip whose single entry claims compression method 99 — zipfile refuses to decompress it.
    Built normally, then the method field is patched in the local and central headers (zipfile
    validates the method on write, so it cannot be produced directly)."""
    raw = bytearray(_zip([(inner, body)]))
    local = raw.find(b"PK\x03\x04")
    central = raw.find(b"PK\x01\x02")
    raw[local + 8:local + 10] = (99).to_bytes(2, "little")
    raw[central + 10:central + 12] = (99).to_bytes(2, "little")
    return bytes(raw)


def _zip_damaged_stream(inner="prog.py"):
    """A deflated entry whose compressed stream is corrupted in place (offsets stay valid, so the
    archive opens and only the read fails)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(inner, b"x = 1\n" * 2000)
    raw = bytearray(buf.getvalue())
    local = raw.find(b"PK\x03\x04")
    name_len = int.from_bytes(raw[local + 26:local + 28], "little")
    extra_len = int.from_bytes(raw[local + 28:local + 30], "little")
    start = local + 30 + name_len + extra_len
    raw[start:start + 24] = b"\xff" * 24
    return bytes(raw)


def test_unreadable_zip_entry_is_a_bad_file():
    for data in (_zip_unreadable_method(), _zip_damaged_stream()):
        with pytest.raises(IntakeError) as e:
            classify_uploads([("work.zip", data)])
        assert e.value.code == "bad_file" and "work.zip" in e.value.message
        assert "could not be unpacked" in e.value.message


def test_decompressed_bytes_are_capped_across_the_whole_upload():
    # Each zip is legal on its own (well under the 20 MB per-archive budget) but together they
    # would hold more than the 50 MB request body cap in memory once unpacked.
    one = _zip([(f"p{i}.png", b"0" * 1_800_000) for i in range(10)])
    with pytest.raises(IntakeError) as e:
        classify_uploads([("a.zip", one), ("b.zip", one), ("c.zip", one)])
    assert e.value.code == "too_large" and e.value.message == "upload is over 50 MB once unpacked"


def test_aggregate_cap_is_overridable_and_counts_loose_uploads_too():
    with pytest.raises(IntakeError) as e:
        classify_uploads([("a.py", b"x" * 60), ("b.py", b"x" * 60)], max_total_bytes=100)
    assert e.value.code == "too_large" and "once unpacked" in e.value.message
    it = classify_uploads([("a.py", b"x" * 60)], max_total_bytes=100)
    assert it.total_bytes == 60


def test_a_big_page_inside_a_small_zip_is_refused():
    """A 19 MB PDF slips under the per-archive budget; the per-entry cap still catches it."""
    with pytest.raises(IntakeError) as e:
        classify_uploads([("z.zip", _zip([("scan.pdf", b"0" * (19 * 1024 * 1024))]))])
    assert e.value.code == "too_large" and "scan.pdf" in e.value.message


def test_duplicate_basenames_in_a_zip_are_suffixed():
    it = classify_uploads([("z.zip", _zip([("f1/prog.py", b"a"), ("f2/prog.py", b"b"), ("f3/prog.py", b"c")]))])
    assert [n for n, _ in it.files] == ["prog.py", "prog (2).py", "prog (3).py"]
    assert [b for _, b in it.files] == [b"a", b"b", b"c"]


def test_windows_entry_names_are_normalised():
    it = classify_uploads([("z.zip", _zip([("a\\win.py", b"x"), ("b\\scan.png", b"y")]))])
    assert [n for n, _ in it.files] == ["win.py"] and [n for n, _ in it.pages] == ["scan.png"]


def test_path_traversal_entries_are_listed_not_used():
    it = classify_uploads([("z.zip", _zip([("../evil.py", b"x"), ("/abs/evil2.py", b"y"), ("ok.py", b"z")]))])
    assert [n for n, _ in it.files] == ["ok.py"]
    assert it.ignored == ["../evil.py", "/abs/evil2.py"]


def test_too_many_files_names_the_file_and_beats_the_size_check():
    entries = [(f"f{i}.py", b"x") for i in range(12)] + [("last.py", b"x" * (2 * 1024 * 1024 + 1))]
    with pytest.raises(IntakeError) as e:
        classify_uploads(entries)
    assert e.value.code == "too_many_files" and e.value.name == "last.py"
    assert e.value.message == "last.py: too many files — the limit is 12 per submission"

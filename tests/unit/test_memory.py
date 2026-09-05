from sms.memory.db import Database
from sms.memory.extraction_cache import ExtractionCache


def test_database_creates_tables(tmp_path):
    db = Database(path=str(tmp_path / "sms.db"))
    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"marking_runs", "teacher_corrections", "rubric_notes", "exemplar_cases",
            "extraction_cache", "agent_metrics", "teacher_queue"} <= tables


def test_extraction_cache_roundtrip(tmp_path):
    db = Database(path=str(tmp_path / "sms.db"))
    cache = ExtractionCache(db)
    extracted = {"questions": [{"q_id": "q1", "transcribed_answer": "x=3",
                                "workings": "", "confidence": 0.9,
                                "needs_human_transcription": False}]}
    cache.put(hash_="abc123", subject="math", extracted=extracted)
    hit = cache.get(hash_="abc123", subject="math")
    assert hit["questions"][0]["transcribed_answer"] == "x=3"
    assert cache.get(hash_="abc123", subject="language") is None
    assert cache.get(hash_="nope", subject="math") is None


def test_extraction_cache_hash(tmp_path):
    db = Database(path=str(tmp_path / "sms.db"))
    cache = ExtractionCache(db)
    h1 = cache.hash_image(b"img-bytes")
    h2 = cache.hash_image(b"img-bytes")
    h3 = cache.hash_image(b"other")
    assert h1 == h2 and h1 != h3 and len(h1) == 64

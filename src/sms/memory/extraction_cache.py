import hashlib
import json
from typing import Any, Dict, Optional

from sms.memory.db import Database


class ExtractionCache:
    """Content-hash cache: SHA-256(image bytes) -> cached ExtractedScript JSON.

    Keyed by hash + subject because extraction prompts and question
    segmentation differ per subject.
    """

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def hash_image(image_bytes: bytes) -> str:
        return hashlib.sha256(image_bytes).hexdigest()

    def get(self, hash_: str, subject: str) -> Optional[Dict[str, Any]]:
        row = self.db.query(
            "SELECT extracted_json FROM extraction_cache WHERE hash = ? AND subject = ? AND schema_version = 1",
            (hash_, subject),
        )
        if not row:
            return None
        return json.loads(row[0]["extracted_json"])

    def put(self, hash_: str, subject: str, extracted: Dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO extraction_cache (hash, subject, schema_version, extracted_json) "
            "VALUES (?, ?, 1, ?)",
            (hash_, subject, json.dumps(extracted)),
        )

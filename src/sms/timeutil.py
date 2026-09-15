from datetime import datetime, timezone
from typing import Optional, Union


def iso_utc(value: Optional[Union[str, datetime]]) -> Optional[str]:
    """Normalise a DB timestamp (naive/aware datetime, or SQLite/ISO string) to 'YYYY-MM-DDTHH:MM:SSZ' UTC.

    SQLite returns timestamps as strings like 'YYYY-MM-DD HH:MM:SS[.ffffff]'; Postgres returns
    `datetime` objects (naive, stored as UTC). Both must render identically to API consumers.
    """
    if value is None:
        return None
    dt = value
    if isinstance(dt, str):
        s = dt.strip()
        if "T" not in s and " " in s:
            s = s.replace(" ", "T", 1)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

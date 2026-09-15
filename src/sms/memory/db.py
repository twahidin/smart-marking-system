import os
import re
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine

Params = Union[None, Sequence[Any], Dict[str, Any]]

_QMARK = re.compile(r"\?")


def _bind(sql: str, params: Params):
    """Accept `?` + tuple (legacy) or `:name` + dict. Returns (sql, dict)."""
    if params is None:
        return sql, {}
    if isinstance(params, dict):
        return sql, params
    seq = list(params)
    counter = iter(range(len(seq)))
    converted = _QMARK.sub(lambda _m: f":p{next(counter)}", sql)
    return converted, {f"p{i}": v for i, v in enumerate(seq)}


class _Executor:
    def __init__(self, conn: Connection):
        self._conn = conn

    def execute(self, sql: str, params: Params = None) -> int:
        sql, bound = _bind(sql, params)
        return self._conn.execute(text(sql), bound).rowcount

    def query(self, sql: str, params: Params = None) -> List[Dict[str, Any]]:
        sql, bound = _bind(sql, params)
        result = self._conn.execute(text(sql), bound)
        return [dict(row) for row in result.mappings().all()]

    def insert(self, sql: str, params: Params = None) -> int:
        sql, bound = _bind(sql, params)
        return int(self._conn.execute(text(sql), bound).scalar_one())


class Database:
    """SQLAlchemy Core wrapper. Same code path on SQLite (tests/local) and Postgres (Railway)."""

    def __init__(self, url: Optional[str] = None, *, path: Optional[str] = None, migrate: bool = True):
        if path is not None:
            url = f"sqlite:///{path}"
        url = url or os.environ.get("DATABASE_URL", "sqlite:///sms.db")
        self.url = self._normalise_url(url)
        self.is_sqlite = self.url.startswith("sqlite")
        kwargs: Dict[str, Any] = {"future": True, "pool_pre_ping": not self.is_sqlite}
        if self.is_sqlite:
            kwargs["connect_args"] = {"check_same_thread": False}
        self.engine: Engine = create_engine(self.url, **kwargs)
        if self.is_sqlite:
            @event.listens_for(self.engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _record):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=5000")
                cur.close()
        if migrate:
            from sms.memory.migrate import upgrade
            upgrade(self.engine)

    @staticmethod
    def _normalise_url(url: str) -> str:
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    def execute(self, sql: str, params: Params = None) -> int:
        with self.engine.begin() as conn:
            return _Executor(conn).execute(sql, params)

    def query(self, sql: str, params: Params = None) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            return _Executor(conn).query(sql, params)

    def insert(self, sql: str, params: Params = None) -> int:
        with self.engine.begin() as conn:
            return _Executor(conn).insert(sql, params)

    @contextmanager
    def transaction(self) -> Iterator[_Executor]:
        with self.engine.begin() as conn:
            yield _Executor(conn)

    def dispose(self) -> None:
        self.engine.dispose()

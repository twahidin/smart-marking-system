from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BASELINE_REVISION = "0001"


def _config(engine: Engine) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", str(engine.url).replace("%", "%%"))
    return cfg


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Apply all migrations using an existing engine (works for SQLite and Postgres)."""
    cfg = _config(engine)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        insp = inspect(conn)
        if insp.has_table("marking_runs") and not insp.has_table("alembic_version"):
            # A database created by the pre-Alembic CLI already has the baseline tables but no
            # version stamp; stamp it as 0001 so the baseline migration is not re-applied.
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, revision)

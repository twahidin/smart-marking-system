from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

config = context.config


def _run_with(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=None, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if connection is not None:
    _run_with(connection)
else:
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    with engine.connect() as conn:
        _run_with(conn)

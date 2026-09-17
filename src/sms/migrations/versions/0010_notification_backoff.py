"""notification retry bookkeeping: attempts and the earliest next try

A refused send used to be retried on every 10 s tick forever. These two columns let the flush back
off (10 s, doubling to an hour) and eventually give up, so one unreachable chat cannot keep the
outbox spinning.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as b:
        b.add_column(sa.Column("attempts", sa.Integer, nullable=False, server_default="0"))
        # 'YYYY-MM-DD HH:MM:SS' UTC, compared as text — NULL means "try on the next tick".
        b.add_column(sa.Column("next_attempt_at", sa.Text))


def downgrade() -> None:
    with op.batch_alter_table("notifications") as b:
        b.drop_column("next_attempt_at")
        b.drop_column("attempts")

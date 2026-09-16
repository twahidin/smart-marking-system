"""marking_runs.provider / model: which provider and model marked a script

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stamped by the worker (and `sms mark`) once a run finishes, so a marking record can say what
    # marked the script rather than what is configured today. NULL on runs from before this migration.
    with op.batch_alter_table("marking_runs") as b:
        b.add_column(sa.Column("provider", sa.Text))
        b.add_column(sa.Column("model", sa.Text))


def downgrade() -> None:
    with op.batch_alter_table("marking_runs") as b:
        b.drop_column("model")
        b.drop_column("provider")

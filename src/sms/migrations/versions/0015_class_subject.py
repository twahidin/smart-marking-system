"""A class can carry a subject so the school draws the right classroom tile.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("classes") as b:
        b.add_column(sa.Column("subject", sa.Text))   # NULL = derive from the latest class assignment


def downgrade() -> None:
    with op.batch_alter_table("classes") as b:
        b.drop_column("subject")

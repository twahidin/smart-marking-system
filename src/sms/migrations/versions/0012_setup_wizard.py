"""first-run setup: the teacher password can live on the website

The password used to come only from the TEACHER_PASSWORD variable, which the deployer had to read
off the Railway dashboard. A hash stored on the settings row lets the first visitor set it in a
wizard; the variable, when set, still wins (dashboard override / recovery).

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("settings") as b:
        b.add_column(sa.Column("teacher_password_hash", sa.Text))
        b.add_column(sa.Column("setup_completed_at", sa.DateTime))


def downgrade() -> None:
    with op.batch_alter_table("settings") as b:
        b.drop_column("setup_completed_at")
        b.drop_column("teacher_password_hash")

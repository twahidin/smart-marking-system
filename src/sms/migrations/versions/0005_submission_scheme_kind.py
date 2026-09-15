"""submissions.scheme_kind: the assignment type a script was uploaded against

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 'criteria' | 'mark_scheme' | 'rubric', copied from the assignment at upload so a retry can refuse to
    # mark with a different pipeline once the assignment has changed or gone. NULL on rows uploaded
    # before this migration that had no assignment (quick mark) or whose assignment is already gone.
    with op.batch_alter_table("submissions") as b:
        b.add_column(sa.Column("scheme_kind", sa.Text))
    op.execute(
        "UPDATE submissions SET scheme_kind = (SELECT t.scheme_kind FROM assignment_templates t WHERE t.id = submissions.assignment_id) "
        "WHERE assignment_id IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("submissions") as b:
        b.drop_column("scheme_kind")

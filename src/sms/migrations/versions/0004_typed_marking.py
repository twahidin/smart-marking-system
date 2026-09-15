"""typed marking: page kinds and deletion, per-assignment and global delete-pages flag, marks version

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL = follow the global default in settings.delete_pages_after_marking.
    with op.batch_alter_table("assignment_templates") as b:
        b.add_column(sa.Column("delete_pages_after_marking", sa.Boolean))
    with op.batch_alter_table("settings") as b:
        b.add_column(sa.Column("delete_pages_after_marking", sa.Boolean, nullable=False, server_default=sa.true()))
    # kind: 'student' (a submission's pages), 'paper' (an assignment's question paper) or 'scheme'
    # (an assignment's mark scheme / rubric). deleted_at is set when a student's pages are removed
    # after marking; paper and scheme pages are never deleted this way.
    with op.batch_alter_table("pages") as b:
        b.add_column(sa.Column("kind", sa.Text, nullable=False, server_default="student"))
        b.add_column(sa.Column("deleted_at", sa.DateTime))
    op.execute("UPDATE pages SET kind = 'paper' WHERE template_id IS NOT NULL AND submission_id IS NULL")
    # 1 = slice-1 final_marks_json (rows are questions, columns are criteria); 2 = per-part marks.
    with op.batch_alter_table("submissions") as b:
        b.add_column(sa.Column("marks_version", sa.Integer, nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("submissions") as b:
        b.drop_column("marks_version")
    with op.batch_alter_table("pages") as b:
        b.drop_column("deleted_at")
        b.drop_column("kind")
    with op.batch_alter_table("settings") as b:
        b.drop_column("delete_pages_after_marking")
    with op.batch_alter_table("assignment_templates") as b:
        b.drop_column("delete_pages_after_marking")

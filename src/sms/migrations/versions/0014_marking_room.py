"""The Marking Room: stage events from the pipeline, the submission's current stage, the reflection
window, and student corrections (one per part, re-marked by the AI, released by the teacher).

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marking_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.Text, nullable=False),          # read | mark | check | feedback | done
        sa.Column("kind", sa.Text, nullable=False),           # started | finished | note
        sa.Column("q_id", sa.Text),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_marking_events_submission", "marking_events", ["submission_id", "id"])
    with op.batch_alter_table("submissions") as b:
        b.add_column(sa.Column("stage", sa.Text))
    with op.batch_alter_table("settings") as b:
        b.add_column(sa.Column("reflect_days", sa.Integer, nullable=False, server_default="7"))
    with op.batch_alter_table("class_assignments") as b:
        b.add_column(sa.Column("reflect_days", sa.Integer))   # NULL = follow settings.reflect_days
    op.create_table(
        "student_corrections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("q_id", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("text", sa.Text),
        sa.Column("page_id", sa.Integer, sa.ForeignKey("pages.id", ondelete="SET NULL")),
        sa.Column("submitted_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("remark_run_id", sa.Text),
        sa.Column("remark_total", sa.Float),
        sa.Column("remark_max", sa.Float),
        sa.Column("remark_note", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="submitted"),
        sa.Column("teacher_total", sa.Float),
        sa.Column("teacher_reason", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("released_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ux_student_corrections_part", "student_corrections", ["submission_id", "q_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_student_corrections_part", table_name="student_corrections")
    op.drop_table("student_corrections")
    with op.batch_alter_table("class_assignments") as b:
        b.drop_column("reflect_days")
    with op.batch_alter_table("settings") as b:
        b.drop_column("reflect_days")
    with op.batch_alter_table("submissions") as b:
        b.drop_column("stage")
    op.drop_index("ix_marking_events_submission", table_name="marking_events")
    op.drop_table("marking_events")

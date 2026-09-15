"""assignment bank, job payloads, reflection runs, auto_reflect setting

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assignment_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=False, server_default=""),
        sa.Column("rubric_json", sa.Text, nullable=False),
        # 'criteria' (one list applied to every question), 'mark_scheme' (per-question answer + marks)
        # or 'rubric' (criteria x bands). questions_json/scheme_json hold the paper and its scheme.
        sa.Column("scheme_kind", sa.Text, nullable=False, server_default="criteria"),
        sa.Column("questions_json", sa.Text),
        sa.Column("scheme_json", sa.Text),
        sa.Column("times_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "reflection_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("lookback_days", sa.Integer, nullable=False),
        sa.Column("proposed_notes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("error", sa.Text),
    )
    # No FK: consistent with marking_runs.submission_id — a deleted template must not block anything.
    with op.batch_alter_table("submissions") as b:
        b.add_column(sa.Column("assignment_id", sa.Integer))
    # Question-paper pages belong to a template instead of a submission.
    with op.batch_alter_table("pages") as b:
        b.alter_column("submission_id", existing_type=sa.Integer, nullable=True)
        b.add_column(sa.Column("template_id", sa.Integer))
    with op.batch_alter_table("jobs") as b:
        b.add_column(sa.Column("payload_json", sa.Text))
    with op.batch_alter_table("settings") as b:
        b.add_column(sa.Column("auto_reflect", sa.Boolean, nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("settings") as b:
        b.drop_column("auto_reflect")
    with op.batch_alter_table("jobs") as b:
        b.drop_column("payload_json")
    # Template pages have no submission; drop them before submission_id becomes NOT NULL again.
    op.execute("DELETE FROM pages WHERE submission_id IS NULL")
    with op.batch_alter_table("pages") as b:
        b.drop_column("template_id")
        b.alter_column("submission_id", existing_type=sa.Integer, nullable=False)
    with op.batch_alter_table("submissions") as b:
        b.drop_column("assignment_id")
    op.drop_table("reflection_runs")
    op.drop_table("assignment_templates")

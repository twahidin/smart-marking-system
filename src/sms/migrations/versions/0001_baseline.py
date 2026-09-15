"""baseline: existing sms tables

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marking_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("rubric_json", sa.Text, nullable=False),
        sa.Column("extracted_json", sa.Text),
        sa.Column("marks_json", sa.Text),
        sa.Column("reviewed_json", sa.Text),
        sa.Column("feedback_json", sa.Text),
        sa.Column("final_status", sa.Text, nullable=False, server_default="running"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_marking_runs_run_id", "marking_runs", ["run_id"])
    op.create_table(
        "teacher_corrections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("q_id", sa.Text, nullable=False),
        sa.Column("agent_mark", sa.Integer),
        sa.Column("teacher_mark", sa.Integer),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "rubric_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("source_run_ids_json", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "exemplar_cases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("q_id", sa.Text, nullable=False),
        sa.Column("answer_text", sa.Text, nullable=False),
        sa.Column("awarded", sa.Integer, nullable=False),
        sa.Column("max_score", sa.Integer, nullable=False),
        sa.Column("why_it_matters", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "extraction_cache",
        sa.Column("hash", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("extracted_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("hash", "subject", "schema_version"),
    )
    op.create_table(
        "agent_metrics",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Text),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("agent_role", sa.Text, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "teacher_queue",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("q_id", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    for t in ("teacher_queue", "agent_metrics", "extraction_cache", "exemplar_cases",
              "rubric_notes", "teacher_corrections", "marking_runs"):
        op.drop_table(t)

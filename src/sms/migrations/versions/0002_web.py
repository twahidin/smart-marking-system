"""web: settings, submissions, pages, jobs, heartbeat; link runs/queue to submissions

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("base_url", sa.Text),
        sa.Column("extractor_model", sa.Text),
        sa.Column("api_key_enc", sa.Text),
        sa.Column("rpm_limit", sa.Integer, nullable=False, server_default="8"),
        sa.Column("confidence_threshold", sa.Float, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=False, server_default=""),
        sa.Column("rubric_json", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="uploaded"),
        sa.Column("run_id", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "pages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("sha256", sa.Text, nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("source_filename", sa.Text, nullable=False, server_default=""),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.UniqueConstraint("submission_id", "page_index", name="uq_pages_submission_index"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE")),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("not_before", sa.DateTime),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime),
    )
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])
    op.create_table(
        "worker_heartbeat",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("last_seen", sa.DateTime, nullable=False),
    )
    with op.batch_alter_table("marking_runs") as b:
        b.add_column(sa.Column("submission_id", sa.Integer))
        b.add_column(sa.Column("final_marks_json", sa.Text))
    with op.batch_alter_table("teacher_queue") as b:
        b.add_column(sa.Column("submission_id", sa.Integer))
    with op.batch_alter_table("teacher_corrections") as b:
        b.add_column(sa.Column("criterion_scores_json", sa.Text))


def downgrade() -> None:
    with op.batch_alter_table("teacher_corrections") as b:
        b.drop_column("criterion_scores_json")
    with op.batch_alter_table("teacher_queue") as b:
        b.drop_column("submission_id")
    with op.batch_alter_table("marking_runs") as b:
        b.drop_column("final_marks_json")
        b.drop_column("submission_id")
    op.drop_table("worker_heartbeat")
    op.drop_index("ix_jobs_status_created", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("pages")
    op.drop_table("submissions")
    op.drop_table("settings")

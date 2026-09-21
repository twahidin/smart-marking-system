"""file submissions, MT and Computing, per-subject models

Adds `submissions.input_kind` (pages vs a file upload), `assignment_templates.language` (Mother
Tongue's zh/ms/ta choice, NULL for every other subject), the `submission_files` table for uploaded
Python/Scratch/Excel files, and `subject_models` for a provider/model choice per subject.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("submissions") as b:
        b.add_column(sa.Column("input_kind", sa.Text, nullable=False, server_default="pages"))
    with op.batch_alter_table("assignment_templates") as b:
        b.add_column(sa.Column("language", sa.Text))  # zh | ms | ta, MT only
    op.create_table(
        "submission_files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),          # py | sb3 | xlsx
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("sha256", sa.Text, nullable=False),
        sa.Column("stored_path", sa.Text, nullable=False),
        sa.Column("text_rendered", sa.Text),
        # Timestamps are DateTime, as in 0001-0009: Postgres refuses a CURRENT_TIMESTAMP default on a
        # text column ("column is of type text but default expression is of type timestamp with time zone").
        sa.Column("deleted_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_submission_files_submission", "submission_files", ["submission_id"])
    op.create_table(
        "subject_models",
        sa.Column("subject", sa.Text, primary_key=True),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("extractor_model", sa.Text),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("subject_models")
    op.drop_index("ix_submission_files_submission", table_name="submission_files")
    op.drop_table("submission_files")
    with op.batch_alter_table("assignment_templates") as b:
        b.drop_column("language")
    with op.batch_alter_table("submissions") as b:
        b.drop_column("input_kind")

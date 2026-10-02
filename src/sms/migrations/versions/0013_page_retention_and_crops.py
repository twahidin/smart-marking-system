"""what is kept after marking: answer crops (default), whole pages, or nothing

`delete_pages_after_marking` (bool) becomes `page_retention`: 'crops' | 'pages' | 'none'. The old
boolean columns stay in place (unread) so a downgrade is trivial; their values seed the new ones.
`part_crops` holds the cropped answer region of each marked part.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("settings") as b:
        b.add_column(sa.Column("page_retention", sa.Text, nullable=False, server_default="crops"))
    with op.batch_alter_table("assignment_templates") as b:
        b.add_column(sa.Column("page_retention", sa.Text))  # NULL = follow the global default
    # Existing deployments: "delete after marking" keeps the (small) answer crops from now on; "keep" keeps whole pages.
    op.execute("UPDATE settings SET page_retention = CASE WHEN delete_pages_after_marking THEN 'crops' ELSE 'pages' END")
    op.execute("UPDATE assignment_templates SET page_retention = CASE delete_pages_after_marking WHEN 1 THEN 'crops' "
               "WHEN 0 THEN 'pages' ELSE NULL END")
    op.create_table(
        "part_crops",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("q_id", sa.Text, nullable=False),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("box_json", sa.Text),                 # [x0, y0, x1, y1] fractions actually cropped; NULL = whole page
        sa.Column("whole_page", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("sha256", sa.Text, nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("deleted_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_part_crops_submission", "part_crops", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_part_crops_submission", table_name="part_crops")
    op.drop_table("part_crops")
    with op.batch_alter_table("assignment_templates") as b:
        b.drop_column("page_retention")
    with op.batch_alter_table("settings") as b:
        b.drop_column("page_retention")

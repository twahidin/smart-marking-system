"""classes, students, class assignments; submissions linked to a class assignment and a student

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        # 4 chars from 23456789ABCDEFGHJKMNPQRSTUVWXYZ; the student link is /c/<code>
        sa.Column("code", sa.Text, nullable=False, unique=True),
        sa.Column("archived_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "students",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("class_id", sa.Integer, sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reg_no", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("last_seen_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("class_id", "reg_no", name="uq_students_class_reg"),
    )
    op.create_table(
        "class_assignments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("class_id", sa.Integer, sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        # the bank template; deliberately not a FK so a forced template delete leaves the row (see delete guard)
        sa.Column("template_id", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("due_at", sa.DateTime),
        # draft (invisible to students) -> open (hand-in allowed) -> released (feedback visible)
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("allow_student_uploads", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("released_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    with op.batch_alter_table("submissions") as b:
        b.add_column(sa.Column("class_assignment_id", sa.Integer))
        b.add_column(sa.Column("student_id", sa.Integer))
        b.add_column(sa.Column("handed_in_at", sa.DateTime))
        b.add_column(sa.Column("source", sa.Text, nullable=False, server_default="teacher"))
    # one hand-in per student per class assignment; hand_in relies on this under concurrent taps
    op.create_index("uq_submissions_student_assignment", "submissions", ["class_assignment_id", "student_id"], unique=True,
                    postgresql_where=sa.text("class_assignment_id IS NOT NULL AND student_id IS NOT NULL"),
                    sqlite_where=sa.text("class_assignment_id IS NOT NULL AND student_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("uq_submissions_student_assignment", table_name="submissions")
    with op.batch_alter_table("submissions") as b:
        b.drop_column("source")
        b.drop_column("handed_in_at")
        b.drop_column("student_id")
        b.drop_column("class_assignment_id")
    op.drop_table("class_assignments")
    op.drop_table("students")
    op.drop_table("classes")

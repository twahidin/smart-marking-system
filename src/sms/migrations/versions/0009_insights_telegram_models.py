"""insights, telegram notifications, per-assignment models, custom model lists

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("settings") as b:
        b.add_column(sa.Column("telegram_bot_token_enc", sa.Text))
        b.add_column(sa.Column("telegram_chat_id", sa.Text))
        b.add_column(sa.Column("telegram_instant", sa.Boolean, nullable=False, server_default=sa.true()))
        b.add_column(sa.Column("telegram_daily_time", sa.Text, nullable=False, server_default="07:00"))
        b.add_column(sa.Column("timezone", sa.Text, nullable=False, server_default="Asia/Singapore"))
        b.add_column(sa.Column("app_url", sa.Text))
        b.add_column(sa.Column("telegram_daily_last_sent", sa.Text))
        b.add_column(sa.Column("telegram_update_offset", sa.Integer, nullable=False, server_default="0"))
    # NULL provider = follow Settings
    with op.batch_alter_table("assignment_templates") as b:
        b.add_column(sa.Column("provider", sa.Text))
        b.add_column(sa.Column("model", sa.Text))
        b.add_column(sa.Column("extractor_model", sa.Text))
    with op.batch_alter_table("class_assignments") as b:
        b.add_column(sa.Column("last_done_notified_at", sa.DateTime))
    op.create_table(
        "custom_models",
        sa.Column("provider", sa.Text, primary_key=True),
        sa.Column("model_id", sa.Text, primary_key=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("vision", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "assignment_insights",
        sa.Column("class_assignment_id", sa.Integer, sa.ForeignKey("class_assignments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("stats_json", sa.Text, nullable=False),
        sa.Column("report_json", sa.Text),
        sa.Column("n_marked", sa.Integer, nullable=False, server_default="0"),
        sa.Column("provider", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("generated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("error", sa.Text),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("class_assignment_id", sa.Integer),
        sa.Column("payload_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_notifications_unsent", "notifications", ["sent_at", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_unsent", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("assignment_insights")
    op.drop_table("custom_models")
    with op.batch_alter_table("class_assignments") as b:
        b.drop_column("last_done_notified_at")
    with op.batch_alter_table("assignment_templates") as b:
        b.drop_column("extractor_model"); b.drop_column("model"); b.drop_column("provider")
    with op.batch_alter_table("settings") as b:
        for c in ("telegram_update_offset", "telegram_daily_last_sent", "app_url", "timezone", "telegram_daily_time",
                  "telegram_instant", "telegram_chat_id", "telegram_bot_token_enc"):
            b.drop_column(c)

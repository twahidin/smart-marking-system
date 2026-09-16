"""provider_keys: one encrypted API key per provider, so switching provider switches key

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_keys",
        sa.Column("provider", sa.Text, primary_key=True),
        sa.Column("api_key_enc", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    # The single key stored so far belonged to whichever provider was selected; move it there.
    op.execute("INSERT INTO provider_keys (provider, api_key_enc) "
               "SELECT provider, api_key_enc FROM settings WHERE id = 1 AND api_key_enc IS NOT NULL")
    op.execute("UPDATE settings SET api_key_enc = NULL WHERE id = 1")


def downgrade() -> None:
    op.execute("UPDATE settings SET api_key_enc = (SELECT k.api_key_enc FROM provider_keys k WHERE k.provider = settings.provider) "
               "WHERE id = 1")
    op.drop_table("provider_keys")

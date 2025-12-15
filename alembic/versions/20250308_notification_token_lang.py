"""Add language to notification device tokens.

Revision ID: 20250308_notification_token_lang
Revises: 20250306_add_notification_tokens
Create Date: 2025-03-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20250308_notification_token_lang"
down_revision = "20250306_add_notification_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notification_device_tokens", sa.Column("language", sa.String(length=8), nullable=False, server_default="ru"))


def downgrade() -> None:
    op.drop_column("notification_device_tokens", "language")

"""Create notification device tokens table.

Revision ID: 20250306_add_notification_tokens
Revises: 20250304_add_cards_and_user_meta
Create Date: 2025-03-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20250306_add_notification_tokens"
down_revision = "20250304_add_cards_and_user_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_device_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_token", sa.String(length=255), nullable=False, unique=True),
        sa.Column("device_type", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notification_device_tokens_user_id", "notification_device_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_device_tokens_user_id", table_name="notification_device_tokens")
    op.drop_table("notification_device_tokens")

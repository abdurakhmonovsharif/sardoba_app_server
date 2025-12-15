"""Add user notifications table.

Revision ID: 20250410_add_user_notifications
Revises: 1b6fa207dc8d
Create Date: 2025-04-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20250410_add_user_notifications"
down_revision = "1b6fa207dc8d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False, server_default=sa.text("'ru'")),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_notifications_user_id", "user_notifications", ["user_id"])
    op.alter_column("notification_device_tokens", "device_token", nullable=True)
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "deleted_phones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("real_phone", sa.String(length=20), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_deleted_phones_real_phone", "deleted_phones", ["real_phone"])
    op.create_index("ix_deleted_phones_user_id", "deleted_phones", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_notifications_user_id", table_name="user_notifications")
    op.drop_table("user_notifications")
    op.alter_column("notification_device_tokens", "device_token", nullable=False)
    op.drop_index("ix_deleted_phones_user_id", table_name="deleted_phones")
    op.drop_index("ix_deleted_phones_real_phone", table_name="deleted_phones")
    op.drop_table("deleted_phones")
    op.drop_column("users", "deleted_at")

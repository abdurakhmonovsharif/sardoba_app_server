"""Add notification reference to user notifications.

Revision ID: 20260113_add_user_notification_reference
Revises: 20251205_expand_card_number
Create Date: 2026-01-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260113_add_user_notification_reference"
down_revision = "20251205_expand_card_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_notifications",
        sa.Column(
            "notification_id",
            sa.Integer(),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_user_notifications_notification_id",
        "user_notifications",
        ["notification_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_notifications_notification_id", table_name="user_notifications")
    op.drop_column("user_notifications", "notification_id")

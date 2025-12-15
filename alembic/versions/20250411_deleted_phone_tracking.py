"""Track deleted phone metadata.

Revision ID: 20250411_deleted_phone_tracking
Revises: 20250410_add_user_notifications
Create Date: 2025-04-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20250411_deleted_phone_tracking"
down_revision = "20250410_add_user_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.drop_index("ix_deleted_phones_user_id", table_name="deleted_phones")
    op.drop_index("ix_deleted_phones_real_phone", table_name="deleted_phones")
    op.drop_table("deleted_phones")
    op.drop_column("users", "deleted_at")

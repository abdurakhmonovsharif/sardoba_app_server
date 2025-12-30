"""Add giftget flag to users.

Revision ID: 20250312_add_user_giftget
Revises: 20250301_add_iiko_identifiers
Create Date: 2025-03-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20250312_add_user_giftget"
down_revision = "d9cc0ac0421f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("giftget", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "giftget")

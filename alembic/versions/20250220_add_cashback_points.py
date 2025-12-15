"""Add cashback balance points column.

Revision ID: 20250220_add_cashback_points
Revises: 20241118_add_user_photo_url
Create Date: 2025-02-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20250220_add_cashback_points"
down_revision = "20241118_add_user_photo_url"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cashback_balances",
        sa.Column("points", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("cashback_balances", "points")

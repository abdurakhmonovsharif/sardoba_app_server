"""Merge existing heads into a single chain.

Revision ID: 20250226_merge_heads
Revises: 20241118_add_user_level, 20250220_add_cashback_points
Create Date: 2025-11-26 15:05:00.000000
"""

from alembic import op


revision = "20250226_merge_heads"
down_revision = ("20241118_add_user_level", "20250220_add_cashback_points")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # no schema changes; merge migration only
    pass


def downgrade() -> None:
    pass

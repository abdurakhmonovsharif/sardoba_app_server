"""Add Iiko event id to cashback transactions.

Revision ID: 20241201_add_cashback_event_id
Revises: 20250304_add_cards_and_user_meta
Create Date: 2024-12-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20241201_add_cashback_event_id"
down_revision = "20250304_add_cards_and_user_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cashback_transactions",
        sa.Column("iiko_event_id", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_cashback_transactions_iiko_event_id",
        "cashback_transactions",
        ["iiko_event_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_cashback_transactions_iiko_event_id", "cashback_transactions", type_="unique")
    op.drop_column("cashback_transactions", "iiko_event_id")

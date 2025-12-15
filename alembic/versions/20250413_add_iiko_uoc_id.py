"""Add Iiko uoc_id reference on cashback transactions."""

from alembic import op
import sqlalchemy as sa

revision = "20250413_add_iiko_uoc_id"
down_revision = "20250412_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cashback_transactions",
        sa.Column("iiko_uoc_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cashback_transactions", "iiko_uoc_id")

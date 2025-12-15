"""Widen card_number column to match incoming values."""

from alembic import op
import sqlalchemy as sa

revision = "20251205_expand_card_number"
down_revision = "20251202_pending_iiko_update"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "cards",
        "card_number",
        type_=sa.String(length=32),
        existing_type=sa.String(length=16),
    )


def downgrade() -> None:
    op.alter_column(
        "cards",
        "card_number",
        type_=sa.String(length=16),
        existing_type=sa.String(length=32),
    )

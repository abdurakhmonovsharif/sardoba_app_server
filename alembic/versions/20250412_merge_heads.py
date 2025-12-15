"""Merge Alembic heads so upgrades can use a single target."""

from alembic import op

revision = "20250412_merge_heads"
down_revision = (
    "20241201_add_cashback_event_id",
    "20250411_deleted_phone_tracking",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

"""Add pending Iiko profile update payload on users."""

from alembic import op
import sqlalchemy as sa

revision = "20251202_pending_iiko_update"
down_revision = "20250413_add_iiko_uoc_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("pending_iiko_profile_update", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "pending_iiko_profile_update")

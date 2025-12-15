"""Add Iiko identifiers to users.

Revision ID: 20250301_add_iiko_identifiers
Revises: 20250226_merge_heads
Create Date: 2025-03-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20250301_add_iiko_identifiers"
down_revision = "20250226_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS iiko_wallet_id VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS iiko_customer_id VARCHAR(64)"
    )
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE users ADD CONSTRAINT uq_users_iiko_wallet_id UNIQUE (iiko_wallet_id);
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE users ADD CONSTRAINT uq_users_iiko_customer_id UNIQUE (iiko_customer_id);
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_iiko_customer_id")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_iiko_wallet_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS iiko_customer_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS iiko_wallet_id")

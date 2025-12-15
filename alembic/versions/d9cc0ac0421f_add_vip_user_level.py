"""add vip user level

Revision ID: d9cc0ac0421f
Revises: 20251205_expand_card_number
Create Date: 2025-12-05 10:14:57.805852
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd9cc0ac0421f'
down_revision = '20251205_expand_card_number'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumtypid = 'user_level'::regtype
                AND enumlabel = 'VIP'
            ) THEN
                ALTER TYPE user_level ADD VALUE 'VIP';
            END IF;
        END
        $$;
        """
    )


def downgrade():
    raise NotImplementedError("Downgrading user_level enums is not supported")

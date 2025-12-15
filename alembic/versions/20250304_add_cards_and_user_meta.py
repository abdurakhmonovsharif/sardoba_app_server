"""Add cards table and user metadata.

Revision ID: 20250304_add_cards_and_user_meta
Revises: 20250301_add_iiko_identifiers
Create Date: 2025-03-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20250304_add_cards_and_user_meta"
down_revision = "20250301_add_iiko_identifiers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(320)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR(16)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            card_number VARCHAR(16) UNIQUE NOT NULL,
            card_track VARCHAR(64) UNIQUE NOT NULL,
            iiko_card_id VARCHAR(64),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_cards_user_id ON cards(user_id)")
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE users ADD CONSTRAINT uq_users_email UNIQUE (email);
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cards_user_id")
    op.execute("DROP TABLE IF EXISTS cards")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_deleted")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS gender")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_email")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email")

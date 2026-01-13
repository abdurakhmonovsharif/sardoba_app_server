"""Merge notification heads

Revision ID: ba8f4f58e6fd
Revises: 20250312_add_user_giftget, 20260113_add_user_notification_reference
Create Date: 2026-01-12 23:33:32.808436
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ba8f4f58e6fd'
down_revision = ('20250312_add_user_giftget', '20260113_add_user_notification_reference')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

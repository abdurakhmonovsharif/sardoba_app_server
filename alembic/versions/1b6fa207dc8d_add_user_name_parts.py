"""Add user name parts

Revision ID: 1b6fa207dc8d
Revises: 20250308_notification_token_lang
Create Date: 2025-11-27 17:54:51.167438
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b6fa207dc8d'
down_revision = '20250308_notification_token_lang'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("surname", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("middle_name", sa.String(length=100), nullable=True))


def downgrade():
    op.drop_column("users", "middle_name")
    op.drop_column("users", "surname")

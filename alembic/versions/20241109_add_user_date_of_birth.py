"""Add user date_of_birth field.

Revision ID: 20241109_add_user_date_of_birth
Revises: 20241020_cashback_wallets
Create Date: 2024-11-09 14:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20241109_add_user_date_of_birth"
down_revision = "20241020_cashback_wallets"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("users", "date_of_birth")

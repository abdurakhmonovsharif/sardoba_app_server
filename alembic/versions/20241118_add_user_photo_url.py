"""Add users.profile_photo_url column.

Revision ID: 20241118_add_user_photo_url
Revises: 20241109_add_user_date_of_birth
Create Date: 2024-11-18 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20241118_add_user_photo_url"
down_revision = "20241109_add_user_date_of_birth"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("profile_photo_url", sa.String(length=512), nullable=True))


def downgrade():
    op.drop_column("users", "profile_photo_url")

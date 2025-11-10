"""Add user level column.

Revision ID: 20241118_add_user_level
Revises: 20241118_add_user_photo_url
Create Date: 2024-11-18 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20241118_add_user_level"
down_revision = "20241118_add_user_photo_url"
branch_labels = None
depends_on = None


def upgrade():
    user_level_enum = sa.Enum("SILVER", "GOLD", "PREMIUM", name="user_level")
    user_level_enum.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("level", user_level_enum, nullable=False, server_default="SILVER"))


def downgrade():
    op.drop_column("users", "level")
    user_level_enum = sa.Enum("SILVER", "GOLD", "PREMIUM", name="user_level")
    user_level_enum.drop(op.get_bind(), checkfirst=True)

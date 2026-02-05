"""Add iiko sync jobs queue table.

Revision ID: 20260205_add_iiko_sync_jobs
Revises: 20260113_add_user_notification_reference
Create Date: 2026-02-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260205_add_iiko_sync_jobs"
down_revision = "20260113_add_user_notification_reference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iiko_sync_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_owner", sa.String(length=64), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_iiko_sync_jobs_user_id",
        "iiko_sync_jobs",
        ["user_id"],
    )
    op.create_index(
        "ix_iiko_sync_jobs_phone",
        "iiko_sync_jobs",
        ["phone"],
    )
    op.create_index(
        "ix_iiko_sync_jobs_status_next_retry_at",
        "iiko_sync_jobs",
        ["status", "next_retry_at"],
    )
    op.create_index(
        "ix_iiko_sync_jobs_user_operation",
        "iiko_sync_jobs",
        ["user_id", "operation"],
    )


def downgrade() -> None:
    op.drop_index("ix_iiko_sync_jobs_user_operation", table_name="iiko_sync_jobs")
    op.drop_index("ix_iiko_sync_jobs_status_next_retry_at", table_name="iiko_sync_jobs")
    op.drop_index("ix_iiko_sync_jobs_phone", table_name="iiko_sync_jobs")
    op.drop_index("ix_iiko_sync_jobs_user_id", table_name="iiko_sync_jobs")
    op.drop_table("iiko_sync_jobs")

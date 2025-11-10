"""Introduce cashback balances and transaction history tables.

Revision ID: 20241020_cashback_wallets
Revises: 20240101_initial
Create Date: 2024-10-20 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20241020_cashback_wallets"
down_revision = "20240101_initial"
branch_labels = None
depends_on = None


def upgrade():
    cashback_source_enum = postgresql.ENUM(
        "QR",
        "ORDER",
        "MANUAL",
        name="cashback_source",
        create_type=False,
    )

    op.create_table(
        "cashback_balances",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("balance", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "cashback_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("source", cashback_source_enum, nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_cashback_transactions_user_id", "cashback_transactions", ["user_id"])

    op.execute(
        """
        INSERT INTO cashback_balances (user_id, balance, created_at, updated_at)
        SELECT id, cashback_balance, now(), now()
        FROM users
        """
    )

    op.execute(
        """
        INSERT INTO cashback_transactions (id, user_id, amount, branch_id, source, balance_after, created_at)
        SELECT
            id,
            user_id,
            amount,
            branch_id,
            source,
            SUM(amount) OVER (PARTITION BY user_id ORDER BY created_at, id),
            created_at
        FROM cashbacks
        ORDER BY created_at, id
        """
    )

    op.drop_index(op.f("ix_cashbacks_user_id"), table_name="cashbacks")
    op.drop_table("cashbacks")

    op.drop_column("users", "cashback_balance")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            SELECT setval(
                pg_get_serial_sequence('cashback_transactions', 'id'),
                COALESCE((SELECT MAX(id) FROM cashback_transactions), 0) + 1,
                false
            )
            """
        )


def downgrade():
    cashback_source_enum = postgresql.ENUM(
        "QR",
        "ORDER",
        "MANUAL",
        name="cashback_source",
        create_type=False,
    )

    op.add_column(
        "users",
        sa.Column("cashback_balance", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )

    op.execute(
        """
        UPDATE users
        SET cashback_balance = cb.balance
        FROM cashback_balances cb
        WHERE cb.user_id = users.id
        """
    )

    op.create_table(
        "cashbacks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("source", cashback_source_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(op.f("ix_cashbacks_user_id"), "cashbacks", ["user_id"])

    op.execute(
        """
        INSERT INTO cashbacks (id, user_id, amount, branch_id, source, created_at)
        SELECT id, user_id, amount, branch_id, source, created_at
        FROM cashback_transactions
        ORDER BY created_at, id
        """
    )

    op.drop_index("ix_cashback_transactions_user_id", table_name="cashback_transactions")
    op.drop_table("cashback_transactions")
    op.drop_table("cashback_balances")

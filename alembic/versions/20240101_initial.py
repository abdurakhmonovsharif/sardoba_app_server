"""initial schema

Revision ID: 20240101_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20240101_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TYPE IF EXISTS auth_action CASCADE")
    op.execute("DROP TYPE IF EXISTS auth_actor_type CASCADE")
    op.execute("DROP TYPE IF EXISTS cashback_source CASCADE")
    op.execute("DROP TYPE IF EXISTS staff_role CASCADE")

    staff_role_enum = sa.Enum("MANAGER", "WAITER", name="staff_role")
    cashback_source_enum = sa.Enum("QR", "ORDER", "MANUAL", name="cashback_source")
    auth_actor_type_enum = sa.Enum("CLIENT", "STAFF", name="auth_actor_type")
    auth_action_enum = sa.Enum(
        "LOGIN", "LOGOUT", "OTP_REQUEST", "OTP_VERIFICATION", "FAILED_LOGIN", name="auth_action"
    )

    op.create_table(
        "staff",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", staff_role_enum, nullable=False, server_default="WAITER"),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("referral_code", sa.String(length=12), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            server_onupdate=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_staff_phone"), "staff", ["phone"], unique=True)
    op.create_index(op.f("ix_staff_referral_code"), "staff", ["referral_code"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("waiter_id", sa.Integer(), nullable=True),
        sa.Column("cashback_balance", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            server_onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["waiter_id"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=True)

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_otp_codes_code"), "otp_codes", ["code"])
    op.create_index(op.f("ix_otp_codes_phone"), "otp_codes", ["phone"])
    op.create_index(op.f("ix_otp_codes_ip"), "otp_codes", ["ip"])

    op.create_table(
        "news",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "cashbacks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("source", cashback_source_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cashbacks_user_id"), "cashbacks", ["user_id"])

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"])

    op.create_table(
        "auth_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_type", auth_actor_type_enum, nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("action", auth_action_enum, nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("auth_logs")
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_cashbacks_user_id"), table_name="cashbacks")
    op.drop_table("cashbacks")
    op.drop_table("categories")
    op.drop_table("notifications")
    op.drop_table("news")
    op.drop_index(op.f("ix_otp_codes_ip"), table_name="otp_codes")
    op.drop_index(op.f("ix_otp_codes_phone"), table_name="otp_codes")
    op.drop_index(op.f("ix_otp_codes_code"), table_name="otp_codes")
    op.drop_table("otp_codes")
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_staff_referral_code"), table_name="staff")
    op.drop_index(op.f("ix_staff_phone"), table_name="staff")
    op.drop_table("staff")

    op.execute("DROP TYPE IF EXISTS auth_action")
    op.execute("DROP TYPE IF EXISTS auth_actor_type")
    op.execute("DROP TYPE IF EXISTS cashback_source")
    op.execute("DROP TYPE IF EXISTS staff_role")

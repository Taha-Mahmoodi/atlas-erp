"""auth

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-12

core_users (auth principals) and core_refresh_sessions (refresh-token server state)
per D-008. Both carry the D-007 composite-FK backstop: tenant_id anchored to
adm_tenants, and refresh sessions' (tenant_id, user_id) anchored to core_users'
UNIQUE(tenant_id, id). Constraint names are spelled out per the D-022 convention so
SQLite batch mode can drop them later.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "core_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("token_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_core_users_tenant_id_adm_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_users")),
        sa.UniqueConstraint("tenant_id", "email", name="uq_core_users_tenant_id_email"),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_core_users_tenant_id")),
    )
    op.create_index(op.f("ix_core_users_tenant_id"), "core_users", ["tenant_id"])

    op.create_table(
        "core_refresh_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("current_jti_hash", sa.String(length=64), nullable=False),
        sa.Column("prev_jti_hash", sa.String(length=64), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_core_refresh_sessions_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["core_users.tenant_id", "core_users.id"],
            name=op.f("fk_core_refresh_sessions_tenant_id_core_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_refresh_sessions")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_core_refresh_sessions_tenant_id")),
    )
    op.create_index(
        op.f("ix_core_refresh_sessions_tenant_id"), "core_refresh_sessions", ["tenant_id"]
    )
    op.create_index(
        "ix_core_refresh_sessions_tenant_id_user_id",
        "core_refresh_sessions",
        ["tenant_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_refresh_sessions_tenant_id_user_id", table_name="core_refresh_sessions"
    )
    op.drop_index(
        op.f("ix_core_refresh_sessions_tenant_id"), table_name="core_refresh_sessions"
    )
    op.drop_table("core_refresh_sessions")
    op.drop_index(op.f("ix_core_users_tenant_id"), table_name="core_users")
    op.drop_table("core_users")

"""core api keys

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-14

core_api_keys — the Phase 18 machine credential (spec Q1). Mirrors
core_refresh_sessions: hashed secret, expiry, revocation, with the D-007
composite-FK backstop on both tenant_id and (tenant_id, user_id). `scopes` uses
the shared JSON_VARIANT (JSONB on Postgres, JSON elsewhere) so no second JSON
convention enters the schema (D-003). Constraint names are spelled out per the
D-022 convention so SQLite batch mode can drop them later.
"""

import sqlalchemy as sa
from alembic import op

from app.core.models import JSON_VARIANT

# revision identifiers, used by Alembic.
revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "core_api_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("prefix", sa.String(length=80), nullable=False),
        sa.Column("secret_sha256", sa.String(length=64), nullable=False),
        sa.Column("scopes", JSON_VARIANT, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_core_api_keys_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["core_users.tenant_id", "core_users.id"],
            name="fk_core_api_keys_tenant_id_core_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_core_api_keys"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_core_api_keys_tenant_id"),
        sa.UniqueConstraint("secret_sha256", name="uq_core_api_keys_secret_sha256"),
    )
    op.create_index("ix_core_api_keys_tenant_id", "core_api_keys", ["tenant_id"])
    op.create_index(
        "ix_core_api_keys_tenant_id_user_id", "core_api_keys", ["tenant_id", "user_id"]
    )


def downgrade() -> None:
    op.drop_table("core_api_keys")

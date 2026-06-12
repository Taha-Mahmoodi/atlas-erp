"""tenants

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-12

adm_tenants (tenancy root) and adm_tenant_settings (first tenant-scoped table,
D-007 FK backstop: tenant_id anchored to the root). Constraint names are spelled
out per the D-022 naming convention so SQLite batch mode can drop them later.
"""

import sqlalchemy as sa
from alembic import op

from app.core.models import JSON_VARIANT

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "adm_tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_adm_tenants")),
        sa.UniqueConstraint("slug", name=op.f("uq_adm_tenants_slug")),
    )
    op.create_table(
        "adm_tenant_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", JSON_VARIANT, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_adm_tenant_settings_tenant_id_adm_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_adm_tenant_settings")),
        sa.UniqueConstraint("tenant_id", "key", name=op.f("uq_adm_tenant_settings_tenant_id_key")),
    )
    op.create_index(
        op.f("ix_adm_tenant_settings_tenant_id"), "adm_tenant_settings", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_adm_tenant_settings_tenant_id"), table_name="adm_tenant_settings")
    op.drop_table("adm_tenant_settings")
    op.drop_table("adm_tenants")

"""industry configuration layer: core custom-field registry + applied-template record

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-14

PLAN 14.1 / D-016 / D-060 — the INDUSTRY CONFIGURATION LAYER schema. Creates TWO tables and alters
NOTHING pre-existing (no trigger-bearing table is touched, D-022, so no trigger-recreation concern).
All DDL is portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap).

- core_custom_field_defs (D-016): the CORE-owned typed custom-field registry. One row per registered
  field for an entity (entity_key like 'inventory.item', field_key '^[a-z][a-z0-9_]{0,49}$',
  data_type STRING|NUMBER|DECIMAL|BOOL|DATE, is_required, is_active soft-deactivation, default_value
  stored portably as a string). UNIQUE(tenant_id, entity_key, field_key) is the natural key the
  loader's get-or-create + the owning-module validate read on; (tenant_id, entity_key) index serves
  the "active defs for this entity" read. The custom_fields JSON column itself is added per-entity
  as models opt in over time (custom_fields_column()) — NOT retrofitted here.

- ind_tenant_industry_configs (D-060): the INDUSTRY-owned applied-template record. One row per
  tenant (UNIQUE(tenant_id)) recording which template the tenant applied + when — the onboarding
  record and the loader's idempotency anchor.

Both follow the D-007 composite-tenant-FK backstop (tenant_fk to adm_tenants) and the explicit
tenant_id index TenantMixin declares (index=True).
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "core_custom_field_defs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entity_key", sa.String(length=80), nullable=False),
        sa.Column("field_key", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("data_type", sa.String(length=10), nullable=False),
        sa.Column(
            "is_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("default_value", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_core_custom_field_defs_tenant_id_adm_tenants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_core_custom_field_defs"),
        sa.UniqueConstraint(
            "tenant_id",
            "entity_key",
            "field_key",
            name="uq_core_custom_field_defs_tenant_id_entity_key_field_key",
        ),
    )
    op.create_index(
        "ix_core_custom_field_defs_tenant_id", "core_custom_field_defs", ["tenant_id"]
    )
    op.create_index(
        "ix_core_custom_field_defs_tenant_id_entity_key",
        "core_custom_field_defs",
        ["tenant_id", "entity_key"],
    )

    op.create_table(
        "ind_tenant_industry_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("template_name", sa.String(length=60), nullable=False),
        sa.Column(
            "applied_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_ind_tenant_industry_configs_tenant_id_adm_tenants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ind_tenant_industry_configs"),
        sa.UniqueConstraint(
            "tenant_id", name="uq_ind_tenant_industry_configs_tenant_id"
        ),
    )
    op.create_index(
        "ix_ind_tenant_industry_configs_tenant_id",
        "ind_tenant_industry_configs",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ind_tenant_industry_configs_tenant_id",
        table_name="ind_tenant_industry_configs",
    )
    op.drop_table("ind_tenant_industry_configs")
    op.drop_index(
        "ix_core_custom_field_defs_tenant_id_entity_key",
        table_name="core_custom_field_defs",
    )
    op.drop_index(
        "ix_core_custom_field_defs_tenant_id", table_name="core_custom_field_defs"
    )
    op.drop_table("core_custom_field_defs")

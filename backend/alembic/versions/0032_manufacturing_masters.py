"""manufacturing master data: work centres, multi-level versioned BOMs, routings

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-13

PLAN 8.1 — opens the manufacturing module with the PP MASTER DATA (parity: BOMs multi-level +
versioned, work centers, routings — all FULL). Creates FIVE tables and alters NOTHING — no
trigger-bearing table is touched (D-022), so there is no trigger-recreation concern. All DDL is
portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap). The QuantityType
columns render as NUMERIC(18,6) on Postgres / INTEGER micro-units on SQLite (D-015) via the model
column type — imported from app.core.money so the revision stays dialect-clean.

- mfg_work_centers: the production-resource master. UNIQUE(tenant_id, code) (user-supplied code, no
  auto-number); CHECKs capacity >= 0 and efficiency > 0; (tenant, is_active) filter index. The
  nullable cost_center_id is an OPAQUE finance id (D-029) — no FK.
- mfg_boms: the versioned BOM header. UNIQUE(tenant_id, item_id, version) (the (item, version)
  identity, D-047); CHECK base_quantity > 0; (tenant, item_id, status) resolver/filter index. The
  item_id/uom_id are OPAQUE inventory ids (D-029) — no FK to inv_items/inv_uoms.
- mfg_bom_components: one direct component per line. Composite FK to mfg_boms; CHECKs quantity_per >
  0 and scrap_percent >= 0; UNIQUE(tenant, bom_id, line_number); (tenant, bom_id) read index. The
  component_item_id/uom_id are OPAQUE inventory ids (D-029).
- mfg_routings: the versioned routing header. UNIQUE(tenant_id, item_id, version) (the BOM shape,
  D-047); (tenant, item_id, status) resolver/filter index. item_id is an OPAQUE inventory id.
- mfg_routing_operations: one operation per (routing, operation_number). Composite FKs to
  mfg_routings AND mfg_work_centers (work_center_id is intra-module, a real composite tenant FK);
  CHECKs setup/run times >= 0; UNIQUE(tenant, routing_id, operation_number); (tenant, routing_id) +
  (tenant, work_center_id) read indexes. Times are minutes (QuantityType, scale-6).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import QuantityType

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | None = None
depends_on: str | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.create_table(
        "mfg_work_centers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column(
            "capacity_hours_per_day", QuantityType(), nullable=False, server_default="0"
        ),
        sa.Column("efficiency_percent", QuantityType(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.CheckConstraint(
            "capacity_hours_per_day >= 0", name="ck_mfg_work_centers_capacity_non_negative"
        ),
        sa.CheckConstraint(
            "efficiency_percent > 0", name="ck_mfg_work_centers_efficiency_positive"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_mfg_work_centers_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_work_centers"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mfg_work_centers_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_mfg_work_centers_tenant_id_code"),
    )
    op.create_index("ix_mfg_work_centers_tenant_id", "mfg_work_centers", ["tenant_id"])
    op.create_index(
        "ix_mfg_work_centers_tenant_id_is_active",
        "mfg_work_centers",
        ["tenant_id", "is_active"],
    )

    op.create_table(
        "mfg_boms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("base_quantity", QuantityType(), nullable=False, server_default="1"),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("base_quantity > 0", name="ck_mfg_boms_base_quantity_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_mfg_boms_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_boms"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mfg_boms_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "item_id", "version", name="uq_mfg_boms_tenant_id_item_id_version"
        ),
    )
    op.create_index("ix_mfg_boms_tenant_id", "mfg_boms", ["tenant_id"])
    op.create_index(
        "ix_mfg_boms_tenant_id_item_id_status",
        "mfg_boms",
        ["tenant_id", "item_id", "status"],
    )

    op.create_table(
        "mfg_bom_components",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bom_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("component_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_per", QuantityType(), nullable=False),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("scrap_percent", QuantityType(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "quantity_per > 0", name="ck_mfg_bom_components_quantity_per_positive"
        ),
        sa.CheckConstraint(
            "scrap_percent >= 0", name="ck_mfg_bom_components_scrap_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_mfg_bom_components_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bom_id"],
            ["mfg_boms.tenant_id", "mfg_boms.id"],
            name="fk_mfg_bom_components_bom_id_mfg_boms",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_bom_components"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mfg_bom_components_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "bom_id",
            "line_number",
            name="uq_mfg_bom_components_tenant_id_bom_id_line_number",
        ),
    )
    op.create_index(
        "ix_mfg_bom_components_tenant_id", "mfg_bom_components", ["tenant_id"]
    )
    op.create_index(
        "ix_mfg_bom_components_tenant_id_bom_id",
        "mfg_bom_components",
        ["tenant_id", "bom_id"],
    )

    op.create_table(
        "mfg_routings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_mfg_routings_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_routings"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mfg_routings_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "item_id",
            "version",
            name="uq_mfg_routings_tenant_id_item_id_version",
        ),
    )
    op.create_index("ix_mfg_routings_tenant_id", "mfg_routings", ["tenant_id"])
    op.create_index(
        "ix_mfg_routings_tenant_id_item_id_status",
        "mfg_routings",
        ["tenant_id", "item_id", "status"],
    )

    op.create_table(
        "mfg_routing_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("routing_id", sa.Uuid(), nullable=False),
        sa.Column("operation_number", sa.Integer(), nullable=False),
        sa.Column("work_center_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("setup_time_minutes", QuantityType(), nullable=False, server_default="0"),
        sa.Column(
            "run_time_minutes_per_unit", QuantityType(), nullable=False, server_default="0"
        ),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "setup_time_minutes >= 0",
            name="ck_mfg_routing_operations_setup_non_negative",
        ),
        sa.CheckConstraint(
            "run_time_minutes_per_unit >= 0",
            name="ck_mfg_routing_operations_run_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_mfg_routing_operations_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "routing_id"],
            ["mfg_routings.tenant_id", "mfg_routings.id"],
            name="fk_mfg_routing_operations_routing_id_mfg_routings",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "work_center_id"],
            ["mfg_work_centers.tenant_id", "mfg_work_centers.id"],
            name="fk_mfg_routing_operations_work_center_id_mfg_work_centers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_routing_operations"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mfg_routing_operations_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "routing_id",
            "operation_number",
            name="uq_mfg_routing_operations_tenant_id_routing_id_operation_number",
        ),
    )
    op.create_index(
        "ix_mfg_routing_operations_tenant_id", "mfg_routing_operations", ["tenant_id"]
    )
    op.create_index(
        "ix_mfg_routing_operations_tenant_id_routing_id",
        "mfg_routing_operations",
        ["tenant_id", "routing_id"],
    )
    op.create_index(
        "ix_mfg_routing_operations_tenant_id_work_center_id",
        "mfg_routing_operations",
        ["tenant_id", "work_center_id"],
    )


def downgrade() -> None:
    op.drop_table("mfg_routing_operations")
    op.drop_table("mfg_routings")
    op.drop_table("mfg_bom_components")
    op.drop_table("mfg_boms")
    op.drop_table("mfg_work_centers")

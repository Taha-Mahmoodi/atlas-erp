"""manufacturing production orders: header + exploded components + routing-snapshot operations

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-13

PLAN 8.2 — the manufacturing↔inventory↔finance seam (parity: PP production orders = FULL). A
production order reserves → issues components to WIP (Dr WIP / Cr Inventory) → finishes to stock (Dr
Inventory / Cr WIP), with the WIP clearing account netting to zero per order. Creates THREE tables
and alters NOTHING — no trigger-bearing table is touched (D-022), so there is no trigger-recreation
concern. All DDL is portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap).
The QuantityType/MoneyType columns render as NUMERIC(18,6) on Postgres / INTEGER micro-units on
SQLite (D-015) via the model column type — imported from app.core.money so the revision stays
dialect-clean.

- mfg_production_orders: the order header. DocumentMixin (composite FK to core_documents); UNIQUE
  (tenant_id, order_number) (the gapless MO- number claimed at creation); composite FKs to mfg_boms
  (the exploded version) and mfg_routings (nullable, the snapshot); CHECKs quantity > 0 and
  finished_quantity >= 0; (tenant, status) + (tenant, item_id) filter indexes. item_id/warehouse_id
  are OPAQUE inventory ids (D-029) — no FK to inv_*. accumulated_wip_cost is MoneyType (WIP SSOT).
- mfg_production_order_components: the EXPLODED component reservations. Composite FK to
  mfg_production_orders; CHECKs required_quantity > 0 and issued_quantity >= 0; UNIQUE(tenant,
  production_order_id, line_number); (tenant, production_order_id) read index. component_item_id/
  uom_id/bin_id are OPAQUE inventory ids (D-029).
- mfg_production_order_operations: the routing-SNAPSHOT operations (8.3 capacity load). Composite
  to mfg_production_orders AND mfg_work_centers (work_center_id is intra-module, a real composite
  tenant FK); CHECK planned_minutes >= 0; UNIQUE(tenant, production_order_id, operation_number);
  (tenant, production_order_id) + (tenant, work_center_id) read indexes. Times are minutes
  (QuantityType, scale-6).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0033"
down_revision: str | None = "0032"
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
        "mfg_production_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("order_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("bom_id", sa.Uuid(), nullable=False),
        sa.Column("routing_id", sa.Uuid(), nullable=True),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("planned_start_date", sa.Date(), nullable=True),
        sa.Column("planned_end_date", sa.Date(), nullable=True),
        sa.Column("finished_quantity", QuantityType(), nullable=False, server_default="0"),
        sa.Column("accumulated_wip_cost", MoneyType(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "quantity > 0", name="ck_mfg_production_orders_quantity_positive"
        ),
        sa.CheckConstraint(
            "finished_quantity >= 0",
            name="ck_mfg_production_orders_finished_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_mfg_production_orders_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_mfg_production_orders_document_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bom_id"],
            ["mfg_boms.tenant_id", "mfg_boms.id"],
            name="fk_mfg_production_orders_bom_id_mfg_boms",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "routing_id"],
            ["mfg_routings.tenant_id", "mfg_routings.id"],
            name="fk_mfg_production_orders_routing_id_mfg_routings",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_production_orders"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mfg_production_orders_tenant_id"),
        sa.UniqueConstraint(
            "document_id", name="uq_mfg_production_orders_document_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "order_number",
            name="uq_mfg_production_orders_tenant_id_order_number",
        ),
    )
    op.create_index(
        "ix_mfg_production_orders_tenant_id", "mfg_production_orders", ["tenant_id"]
    )
    op.create_index(
        "ix_mfg_production_orders_tenant_id_status",
        "mfg_production_orders",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_mfg_production_orders_tenant_id_item_id",
        "mfg_production_orders",
        ["tenant_id", "item_id"],
    )

    op.create_table(
        "mfg_production_order_components",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("production_order_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("component_item_id", sa.Uuid(), nullable=False),
        sa.Column("required_quantity", QuantityType(), nullable=False),
        sa.Column("issued_quantity", QuantityType(), nullable=False, server_default="0"),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("bin_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "required_quantity > 0", name="ck_mfg_po_components_required_positive"
        ),
        sa.CheckConstraint(
            "issued_quantity >= 0", name="ck_mfg_po_components_issued_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_mfg_production_order_components_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "production_order_id"],
            ["mfg_production_orders.tenant_id", "mfg_production_orders.id"],
            name="fk_mfg_po_components_production_order_id_mfg_production_orders",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_production_order_components"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_mfg_production_order_components_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "production_order_id",
            "line_number",
            name="uq_mfg_po_components_tenant_id_production_order_id_line_number",
        ),
    )
    op.create_index(
        "ix_mfg_production_order_components_tenant_id",
        "mfg_production_order_components",
        ["tenant_id"],
    )
    op.create_index(
        "ix_mfg_po_components_tenant_id_production_order_id",
        "mfg_production_order_components",
        ["tenant_id", "production_order_id"],
    )

    op.create_table(
        "mfg_production_order_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("production_order_id", sa.Uuid(), nullable=False),
        sa.Column("operation_number", sa.Integer(), nullable=False),
        sa.Column("work_center_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("setup_time_minutes", QuantityType(), nullable=False, server_default="0"),
        sa.Column(
            "run_time_minutes_per_unit", QuantityType(), nullable=False, server_default="0"
        ),
        sa.Column("planned_minutes", QuantityType(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.CheckConstraint(
            "planned_minutes >= 0", name="ck_mfg_po_operations_planned_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_mfg_production_order_operations_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "production_order_id"],
            ["mfg_production_orders.tenant_id", "mfg_production_orders.id"],
            name="fk_mfg_po_operations_production_order_id_mfg_production_orders",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "work_center_id"],
            ["mfg_work_centers.tenant_id", "mfg_work_centers.id"],
            name="fk_mfg_po_operations_work_center_id_mfg_work_centers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_production_order_operations"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_mfg_production_order_operations_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "production_order_id",
            "operation_number",
            name="uq_mfg_po_operations_tenant_order_operation_number",
        ),
    )
    op.create_index(
        "ix_mfg_production_order_operations_tenant_id",
        "mfg_production_order_operations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_mfg_po_operations_tenant_id_production_order_id",
        "mfg_production_order_operations",
        ["tenant_id", "production_order_id"],
    )
    op.create_index(
        "ix_mfg_po_operations_tenant_id_work_center_id",
        "mfg_production_order_operations",
        ["tenant_id", "work_center_id"],
    )


def downgrade() -> None:
    op.drop_table("mfg_production_order_operations")
    op.drop_table("mfg_production_order_components")
    op.drop_table("mfg_production_orders")

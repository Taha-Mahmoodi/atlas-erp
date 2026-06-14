"""manufacturing MRP: run header + regenerated planned orders + rough capacity loads

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-13

PLAN 8.3 — the deterministic MRP run + rough capacity check (parity: PP MRP / capacity = PARTIAL). A
run nets demand (sales-order demand + reorder points) against supply (on-hand + open production
orders + open POs) per item, EXPLODES MAKE items' BOMs into dependent component demand level by
level, and writes planned orders (MAKE/BUY); the rough capacity check loads each work centre.
Creates THREE tables and alters NOTHING — no trigger-bearing table is touched (D-022), so there is
no trigger-recreation concern. All DDL is portable across SQLite and Postgres; every identifier is
<= 63 chars (PG cap). QuantityType columns render as NUMERIC(18,6) on Postgres / INTEGER micro-units
on SQLite (D-015) via the model column type — imported from app.core.money so the revision stays
dialect-clean.

- mfg_mrp_runs: the run header. DocumentMixin (composite FK to core_documents); UNIQUE(tenant_id,
  run_number) (the gapless MRP- number claimed at creation); (tenant, status) filter index.
  warehouse_id is OPAQUE (D-029, NULL = tenant-wide) — no FK to inv_*.
- mfg_planned_orders: the regenerated planning output. Composite FK to mfg_mrp_runs; CHECK
  quantity > 0; (tenant, mrp_run_id) + (tenant, item_id, status) read indexes. item_id/
  converted_document_id are OPAQUE ids (D-029) — no FK.
- mfg_capacity_loads: the rough capacity check output. Composite FKs to mfg_mrp_runs AND
  mfg_work_centers; UNIQUE(tenant, mrp_run_id, work_center_id); (tenant, mrp_run_id) read index.
  Minutes are QuantityType.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import QuantityType

# revision identifiers, used by Alembic.
revision: str = "0034"
down_revision: str | None = "0033"
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
        "mfg_mrp_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("run_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="RUNNING"),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("demand_source", sa.String(length=1000), nullable=True),
        sa.Column("planned_make_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("planned_buy_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_mfg_mrp_runs_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_mfg_mrp_runs_document_id_core_documents",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_mrp_runs"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mfg_mrp_runs_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_mfg_mrp_runs_document_id"),
        sa.UniqueConstraint(
            "tenant_id", "run_number", name="uq_mfg_mrp_runs_tenant_id_run_number"
        ),
    )
    op.create_index("ix_mfg_mrp_runs_tenant_id", "mfg_mrp_runs", ["tenant_id"])
    op.create_index(
        "ix_mfg_mrp_runs_tenant_id_status", "mfg_mrp_runs", ["tenant_id", "status"]
    )

    op.create_table(
        "mfg_planned_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mrp_run_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("order_type", sa.String(length=10), nullable=False),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PLANNED"),
        sa.Column("source_notes", sa.String(length=500), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("converted_document_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0", name="ck_mfg_planned_orders_quantity_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_mfg_planned_orders_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mrp_run_id"],
            ["mfg_mrp_runs.tenant_id", "mfg_mrp_runs.id"],
            name="fk_mfg_planned_orders_mrp_run_id_mfg_mrp_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_planned_orders"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mfg_planned_orders_tenant_id"),
    )
    op.create_index("ix_mfg_planned_orders_tenant_id", "mfg_planned_orders", ["tenant_id"])
    op.create_index(
        "ix_mfg_planned_orders_tenant_id_mrp_run_id",
        "mfg_planned_orders",
        ["tenant_id", "mrp_run_id"],
    )
    op.create_index(
        "ix_mfg_planned_orders_tenant_id_item_id_status",
        "mfg_planned_orders",
        ["tenant_id", "item_id", "status"],
    )

    op.create_table(
        "mfg_capacity_loads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mrp_run_id", sa.Uuid(), nullable=False),
        sa.Column("work_center_id", sa.Uuid(), nullable=False),
        sa.Column("planned_load_minutes", QuantityType(), nullable=False, server_default="0"),
        sa.Column("available_minutes", QuantityType(), nullable=False, server_default="0"),
        sa.Column("utilization_percent", QuantityType(), nullable=False, server_default="0"),
        sa.Column(
            "is_overloaded", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_mfg_capacity_loads_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mrp_run_id"],
            ["mfg_mrp_runs.tenant_id", "mfg_mrp_runs.id"],
            name="fk_mfg_capacity_loads_mrp_run_id_mfg_mrp_runs",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "work_center_id"],
            ["mfg_work_centers.tenant_id", "mfg_work_centers.id"],
            name="fk_mfg_capacity_loads_work_center_id_mfg_work_centers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mfg_capacity_loads"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mfg_capacity_loads_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "mrp_run_id",
            "work_center_id",
            name="uq_mfg_capacity_loads_tenant_run_work_center",
        ),
    )
    op.create_index("ix_mfg_capacity_loads_tenant_id", "mfg_capacity_loads", ["tenant_id"])
    op.create_index(
        "ix_mfg_capacity_loads_tenant_id_mrp_run_id",
        "mfg_capacity_loads",
        ["tenant_id", "mrp_run_id"],
    )


def downgrade() -> None:
    op.drop_table("mfg_capacity_loads")
    op.drop_table("mfg_planned_orders")
    op.drop_table("mfg_mrp_runs")

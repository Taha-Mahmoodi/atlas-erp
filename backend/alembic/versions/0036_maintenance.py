"""maintenance: equipment register + corrective/preventive maintenance orders + interval plans

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-14

PLAN 9.2 — the deliberately small PM core (s4hana-parity §QM/PM: equipment register + corrective and
interval-based preventive maintenance orders; functional locations, notifications, measurement
points, task lists out of scope). Creates THREE tables and alters NOTHING — no trigger-bearing table
is touched (D-022), so there is no trigger-recreation concern. All DDL is portable across SQLite and
Postgres; every identifier is <= 63 chars (PG cap). The MoneyType columns render as NUMERIC(18,6) on
Postgres / INTEGER micro-units on SQLite (D-015) via the model column type — imported from
app.core.money so the revision stays dialect-clean.

- pm_equipment: the flat equipment register. UNIQUE(tenant_id, code) (the user-supplied master
  code); (tenant, status) filter index. cost_center_id is an OPAQUE finance cost-centre id (D-029)
  — no FK.
- pm_maintenance_plans: the interval-based preventive plan. DocumentMixin (so a plan can be the
  docflow predecessor of the orders it generates); UNIQUE(tenant_id, code); composite tenant FK to
  pm_equipment; CHECK interval_value > 0; (tenant, status, next_due_date) due-scan index +
  (tenant, equipment_id) index.
- pm_maintenance_orders: the maintenance-order header. DocumentMixin (gapless MNT- number claimed at
  creation); UNIQUE(tenant_id, order_number); composite tenant FKs to pm_equipment +
  pm_maintenance_plans (nullable); (tenant, equipment_id, status) + (tenant, status, scheduled_date)
  worklist indexes. assigned_to is the technician's user id (a plain id, no FK).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "pm_equipment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("manufacturer", sa.String(length=200), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("serial_number", sa.String(length=200), nullable=True),
        sa.Column("commissioned_date", sa.Date(), nullable=True),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_pm_equipment_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pm_equipment"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_pm_equipment_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_pm_equipment_tenant_id_code"),
    )
    op.create_index("ix_pm_equipment_tenant_id", "pm_equipment", ["tenant_id"])
    op.create_index(
        "ix_pm_equipment_tenant_id_status", "pm_equipment", ["tenant_id", "status"]
    )

    op.create_table(
        "pm_maintenance_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("equipment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("interval_value", sa.Integer(), nullable=False),
        sa.Column("interval_unit", sa.String(length=10), nullable=False),
        sa.Column("task_description", sa.String(length=1000), nullable=False),
        sa.Column("last_generated_date", sa.Date(), nullable=True),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("estimated_cost", MoneyType(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "interval_value > 0", name="ck_pm_maintenance_plans_interval_positive"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_pm_maintenance_plans_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "equipment_id"],
            ["pm_equipment.tenant_id", "pm_equipment.id"],
            name="fk_pm_maintenance_plans_equipment_id_pm_equipment",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_pm_maintenance_plans_document_id_core_documents",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pm_maintenance_plans"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_pm_maintenance_plans_tenant_id"),
        sa.UniqueConstraint(
            "document_id", name="uq_pm_maintenance_plans_document_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "code", name="uq_pm_maintenance_plans_tenant_id_code"
        ),
    )
    op.create_index(
        "ix_pm_maintenance_plans_tenant_id", "pm_maintenance_plans", ["tenant_id"]
    )
    op.create_index(
        "ix_pm_maintenance_plans_tenant_id_status_next_due_date",
        "pm_maintenance_plans",
        ["tenant_id", "status", "next_due_date"],
    )
    op.create_index(
        "ix_pm_maintenance_plans_tenant_id_equipment_id",
        "pm_maintenance_plans",
        ["tenant_id", "equipment_id"],
    )

    op.create_table(
        "pm_maintenance_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("order_number", sa.String(length=60), nullable=False),
        sa.Column(
            "order_type", sa.String(length=20), nullable=False, server_default="CORRECTIVE"
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("equipment_id", sa.Uuid(), nullable=False),
        sa.Column("maintenance_plan_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column("estimated_cost", MoneyType(), nullable=True),
        sa.Column("actual_cost", MoneyType(), nullable=True),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_pm_maintenance_orders_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "equipment_id"],
            ["pm_equipment.tenant_id", "pm_equipment.id"],
            name="fk_pm_maintenance_orders_equipment_id_pm_equipment",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "maintenance_plan_id"],
            ["pm_maintenance_plans.tenant_id", "pm_maintenance_plans.id"],
            name="fk_pm_mnt_orders_maintenance_plan_id_pm_maintenance_plans",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_pm_maintenance_orders_document_id_core_documents",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pm_maintenance_orders"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_pm_maintenance_orders_tenant_id"),
        sa.UniqueConstraint(
            "document_id", name="uq_pm_maintenance_orders_document_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "order_number", name="uq_pm_maintenance_orders_tenant_id_order_number"
        ),
    )
    op.create_index(
        "ix_pm_maintenance_orders_tenant_id", "pm_maintenance_orders", ["tenant_id"]
    )
    op.create_index(
        "ix_pm_maintenance_orders_tenant_id_equipment_id_status",
        "pm_maintenance_orders",
        ["tenant_id", "equipment_id", "status"],
    )
    op.create_index(
        "ix_pm_maintenance_orders_tenant_id_status_scheduled_date",
        "pm_maintenance_orders",
        ["tenant_id", "status", "scheduled_date"],
    )


def downgrade() -> None:
    op.drop_table("pm_maintenance_orders")
    op.drop_table("pm_maintenance_plans")
    op.drop_table("pm_equipment")

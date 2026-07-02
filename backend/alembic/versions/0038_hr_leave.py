"""hr leave: leave types + balances + requests (accrual, approval flow)

Revision ID: 0038
Revises: 0037
Create Date: 2026-06-14

PLAN 10.2 — leave types, accruals, and the request approval flow (s4hana-parity §HCM "Leave and
absence management" = Full). Creates THREE tables and alters NOTHING — no trigger-bearing table is
touched (D-022), so there is no trigger-recreation concern. All DDL is portable across SQLite and
Postgres; every identifier is <= 63 chars (PG cap). The QuantityType columns render as NUMERIC(18,6)
on Postgres / INTEGER micro-units on SQLite (D-015) via the model column type — imported from
app.core.money so the revision stays dialect-clean.

- hr_leave_types: the leave config. UNIQUE(tenant_id, code); CHECK accrual_amount >= 0; index
  (tenant, accrual_frequency, is_active) for the accrual run's set-based scan.
- hr_leave_balances: the running balance per (employee, type). Composite tenant FKs to
  hr_employees +
  hr_leave_types; UNIQUE(tenant, employee_id, leave_type_id); CHECKs accrued/taken >= 0; index
  (tenant, employee_id). last_accrual_period (YYYY-MM / YYYY) is the accrual idempotency guard.
- hr_leave_requests: the request document. Composite tenant FKs to hr_employees + hr_leave_types;
  UNIQUE(tenant, request_number) (the gapless LV- number claimed at creation); CHECK days > 0; index
  (tenant, employee_id, status). approved_by is an OPAQUE core users id (nullable, no FK).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import QuantityType

# revision identifiers, used by Alembic.
revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hr_leave_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "accrual_frequency", sa.String(length=20), nullable=False, server_default="MONTHLY"
        ),
        sa.Column("accrual_amount", QuantityType(), nullable=False),
        sa.Column("max_balance", QuantityType(), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=False, server_default="DAYS"),
        sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("accrual_amount >= 0", name="ck_hr_leave_types_accrual_non_negative"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hr_leave_types_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_leave_types"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_leave_types_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_hr_leave_types_tenant_id_code"),
    )
    op.create_index("ix_hr_leave_types_tenant_id", "hr_leave_types", ["tenant_id"])
    op.create_index(
        "ix_hr_leave_types_tenant_id_accrual_frequency_is_active",
        "hr_leave_types",
        ["tenant_id", "accrual_frequency", "is_active"],
    )

    op.create_table(
        "hr_leave_balances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("leave_type_id", sa.Uuid(), nullable=False),
        sa.Column("balance_days", QuantityType(), nullable=False, server_default="0"),
        sa.Column("accrued_to_date", QuantityType(), nullable=False, server_default="0"),
        sa.Column("taken_to_date", QuantityType(), nullable=False, server_default="0"),
        sa.Column("last_accrual_period", sa.String(length=7), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "accrued_to_date >= 0", name="ck_hr_leave_balances_accrued_non_negative"
        ),
        sa.CheckConstraint("taken_to_date >= 0", name="ck_hr_leave_balances_taken_non_negative"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hr_leave_balances_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["hr_employees.tenant_id", "hr_employees.id"],
            name="fk_hr_leave_balances_employee_id_hr_employees",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "leave_type_id"],
            ["hr_leave_types.tenant_id", "hr_leave_types.id"],
            name="fk_hr_leave_balances_leave_type_id_hr_leave_types",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_leave_balances"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_leave_balances_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            "leave_type_id",
            name="uq_hr_leave_balances_tenant_employee_type",
        ),
    )
    op.create_index("ix_hr_leave_balances_tenant_id", "hr_leave_balances", ["tenant_id"])
    op.create_index(
        "ix_hr_leave_balances_tenant_id_employee_id",
        "hr_leave_balances",
        ["tenant_id", "employee_id"],
    )

    op.create_table(
        "hr_leave_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("request_number", sa.String(length=40), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("leave_type_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("days", QuantityType(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("days > 0", name="ck_hr_leave_requests_days_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hr_leave_requests_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["hr_employees.tenant_id", "hr_employees.id"],
            name="fk_hr_leave_requests_employee_id_hr_employees",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "leave_type_id"],
            ["hr_leave_types.tenant_id", "hr_leave_types.id"],
            name="fk_hr_leave_requests_leave_type_id_hr_leave_types",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_leave_requests"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_leave_requests_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "request_number", name="uq_hr_leave_requests_tenant_id_request_number"
        ),
    )
    op.create_index("ix_hr_leave_requests_tenant_id", "hr_leave_requests", ["tenant_id"])
    op.create_index(
        "ix_hr_leave_requests_tenant_id_employee_id_status",
        "hr_leave_requests",
        ["tenant_id", "employee_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("hr_leave_requests")
    op.drop_table("hr_leave_balances")
    op.drop_table("hr_leave_types")

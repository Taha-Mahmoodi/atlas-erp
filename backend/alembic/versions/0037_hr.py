"""hr: departments + positions + employees (masked compensation/PII) + org chart

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-14

PLAN 10.1 — the deliberately small HCM core (s4hana-parity §HCM: employees with masked compensation,
departments, positions, org chart; talent/recruiting/benefits and jurisdiction-compliant payroll out
of scope). Creates THREE tables and alters NOTHING — no trigger-bearing table is touched (D-022), so
there is no trigger-recreation concern. All DDL is portable across SQLite and Postgres; every
identifier is <= 63 chars (PG cap). The MoneyType column renders as NUMERIC(18,6) on Postgres /
INTEGER micro-units on SQLite (D-015) via the model column type — imported from app.core.money so
the
revision stays dialect-clean.

- hr_departments: the org unit. UNIQUE(tenant_id, code); self composite FK (tenant, parent_id) ->
  (tenant, id) for the hierarchy; (tenant, parent_id) index. cost_center_id is an OPAQUE finance
  cost-centre id (D-029) — no FK. manager_employee_id is a PLAIN uuid (NOT a composite FK) to break
  the department<->employee circular dependency (D-052) — validated in the service.
- hr_positions: the job title. UNIQUE(tenant_id, code); composite tenant FK to hr_departments
  (nullable); (tenant, department_id) index.
- hr_employees: the person. UNIQUE(tenant_id, employee_code); composite tenant FKs to hr_departments
  + hr_positions (nullable); self composite FK (tenant, manager_id) -> (tenant, id) for the
  org-chart
  reporting line; (tenant, department_id, status) + (tenant, manager_id) indexes. user_id is an
  OPAQUE core users id (nullable, no FK — the optional login link). The compensation/PII columns
  (base_salary MoneyType, currency_code, national_id, tax_id, date_of_birth, bank_account) store the
  real values; the D-009 read masking is a schema-layer concern, not DDL.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hr_departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column("manager_employee_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hr_departments_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["hr_departments.tenant_id", "hr_departments.id"],
            name="fk_hr_departments_parent_id_hr_departments",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_departments"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_departments_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_hr_departments_tenant_id_code"),
    )
    op.create_index("ix_hr_departments_tenant_id", "hr_departments", ["tenant_id"])
    op.create_index(
        "ix_hr_departments_tenant_id_parent_id",
        "hr_departments",
        ["tenant_id", "parent_id"],
    )

    op.create_table(
        "hr_positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hr_positions_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["hr_departments.tenant_id", "hr_departments.id"],
            name="fk_hr_positions_department_id_hr_departments",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_positions"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_positions_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_hr_positions_tenant_id_code"),
    )
    op.create_index("ix_hr_positions_tenant_id", "hr_positions", ["tenant_id"])
    op.create_index(
        "ix_hr_positions_tenant_id_department_id",
        "hr_positions",
        ["tenant_id", "department_id"],
    )

    op.create_table(
        "hr_employees",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("employee_code", sa.String(length=40), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("position_id", sa.Uuid(), nullable=True),
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "employment_type", sa.String(length=20), nullable=False, server_default="FULL_TIME"
        ),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("base_salary", MoneyType(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("national_id", sa.String(length=64), nullable=True),
        sa.Column("tax_id", sa.String(length=64), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("bank_account", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hr_employees_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["hr_departments.tenant_id", "hr_departments.id"],
            name="fk_hr_employees_department_id_hr_departments",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "position_id"],
            ["hr_positions.tenant_id", "hr_positions.id"],
            name="fk_hr_employees_position_id_hr_positions",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "manager_id"],
            ["hr_employees.tenant_id", "hr_employees.id"],
            name="fk_hr_employees_manager_id_hr_employees",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_employees"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_employees_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "employee_code", name="uq_hr_employees_tenant_id_employee_code"
        ),
    )
    op.create_index("ix_hr_employees_tenant_id", "hr_employees", ["tenant_id"])
    op.create_index(
        "ix_hr_employees_tenant_id_department_id_status",
        "hr_employees",
        ["tenant_id", "department_id", "status"],
    )
    op.create_index(
        "ix_hr_employees_tenant_id_manager_id",
        "hr_employees",
        ["tenant_id", "manager_id"],
    )


def downgrade() -> None:
    op.drop_table("hr_employees")
    op.drop_table("hr_positions")
    op.drop_table("hr_departments")

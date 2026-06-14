"""hr time tracking: timesheets + time entries (project/cost-centre allocation)

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-14

PLAN 10.3 — time tracking with project & cost-centre allocation (s4hana-parity §HCM "Time recording
with account assignment (CATS-style timesheet)" = Full). Creates TWO tables and alters NOTHING — no
trigger-bearing table is touched (D-022), so there is no trigger-recreation concern. All DDL is
portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap). The QuantityType
columns render as NUMERIC(18,6) on Postgres / INTEGER micro-units on SQLite (D-015) via the imported
column type so the revision stays dialect-clean.

- hr_timesheets: the period HEADER. Composite tenant FK to hr_employees; UNIQUE(tenant, employee_id,
  period_start) so one timesheet per employee per period; UNIQUE(tenant, timesheet_number) (the
  gapless TS- number claimed at creation); CHECK period_end >= period_start; CHECK total_hours >= 0;
  index (tenant, employee_id, status). approved_by is an OPAQUE core users id (nullable, no FK).
- hr_time_entries: the lines. Composite tenant FK to hr_timesheets; CHECK hours > 0; index
  (tenant, timesheet_id) for the lines-of-a-sheet read; index (tenant, cost_center_id) +
  (tenant, project_id) for the allocation aggregates. project_id is a NULLABLE OPAQUE Uuid NOT
  validated in v1 (projects is Phase 11); cost_center_id is an OPAQUE finance id validated at the
  service layer. Neither is a cross-module FK (D-029).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import QuantityType

# revision identifiers, used by Alembic.
revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hr_timesheets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("timesheet_number", sa.String(length=40), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("total_hours", QuantityType(), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("period_end >= period_start", name="ck_hr_timesheets_period_order"),
        sa.CheckConstraint(
            "total_hours >= 0", name="ck_hr_timesheets_total_hours_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hr_timesheets_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["hr_employees.tenant_id", "hr_employees.id"],
            name="fk_hr_timesheets_employee_id_hr_employees",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_timesheets"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_timesheets_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "timesheet_number",
            name="uq_hr_timesheets_tenant_id_timesheet_number",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            "period_start",
            name="uq_hr_timesheets_tenant_employee_period",
        ),
    )
    op.create_index("ix_hr_timesheets_tenant_id", "hr_timesheets", ["tenant_id"])
    op.create_index(
        "ix_hr_timesheets_tenant_id_employee_id_status",
        "hr_timesheets",
        ["tenant_id", "employee_id", "status"],
    )

    op.create_table(
        "hr_time_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("timesheet_id", sa.Uuid(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("hours", QuantityType(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column("task_description", sa.String(length=1000), nullable=True),
        sa.Column("is_billable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("hours > 0", name="ck_hr_time_entries_hours_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hr_time_entries_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "timesheet_id"],
            ["hr_timesheets.tenant_id", "hr_timesheets.id"],
            name="fk_hr_time_entries_timesheet_id_hr_timesheets",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_time_entries"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_time_entries_tenant_id"),
    )
    op.create_index("ix_hr_time_entries_tenant_id", "hr_time_entries", ["tenant_id"])
    op.create_index(
        "ix_hr_time_entries_tenant_id_timesheet_id",
        "hr_time_entries",
        ["tenant_id", "timesheet_id"],
    )
    op.create_index(
        "ix_hr_time_entries_tenant_id_cost_center_id",
        "hr_time_entries",
        ["tenant_id", "cost_center_id"],
    )
    op.create_index(
        "ix_hr_time_entries_tenant_id_project_id",
        "hr_time_entries",
        ["tenant_id", "project_id"],
    )


def downgrade() -> None:
    op.drop_table("hr_time_entries")
    op.drop_table("hr_timesheets")

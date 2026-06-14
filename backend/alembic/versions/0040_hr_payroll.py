"""hr payroll: payroll runs + payroll run lines (simplistic flat-tax gross→net)

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-14

PLAN 10.4 — a simple gross→net payroll run posting a consolidated finance journal via the event bus,
explicitly flagged NON-JURISDICTION-COMPLIANT (s4hana-parity §HCM "Payroll": flat withholding rate,
no brackets, no social security, no deductions; D-055). Creates TWO tables and alters NOTHING — no
trigger-bearing table is touched (D-022), so there is no trigger-recreation concern. All DDL is
portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap). The MoneyType columns
render as NUMERIC(18,6) on Postgres / INTEGER micro-units on SQLite (D-015) via the imported column
type so the revision stays dialect-clean.

- hr_payroll_runs: the period HEADER. Mixes in DocumentMixin → NOT NULL document_id with a composite
  tenant-safe FK to core_documents (D-012). run_number is NULLABLE (the gapless PAY- number claimed
  at POSTING — an abandoned/cancelled draft burns no number) with a PARTIAL-UNIQUE (tenant,
  run_number) index (NULLs coexist; no two claimed numbers collide — the journal-entry entry_number
  precedent). Composite tenant FK to adm_tenants; CHECK period_end >= period_start + non-negative
  totals/rate/count; indexes (tenant, status) + (tenant, period_start). journal_entry_id is a
  NULLABLE OPAQUE finance journal id (no cross-module FK, D-029).
- hr_payroll_run_lines: the per-employee lines. Composite tenant FKs to hr_payroll_runs +
  hr_employees; UNIQUE(tenant, payroll_run_id, employee_id) (one line per employee per run); CHECK
  gross/tax/net non-negative; index (tenant, payroll_run_id) for the lines-of-a-run read.
  cost_center_id is a NULLABLE OPAQUE finance cost-centre id (the salary-expense allocation, no FK).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hr_payroll_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("run_number", sa.String(length=60), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("tax_rate_percent", MoneyType(), nullable=False),
        sa.Column("total_gross", MoneyType(), nullable=False, server_default="0"),
        sa.Column("total_tax", MoneyType(), nullable=False, server_default="0"),
        sa.Column("total_net", MoneyType(), nullable=False, server_default="0"),
        sa.Column("employee_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_hr_payroll_runs_period_order"
        ),
        sa.CheckConstraint(
            "total_gross >= 0", name="ck_hr_payroll_runs_total_gross_non_negative"
        ),
        sa.CheckConstraint(
            "total_tax >= 0", name="ck_hr_payroll_runs_total_tax_non_negative"
        ),
        sa.CheckConstraint(
            "total_net >= 0", name="ck_hr_payroll_runs_total_net_non_negative"
        ),
        sa.CheckConstraint(
            "tax_rate_percent >= 0", name="ck_hr_payroll_runs_tax_rate_non_negative"
        ),
        sa.CheckConstraint(
            "employee_count >= 0", name="ck_hr_payroll_runs_employee_count_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hr_payroll_runs_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_hr_payroll_runs_document_id_core_documents",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_payroll_runs"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_payroll_runs_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_hr_payroll_runs_document_id"),
    )
    op.create_index("ix_hr_payroll_runs_tenant_id", "hr_payroll_runs", ["tenant_id"])
    op.create_index(
        "ix_hr_payroll_runs_tenant_id_status", "hr_payroll_runs", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_hr_payroll_runs_tenant_id_period_start",
        "hr_payroll_runs",
        ["tenant_id", "period_start"],
    )
    # Partial-unique PAY- number: NULL drafts coexist, no two claimed numbers collide (D-012). Both
    # dialect predicates render the same; each engine needs its own partial-index WHERE.
    op.create_index(
        "uq_hr_payroll_runs_tenant_id_run_number",
        "hr_payroll_runs",
        ["tenant_id", "run_number"],
        unique=True,
        postgresql_where=sa.text("run_number IS NOT NULL"),
        sqlite_where=sa.text("run_number IS NOT NULL"),
    )

    op.create_table(
        "hr_payroll_run_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("payroll_run_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("gross_amount", MoneyType(), nullable=False),
        sa.Column("tax_amount", MoneyType(), nullable=False),
        sa.Column("net_amount", MoneyType(), nullable=False),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "gross_amount >= 0", name="ck_hr_payroll_run_lines_gross_non_negative"
        ),
        sa.CheckConstraint("tax_amount >= 0", name="ck_hr_payroll_run_lines_tax_non_negative"),
        sa.CheckConstraint("net_amount >= 0", name="ck_hr_payroll_run_lines_net_non_negative"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_hr_payroll_run_lines_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payroll_run_id"],
            ["hr_payroll_runs.tenant_id", "hr_payroll_runs.id"],
            name="fk_hr_payroll_run_lines_payroll_run_id_hr_payroll_runs",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["hr_employees.tenant_id", "hr_employees.id"],
            name="fk_hr_payroll_run_lines_employee_id_hr_employees",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_payroll_run_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_payroll_run_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "payroll_run_id",
            "employee_id",
            name="uq_hr_payroll_run_lines_tenant_run_employee",
        ),
    )
    op.create_index(
        "ix_hr_payroll_run_lines_tenant_id", "hr_payroll_run_lines", ["tenant_id"]
    )
    op.create_index(
        "ix_hr_payroll_run_lines_tenant_id_payroll_run_id",
        "hr_payroll_run_lines",
        ["tenant_id", "payroll_run_id"],
    )


def downgrade() -> None:
    op.drop_table("hr_payroll_run_lines")
    op.drop_table("hr_payroll_runs")

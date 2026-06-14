"""HR payroll models (PLAN 10.4, parity HCM "Payroll (localized gross-to-net)" = Partial /
"Payroll posting to finance (FI/CO)" = Full, D-055): the ``PayrollRun`` header and its
``PayrollRunLine`` lines.

TWO tables, one concern (the simplistic gross→net payroll-lite). THE NON-COMPLIANCE FLAG (D-055):
this is a SIMPLISTIC, NON-JURISDICTION-COMPLIANT model — a single flat withholding rate, no tax
brackets, no social security / pension, no deductions beyond the flat tax, no employer-side taxes,
no retro accounting, no payment files, no statutory reporting. The s4hana-parity §HCM Payroll entry
explicitly scopes payroll to this reduced form (see docs/modules/hr.md).

- ``PayrollRun`` is the period HEADER. It mixes in ``DocumentMixin`` (a payroll run IS a posted
  document, unlike the leave/timesheet records): it registers in core_documents at creation and
  claims the gapless ``PAY-`` number AT POSTING (the journal-entry / production-order
  claim-at-permanence precedent, D-012), linking payroll-run → 'posts' → finance-journal in the
  docflow chain. So there is NO plain number column — the number lives on the registry, set at
  posting. Composite tenant FK to ``adm_tenants``. ``tax_rate_percent`` (MoneyType — exact on both
  engines) is the flat withholding rate FOR THIS RUN; ``total_gross`` / ``total_tax`` /
  ``total_net`` (MoneyType) are MAINTAINED at creation (the timesheet ``total_hours`` precedent).
  ``journal_entry_id`` (nullable) links the posted consolidated journal. THE BALANCING INVARIANT:
  ``total_gross == total_tax + total_net`` always (the journal cannot balance otherwise).

- ``PayrollRunLine`` is one employee's payroll for the run. Composite tenant FK to
  ``hr_payroll_runs`` and to ``hr_employees``. ``gross_amount`` is the employee's ``base_salary``
  TAKEN AS the period gross (NO proration — v1 assumes base_salary IS the per-period — e.g.
  monthly — gross, D-055); ``tax_amount`` = quantize(gross × tax_rate_percent / 100);
  ``net_amount`` = gross − tax. ``cost_center_id`` (nullable OPAQUE finance cost-centre id, D-029)
  is the employee's department cost centre, carried so the salary-expense Dr leg carries the CO
  cost-centre dimension. UNIQUE(tenant, payroll_run_id, employee_id) — one line per employee per
  run. NOT audited (a high-churn child line, the journal-line / time-entry precedent — the audited
  unit is the run header).

All money amounts use the D-015 ``MoneyType`` (NUMERIC on PG / integer micro-units on SQLite, exact
on both); a plain ``sa.Numeric`` would round-trip through float on SQLite and lose cents, so it is
never used for stored money here.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.docflow import DocumentMixin, document_fk
from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import MoneyType
from app.modules.hr.constants import PayrollRunStatus


class PayrollRun(UuidPKMixin, TenantMixin, AuditMixin, DocumentMixin, TimestampMixin, Base):
    """A PAYROLL RUN HEADER (D-055): the gross→net payroll for every covered employee over a period.

    Registers a document at creation and claims the gapless ``PAY-`` number AT POSTING (D-012 — the
    number lives on the registry row, not a column here). ``status`` runs the ``PayrollRunStatus``
    lifecycle (DRAFT → POSTED, or DRAFT → CANCELLED). ``period_start`` / ``period_end`` (Date)
    bracket the pay period; ``pay_date`` (Date) is the posting date the consolidated journal lands
    on (a closed period at ``pay_date`` rolls the whole post back). ``tax_rate_percent`` (MoneyType)
    is the FLAT withholding rate for the run. ``total_gross`` / ``total_tax`` / ``total_net``
    (MoneyType) are maintained at creation, with ``total_gross == total_tax + total_net`` always.
    ``employee_count`` is the number of lines. ``currency_code`` is the run's currency.
    ``journal_entry_id`` (nullable) links the posted journal; ``posted_at`` stamps the post. Audited
    (D-010): a payroll run drives GL effects.
    """

    __tablename__ = "hr_payroll_runs"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
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
        # The list filters on (tenant, status) and narrows by period (PERFORMANCE §1).
        sa.Index("ix_hr_payroll_runs_tenant_id_status", "tenant_id", "status"),
        sa.Index(
            "ix_hr_payroll_runs_tenant_id_period_start", "tenant_id", "period_start"
        ),
    )

    # Gapless PAY- number, claimed at POSTING (D-012) — NULLABLE so an abandoned/cancelled draft
    # burns no number; the partial-unique index below makes drafts' NULLs coexist while no two
    # claimed numbers collide (the journal-entry entry_number precedent).
    run_number: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=PayrollRunStatus.DRAFT.value,
        server_default="DRAFT",
    )
    period_start: Mapped[date] = mapped_column(sa.Date, nullable=False)
    period_end: Mapped[date] = mapped_column(sa.Date, nullable=False)
    pay_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    # The FLAT withholding rate for the run (MoneyType — exact decimal on both engines, D-015).
    tax_rate_percent: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)
    total_gross: Mapped[Decimal] = mapped_column(
        MoneyType(), nullable=False, default=Decimal(0), server_default="0"
    )
    total_tax: Mapped[Decimal] = mapped_column(
        MoneyType(), nullable=False, default=Decimal(0), server_default="0"
    )
    total_net: Mapped[Decimal] = mapped_column(
        MoneyType(), nullable=False, default=Decimal(0), server_default="0"
    )
    employee_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    # The posted consolidated journal entry (nullable — set at posting). A plain opaque id (no FK):
    # finance owns fin_journal_entries and HR never holds a cross-module FK (D-029).
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class PayrollRunLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One employee's PAYROLL LINE for a run (D-055): ``gross_amount`` → ``tax_amount`` →
    ``net_amount`` with the salary-expense cost-centre allocation.

    Composite tenant FK to ``hr_payroll_runs`` and to ``hr_employees``. ``gross_amount`` is the
    employee's ``base_salary`` TAKEN AS the period gross (no proration, D-055); ``tax_amount`` =
    quantize(gross × run.tax_rate_percent / 100); ``net_amount`` = gross − tax (so gross = tax +
    net per line). ``cost_center_id`` (nullable OPAQUE finance cost-centre id, D-029) is the
    employee's department cost centre, carried so the consolidated journal's salary-expense Dr
    carries the CO cost-centre dimension. UNIQUE(tenant, payroll_run_id, employee_id). NOT audited
    (a high-churn child line — the audited unit is the run header, the journal-line precedent).
    """

    __tablename__ = "hr_payroll_run_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "payroll_run_id",
            "employee_id",
            name="uq_hr_payroll_run_lines_tenant_run_employee",
        ),
        sa.CheckConstraint(
            "gross_amount >= 0", name="ck_hr_payroll_run_lines_gross_non_negative"
        ),
        sa.CheckConstraint("tax_amount >= 0", name="ck_hr_payroll_run_lines_tax_non_negative"),
        sa.CheckConstraint("net_amount >= 0", name="ck_hr_payroll_run_lines_net_non_negative"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hr_payroll_runs", "payroll_run_id"),
        tenant_fk("hr_employees", "employee_id"),
        # The lines-of-a-run read filters on (tenant, payroll_run_id) (PERFORMANCE §1).
        sa.Index(
            "ix_hr_payroll_run_lines_tenant_id_payroll_run_id",
            "tenant_id",
            "payroll_run_id",
        ),
    )

    payroll_run_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)
    # Opaque finance cost-centre id (D-029): the employee's department cost centre, carried for the
    # salary-expense allocation. Nullable (an employee whose department has no cost centre). No FK.
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


# Partial-unique index declared OUTSIDE the class body so its dialect predicate is a column
# expression (``.isnot(None)``) rather than a raw SQL string — the D-007 grep gate bans raw-SQL
# constructs under app/modules/. Gapless PAY- numbers: many drafts may have NULL run_number, never
# two the SAME (D-012, the journal-entry entry_number precedent). Both dialect kwargs render alike.
sa.Index(
    "uq_hr_payroll_runs_tenant_id_run_number",
    PayrollRun.tenant_id,
    PayrollRun.run_number,
    unique=True,
    postgresql_where=PayrollRun.run_number.isnot(None),
    sqlite_where=PayrollRun.run_number.isnot(None),
)

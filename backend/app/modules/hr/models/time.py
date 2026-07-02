"""HR time-tracking models (PLAN 10.3, parity HCM "Time recording with account assignment
(CATS-style timesheet)" = Full, D-054): the ``Timesheet`` header and its ``TimeEntry`` lines.

TWO tables, one concern (time tracking). The SAP-like model: a timesheet HEADER groups an
employee's time entries over a PERIOD and goes through HEADER-LEVEL approval; ``TimeEntry`` lines
hang off it, each carrying an ALLOCATION to a project and/or a cost centre — the CATS
account-assignment deliverable.

- ``Timesheet`` is the period HEADER. It claims a gapless ``TS-`` ``timesheet_number`` at creation
  (the leave-request claim-at-create precedent, D-040/D-053) but is NOT a docflow document (no
  DocumentMixin — a timesheet has no successor document in v1; payroll 10.4 + project costing 11
  READ its approved entries via ``hr/queries``, not via docflow). Composite tenant FK to
  ``hr_employees``. ``total_hours`` is a MAINTAINED sum of the entry ``hours`` (kept in step by the
  service on every line add/update/remove — a denormalized running total, the stock-balance
  precedent, NOT audited separately). UNIQUE(tenant, employee_id, period_start) — one timesheet per
  employee per period.

- ``TimeEntry`` is a line. Composite tenant FK to ``hr_timesheets``. ``entry_date`` falls within
  the header period (validated in the service). ``hours`` is a QuantityType, CHECK > 0. The
  ALLOCATION: ``project_id`` is a NULLABLE OPAQUE Uuid — NOT validated against any table in v1
  because the PROJECTS module is Phase 11 (NOT YET BUILT); it is a free opaque reference, the
  projects-module validation hook wires up when ``projects/queries`` exists in Phase 11 (D-054,
  D-029). By contrast ``cost_center_id`` IS a real validated opaque finance cost-centre id
  (nullable, validated via ``finance/queries.cost_center_exists`` when set — D-029, never a
  cross-module FK). ``is_billable`` flags billable work for later project costing. Index
  (tenant, timesheet_id) for the lines-of-a-sheet read; index (tenant, cost_center_id) +
  (tenant, project_id) for the allocation aggregates.

CROSS-MODULE / SOFT IDS ARE OPAQUE (D-029/§5). ``approved_by`` is the deciding user — an OPAQUE core
users id (nullable, no FK, the leave-request precedent). ``project_id`` / ``cost_center_id`` are
opaque per the docstrings above.

Hours use the D-015 ``QuantityType`` (scale-6, exact on both engines) — a plain ``sa.Numeric`` would
round-trip through float on SQLite and lose precision, so it is never used for stored hours here.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import QuantityType
from app.modules.hr.constants import TimesheetStatus


class Timesheet(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A TIMESHEET header (D-054): an employee's time entries for one period, approved as a whole.

    Composite tenant FK to ``hr_employees``. Claims a gapless ``TS-`` ``timesheet_number`` at
    creation (unique per tenant). ``period_start``/``period_end`` (Date) bracket the period
    (``end >= start`` enforced in the service); UNIQUE(tenant, employee_id, period_start) so one
    employee has at most one timesheet per period. ``status`` runs the ``TimesheetStatus``
    lifecycle. ``total_hours`` (QuantityType) is the MAINTAINED sum of the entry hours, kept in step
    by the service on every line change. ``submitted_at`` / ``approved_at`` / ``approved_by``
    (OPAQUE core users id, no FK) capture the workflow. Audited (D-010): a tracked time document.
    """

    __tablename__ = "hr_timesheets"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "timesheet_number", name="uq_hr_timesheets_tenant_id_timesheet_number"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            "period_start",
            name="uq_hr_timesheets_tenant_employee_period",
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_hr_timesheets_period_order"
        ),
        sa.CheckConstraint("total_hours >= 0", name="ck_hr_timesheets_total_hours_non_negative"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hr_employees", "employee_id"),
        # The list filters on (tenant, employee_id, status); the period filter narrows further
        # (PERFORMANCE §1).
        sa.Index(
            "ix_hr_timesheets_tenant_id_employee_id_status",
            "tenant_id",
            "employee_id",
            "status",
        ),
    )

    timesheet_number: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    period_start: Mapped[date] = mapped_column(sa.Date, nullable=False)
    period_end: Mapped[date] = mapped_column(sa.Date, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=TimesheetStatus.DRAFT.value,
        server_default="DRAFT",
    )
    total_hours: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    submitted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    # The deciding user (OPAQUE core users id, no FK — the leave-request approved_by precedent).
    approved_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class TimeEntry(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """A TIME ENTRY line (D-054): ``hours`` worked on ``entry_date``, allocated to a project and/or
    a cost centre — the CATS account-assignment deliverable.

    Composite tenant FK to ``hr_timesheets``. ``entry_date`` must fall within the header period
    (validated in the service); ``hours`` (QuantityType) is CHECK > 0. THE ALLOCATION:
    ``project_id`` is a NULLABLE OPAQUE Uuid NOT validated in v1 — the projects module is Phase 11
    (not yet built), so it is a free opaque reference until ``projects/queries`` exists (D-054).
    ``cost_center_id`` is a nullable OPAQUE finance cost-centre id VALIDATED via
    ``finance/queries.cost_center_exists`` when set (D-029). ``task_description`` is free text;
    ``is_billable`` flags billable work (default false). NOT audited (a high-churn child line, the
    journal-line / stock-move precedent — the audited unit is the header).
    """

    __tablename__ = "hr_time_entries"
    __table_args__ = (
        sa.CheckConstraint("hours > 0", name="ck_hr_time_entries_hours_positive"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hr_timesheets", "timesheet_id"),
        # The lines-of-a-timesheet read filters on (tenant, timesheet_id). Entries can repeat per
        # day/project, so NO unique constraint on the line (PLAN 10.3).
        sa.Index("ix_hr_time_entries_tenant_id_timesheet_id", "tenant_id", "timesheet_id"),
        # The allocation aggregates group by cost centre / project over a date range
        # (PERFORMANCE §2).
        sa.Index(
            "ix_hr_time_entries_tenant_id_cost_center_id", "tenant_id", "cost_center_id"
        ),
        sa.Index("ix_hr_time_entries_tenant_id_project_id", "tenant_id", "project_id"),
    )

    timesheet_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    entry_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    # Opaque PROJECTS-module id (D-054/D-029): NOT validated in v1 (projects is Phase 11, not yet
    # built); a free opaque reference, the validation hook wires up when projects/queries exists.
    project_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # Opaque finance cost-centre id (D-029): VALIDATED via finance/queries when set; no cross-module
    # FK.
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    task_description: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    is_billable: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )

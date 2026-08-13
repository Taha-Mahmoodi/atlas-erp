"""HR leave models (PLAN 10.2, parity HCM "Leave and absence management" = Full): the ``LeaveType``
configuration, the running ``LeaveBalance`` per employee per type, and the ``LeaveRequest`` doc.

THREE tables, one concern (leave), the D-053 model:

- ``LeaveType`` is a MASTER keyed by a USER-SUPPLIED ``code`` unique per tenant (the item-code /
  leave-config precedent — no gapless number, no DocumentMixin). It defines the accrual cadence
  (``accrual_frequency``), the per-period grant (``accrual_amount``, a ``QuantityType`` so
  1.67/month is exact, D-015), an optional accrual cap (``max_balance``), whether the leave is paid,
  and active.
- ``LeaveBalance`` is the RUNNING balance per (employee, type): ``balance_days`` available now,
  ``accrued_to_date`` and ``taken_to_date`` for traceability, and ``last_accrual_period`` — the
  most recently granted period (informational; see ``LeaveAccrual``). UNIQUE(tenant, employee,
  type).
- ``LeaveAccrual`` is the accrual-run IDEMPOTENCY GUARD (#160): one row per APPLIED
  (balance, period). The run skips any pair already recorded for its period, so re-running ANY
  previously applied period — not just the latest — grants nothing.
- ``LeaveRequest`` is the request DOCUMENT: it claims a gapless ``LV-`` ``request_number`` at
  creation (D-040 claim-at-create precedent) but is NOT a docflow document (no DocumentMixin — a
  leave request has no successor document in v1). ``days`` is caller-supplied (a ``QuantityType``
  validated > 0; ``start_date``/``end_date`` are stored for reference, ``end >= start`` enforced in
  the service — calendar/business-day computation from the dates is the documented later, D-053).
  ``status`` runs the lifecycle; ``approved_by`` / ``decided_at`` capture the decision.

ALL THREE are composite-tenant-FK'd to their parents (employee, leave type), so a child can never
point at a parent of another tenant. ``approved_by`` is an OPAQUE core users id (the deciding
user — nullable, no hard FK to core_users, the ``Employee.user_id`` precedent, D-029).
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
from app.modules.hr.constants import (
    AccrualFrequency,
    LeaveRequestStatus,
    LeaveUnit,
)


class LeaveType(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A LEAVE TYPE (D-053): the configuration of one kind of leave (annual, sick, …).

    ``code`` is USER-SUPPLIED and unique per tenant. ``accrual_frequency`` (AccrualFrequency) and
    ``accrual_amount`` (QuantityType — days per period) drive the accrual run; ``max_balance``
    (QuantityType, nullable) caps the accrued balance (None = uncapped). ``unit`` is the tracking
    unit (DAYS in v1). ``is_paid`` flags paid leave; ``is_active`` flags a retired type the accrual
    run skips. Audited (D-010): leave config drives balances.
    """

    __tablename__ = "hr_leave_types"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_hr_leave_types_tenant_id_code"),
        sa.CheckConstraint("accrual_amount >= 0", name="ck_hr_leave_types_accrual_non_negative"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # The accrual run filters on (tenant, accrual_frequency, is_active) (PERFORMANCE §1/§2).
        sa.Index(
            "ix_hr_leave_types_tenant_id_accrual_frequency_is_active",
            "tenant_id",
            "accrual_frequency",
            "is_active",
        ),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    accrual_frequency: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=AccrualFrequency.MONTHLY.value,
        server_default="MONTHLY",
    )
    accrual_amount: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    max_balance: Mapped[Decimal | None] = mapped_column(QuantityType(), nullable=True)
    unit: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=LeaveUnit.DAYS.value, server_default="DAYS"
    )
    is_paid: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )


class LeaveBalance(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """The RUNNING leave balance per (employee, leave type) (D-053).

    Composite tenant FKs to ``hr_employees`` and ``hr_leave_types``. UNIQUE(tenant, employee, type)
    — one balance row per pairing. ``balance_days`` (QuantityType) is the currently available amount
    the approve step decrements and a cancel-of-approved restores; ``accrued_to_date`` /
    ``taken_to_date`` are running totals for traceability. ``last_accrual_period`` is the period
    (YYYY-MM for MONTHLY, YYYY for ANNUAL) of the most recent run that granted this balance —
    INFORMATIONAL ONLY since #160: the idempotency guard is ``LeaveAccrual``, which remembers EVERY
    applied period (the single column forgot older periods, so re-running N after N+1 double-granted
    N, D-063). NOT audited (a high-churn running total, the stock-balance precedent).
    """

    __tablename__ = "hr_leave_balances"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            "leave_type_id",
            name="uq_hr_leave_balances_tenant_employee_type",
        ),
        sa.CheckConstraint(
            "accrued_to_date >= 0", name="ck_hr_leave_balances_accrued_non_negative"
        ),
        sa.CheckConstraint("taken_to_date >= 0", name="ck_hr_leave_balances_taken_non_negative"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hr_employees", "employee_id"),
        tenant_fk("hr_leave_types", "leave_type_id"),
        # Balances-for-employee reads filter on (tenant, employee_id) (PERFORMANCE §1).
        sa.Index("ix_hr_leave_balances_tenant_id_employee_id", "tenant_id", "employee_id"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    leave_type_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    balance_days: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    accrued_to_date: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    taken_to_date: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    # The period of the most recent accrual run that granted this balance (YYYY-MM / YYYY), or
    # None before the first accrual. Informational since #160 — the idempotency guard is the
    # LeaveAccrual applied-periods table, which remembers every period, not just the last.
    last_accrual_period: Mapped[str | None] = mapped_column(sa.String(7), nullable=True)


class LeaveAccrual(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One APPLIED accrual per (balance, period) — the accrual-run idempotency guard (#160,
    D-063).

    D-053 stamped a single ``last_accrual_period`` on the balance, which forgot older periods:
    running period N, then N+1, then N again re-granted N (QA reproduced a double-grant). The run
    now records every granted (balance, period) here and skips any pair already recorded for its
    period, so re-running ANY previously applied period grants nothing. UNIQUE(tenant, balance,
    period) is the DB backstop against a concurrent same-period double-grant. NOT audited (a
    mechanical guard row, the balance precedent).
    """

    __tablename__ = "hr_leave_accruals"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "balance_id",
            "period",
            name="uq_hr_leave_accruals_tenant_balance_period",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hr_leave_balances", "balance_id"),
        # The run reads the applied balance ids for (tenant, period) in one query (PERFORMANCE §1).
        sa.Index("ix_hr_leave_accruals_tenant_id_period", "tenant_id", "period"),
    )

    balance_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # The applied period key (YYYY-MM for MONTHLY, YYYY for ANNUAL).
    period: Mapped[str] = mapped_column(sa.String(7), nullable=False)


class LeaveRequest(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A LEAVE REQUEST (D-053): an employee's request to take ``days`` of a leave type over a date
    range, routed DRAFT → SUBMITTED → APPROVED/REJECTED (or CANCELLED).

    Composite tenant FKs to ``hr_employees`` and ``hr_leave_types``. Claims a gapless ``LV-``
    ``request_number`` at creation (unique per tenant). ``days`` (QuantityType) is caller-supplied
    and validated > 0; ``start_date``/``end_date`` are stored for reference (``end >= start``
    enforced in the service). ``status`` runs the lifecycle; ``reason``/``notes`` are free text.
    ``approved_by`` (OPAQUE core users id, nullable, no FK) + ``decided_at`` capture the decision.
    Audited (D-010): a request is a tracked document. Index (tenant, employee_id, status) serves the
    employee-requests-by-status reads + the list filter.
    """

    __tablename__ = "hr_leave_requests"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "request_number", name="uq_hr_leave_requests_tenant_id_request_number"
        ),
        sa.CheckConstraint("days > 0", name="ck_hr_leave_requests_days_positive"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hr_employees", "employee_id"),
        tenant_fk("hr_leave_types", "leave_type_id"),
        sa.Index(
            "ix_hr_leave_requests_tenant_id_employee_id_status",
            "tenant_id",
            "employee_id",
            "status",
        ),
    )

    request_number: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    leave_type_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    start_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    end_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    days: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=LeaveRequestStatus.DRAFT.value,
        server_default="DRAFT",
    )
    reason: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    # The deciding user (OPAQUE core users id, no FK — the Employee.user_id precedent, D-029).
    approved_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)

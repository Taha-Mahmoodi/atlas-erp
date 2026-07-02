"""HR payroll request/response schemas (Pydantic v2, ApiModel base) for PLAN 10.4, D-055.

Split out of ``schemas.py`` (which is at the 400-line cap) into a sibling file, the
``time_schemas.py`` / finance ``*_schemas.py`` precedent (STRUCTURE §8.4). Create/Read/Filter for
the ``PayrollRun`` header (no Update — a run's figures are derived at creation and a run is
recomputed by deleting+recreating, not edited; status changes go through post/cancel), the line
read, and the run-with-lines read.

THE NON-COMPLIANCE FLAG (D-055): the flat ``tax_rate_percent`` is the ONLY withholding model —
no brackets, no social security, no deductions. ``base_salary`` is taken as the period gross with
no proration. See docs/modules/hr.md.

Money amounts are ``Decimal`` strings (D-015). The Read schemas carry the server-derived fields
(run number, totals, employee_count, journal link, timestamps).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.hr.constants import PayrollRunStatus

# --- Payroll run --------------------------------------------------------------


class PayrollRunCreate(ApiModel):
    """Create a DRAFT payroll run over a period for a set of employees (or all active when none is
    given). ``period_end`` >= ``period_start`` (validated in the service); ``pay_date`` is the
    journal posting date. ``tax_rate_percent`` is the FLAT withholding rate for the run (omit to use
    the per-tenant default — D-055). ``employee_ids`` selects which active employees to include;
    ``None`` means every active employee with a ``base_salary``. ``currency_code`` defaults to the
    tenant's functional currency when omitted. The run computes one line per included employee
    (gross = base_salary, tax = gross × rate, net = gross − tax) and the maintained totals."""

    period_start: date
    period_end: date
    pay_date: date
    tax_rate_percent: Decimal | None = None
    employee_ids: list[uuid.UUID] | None = None
    currency_code: str | None = None
    notes: str | None = None


class PayrollRunPost(ApiModel):
    """The post-payroll action payload (PLAN 10.4): ``notes`` is an optional note recorded on the
    run at posting. The endpoint is a distinct ``/post`` route, so the verb is in the route."""

    notes: str | None = None


class PayrollRunLineRead(ApiModel):
    """One employee's payroll line: gross → tax → net with the cost-centre allocation. ``gross =
    tax + net`` per line (the balancing invariant, D-055)."""

    id: uuid.UUID
    payroll_run_id: uuid.UUID
    employee_id: uuid.UUID
    gross_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal
    cost_center_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PayrollRunRead(ApiModel):
    """A payroll run header. ``run_number`` is the gapless ``PAY-`` number (None until posted —
    claimed at posting, D-012). ``total_gross == total_tax + total_net`` always (D-055).
    ``journal_entry_id`` links the posted consolidated journal."""

    id: uuid.UUID
    run_number: str | None
    status: PayrollRunStatus
    period_start: date
    period_end: date
    pay_date: date
    tax_rate_percent: Decimal
    total_gross: Decimal
    total_tax: Decimal
    total_net: Decimal
    employee_count: int
    currency_code: str
    journal_entry_id: uuid.UUID | None
    posted_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PayrollRunDetail(PayrollRunRead):
    """A payroll run plus its per-employee lines (the GET /{id} detail view, PLAN 10.4)."""

    lines: list[PayrollRunLineRead]


class PayrollRunFilter(ApiModel):
    """List filters. None means "no constraint"; folded into the cursor's filter fingerprint so a
    cursor cannot cross filtered views. ``period_from`` / ``period_to`` bound the run period
    (period_start within the range)."""

    status: PayrollRunStatus | None = None
    period_from: date | None = None
    period_to: date | None = None

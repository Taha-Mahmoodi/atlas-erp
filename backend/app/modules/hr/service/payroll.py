"""Payroll-run creation, reads and cancel (PLAN 10.4, D-055): compute a DRAFT gross→net run and
cancel a draft.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. The POST flow (publish
``PayrollPosted`` → finance posts the consolidated journal) lives in ``payroll_post.py`` (the
production ``production_orders``/``production_post`` split precedent) so each file stays under the
400-line cap.

THE GROSS→NET FLAT-TAX MODEL (the headline of 10.4, D-055) — SIMPLISTIC AND NOT
JURISDICTION-COMPLIANT. For each included active employee with a ``base_salary``:
- ``gross = base_salary`` (the period gross, NO proration — base_salary IS the per-period gross).
- ``tax = quantize(gross × tax_rate_percent / 100)`` (a single flat withholding rate — no brackets,
  no social security, no deductions).
- ``net = gross − tax`` (so ``gross == tax + net`` per line — the balancing invariant).
Employees WITHOUT a ``base_salary`` are SKIPPED (no line, not counted). The run claims its gapless
``PAY-`` number at POSTING, not here (D-012) — a draft burns no number.

``from __future__ import annotations`` keeps the model annotations strings at import.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.money import quantize_for_currency
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.hr import queries as hr_queries
from app.modules.hr.constants import (
    DEFAULT_PAYROLL_TAX_RATE_PERCENT,
    PAYROLL_RUN_DOC_TYPE,
    EmploymentStatus,
    PayrollRunStatus,
)
from app.modules.hr.models import Employee, PayrollRun, PayrollRunLine
from app.modules.hr.payroll_schemas import PayrollRunCreate, PayrollRunFilter

_HUNDRED = Decimal(100)


async def get_payroll_run(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> PayrollRun:
    """The payroll run with ``run_id`` in the tenant, or 404. A point lookup on the PK."""
    run = await session.get(PayrollRun, run_id)
    if run is None or run.tenant_id != tenant_id:
        raise NotFoundError(message="Payroll run not found", code="hr.payroll_run_not_found")
    return run


async def list_payroll_runs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: PayrollRunFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[PayrollRun]:
    """Keyset-paginated payroll runs, newest period first (D-014). The status / period-range filters
    fold into the cursor fingerprint; the (tenant, status) + (tenant, period_start) indexes serve
    the filtered page (PERFORMANCE §6)."""
    stmt = select(PayrollRun).where(PayrollRun.tenant_id == tenant_id)
    if filters.status is not None:
        stmt = stmt.where(PayrollRun.status == filters.status)
    if filters.period_from is not None:
        stmt = stmt.where(PayrollRun.period_start >= filters.period_from)
    if filters.period_to is not None:
        stmt = stmt.where(PayrollRun.period_start <= filters.period_to)
    fingerprint = filter_fingerprint(
        filters.status, filters.period_from, filters.period_to
    )
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(PayrollRun.period_start, SortDirection.DESC)],
        pk=PayrollRun.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


async def list_payroll_lines(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> list[PayrollRunLine]:
    """The per-employee lines of one payroll run (D-055). 404 if the run does not exist (a clean
    error over the wire)."""
    await get_payroll_run(session, tenant_id, run_id)
    return await hr_queries.payroll_lines_for_run(session, tenant_id, run_id)


async def create_payroll_run(
    session: AsyncSession, tenant_id: uuid.UUID, payload: PayrollRunCreate
) -> PayrollRun:
    """Compute a DRAFT payroll run (D-055). For each selected active employee with a
    ``base_salary``, builds a line (gross = base_salary, tax = gross × rate, net = gross − tax),
    resolves the employee's department cost centre for the salary-expense allocation, and sums the
    maintained totals.

    ``employee_ids`` selects which active employees to include; ``None`` = every active employee.
    Employees without a ``base_salary`` are skipped. ``tax_rate_percent`` defaults to the per-tenant
    flat default; ``currency_code`` defaults to the tenant's functional currency. Registers the run
    document (no number — claimed at posting, D-012). A run with NO payable employee is a 422 (an
    empty run has nothing to post)."""
    if payload.period_end < payload.period_start:
        raise ValidationFailedError(
            message="The period end cannot be before the period start",
            code="hr.payroll_period_invalid",
            details={
                "period_start": str(payload.period_start),
                "period_end": str(payload.period_end),
            },
        )
    rate = (
        payload.tax_rate_percent
        if payload.tax_rate_percent is not None
        else Decimal(DEFAULT_PAYROLL_TAX_RATE_PERCENT)
    )
    if rate < 0 or rate > _HUNDRED:
        raise ValidationFailedError(
            message="The tax rate percent must be between 0 and 100",
            code="hr.payroll_tax_rate_invalid",
            details={"tax_rate_percent": str(rate)},
        )
    currency = payload.currency_code or await finance_queries.functional_currency_or_none(
        session, tenant_id
    )
    if currency is None:
        raise ValidationFailedError(
            message="No currency supplied and the tenant has no functional currency configured",
            code="hr.payroll_currency_unresolved",
        )

    employees = await _resolve_payable_employees(session, tenant_id, payload.employee_ids)
    if not employees:
        raise ValidationFailedError(
            message="No active employee with a base salary matched this run",
            code="hr.payroll_no_payable_employees",
        )

    run_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        PAYROLL_RUN_DOC_TYPE,
        run_id,
        doc_number=None,
        status=PayrollRunStatus.DRAFT.value,
    )
    run = PayrollRun(
        id=run_id,
        tenant_id=tenant_id,
        document_id=document.id,
        status=PayrollRunStatus.DRAFT.value,
        period_start=payload.period_start,
        period_end=payload.period_end,
        pay_date=payload.pay_date,
        tax_rate_percent=rate,
        currency_code=currency,
        total_gross=Decimal(0),
        total_tax=Decimal(0),
        total_net=Decimal(0),
        employee_count=0,
        notes=payload.notes,
    )
    session.add(run)

    total_gross = Decimal(0)
    total_tax = Decimal(0)
    total_net = Decimal(0)
    for employee in employees:
        gross = quantize_for_currency(Decimal(employee.base_salary), currency)
        tax = quantize_for_currency(gross * rate / _HUNDRED, currency)
        net = gross - tax
        session.add(
            PayrollRunLine(
                tenant_id=tenant_id,
                payroll_run_id=run_id,
                employee_id=employee.id,
                gross_amount=gross,
                tax_amount=tax,
                net_amount=net,
                cost_center_id=await _employee_cost_center(session, tenant_id, employee),
            )
        )
        total_gross += gross
        total_tax += tax
        total_net += net

    run.total_gross = total_gross
    run.total_tax = total_tax
    run.total_net = total_net
    run.employee_count = len(employees)
    await session.flush()
    return run


async def _resolve_payable_employees(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_ids: list[uuid.UUID] | None,
) -> list[Employee]:
    """The ACTIVE employees with a ``base_salary`` to pay (D-055): every active employee when
    ``employee_ids`` is None, else exactly those (each must exist + be active). Employees without a
    ``base_salary`` are filtered out (skipped — documented). Ordered by employee_code so the lines
    and the cost-centre allocation are deterministic."""
    stmt = (
        select(Employee)
        .where(
            Employee.tenant_id == tenant_id,
            Employee.status == EmploymentStatus.ACTIVE.value,
        )
        .order_by(Employee.employee_code)
    )
    if employee_ids is not None:
        if not employee_ids:
            return []
        stmt = stmt.where(Employee.id.in_(employee_ids))
    employees = list((await session.execute(stmt)).scalars().all())
    return [e for e in employees if e.base_salary is not None]


async def _employee_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, employee: Employee
) -> uuid.UUID | None:
    """The employee's department cost centre for the salary-expense allocation (D-055): the
    ``cost_center_id`` on the employee's department (an opaque finance id, D-029), or None when the
    employee has no department or the department carries no cost centre."""
    if employee.department_id is None:
        return None
    department = await hr_queries.get_department(session, tenant_id, employee.department_id)
    return department.cost_center_id if department is not None else None


async def cancel_payroll_run(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> PayrollRun:
    """Cancel a DRAFT payroll run (D-055): DRAFT → CANCELLED. Only a draft can be cancelled — a
    posted run is corrected by reversing its journal in finance, never cancelled. Terminal; no GL
    effect (the run never posted). Lines are left in place for audit/history."""
    run = await get_payroll_run(session, tenant_id, run_id)
    if PayrollRunStatus(run.status) != PayrollRunStatus.DRAFT:
        raise ConflictError(
            message="Only a draft payroll run can be cancelled",
            code="hr.payroll_run_not_draft",
            details={"status": run.status},
        )
    run.status = PayrollRunStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, run.document_id, status=PayrollRunStatus.CANCELLED.value
    )
    return run

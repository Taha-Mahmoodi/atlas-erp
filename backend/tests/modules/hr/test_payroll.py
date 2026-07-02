"""Payroll-run computation tests (PLAN 10.4, D-055): the flat-tax gross→net math, totals, skipping
employees without a salary, and the cost-centre resolution — all at the SERVICE layer.

THE NON-COMPLIANCE FLAG (D-055): these prove the SIMPLISTIC flat-tax model (gross × rate
withholding, net = gross − tax, no brackets/deductions). The post-to-journal flow lives in
test_payroll_post.py; the endpoints + RBAC in test_payroll_api.py.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.hr import queries as hr_queries
from app.modules.hr import service
from app.modules.hr.constants import PayrollRunStatus
from app.modules.hr.payroll_schemas import PayrollRunCreate
from tests.modules.hr.payroll_factories import (
    PayrollSetup,
    build_payroll_setup,
    build_unsalaried_employee,
)


async def _run_create(
    session: AsyncSession, setup: PayrollSetup, payload: PayrollRunCreate
):
    """Create a payroll run through the uow (so events would drain — create publishes none)."""
    holder: dict[str, object] = {}

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            holder["run"] = await service.create_payroll_run(
                session, setup.tenant_id, payload
            )

    with tenant_context(setup.tenant_id):
        await run_in_uow(session, work)
    return holder["run"]


def _payload(setup: PayrollSetup, **overrides) -> PayrollRunCreate:
    base = dict(
        period_start="2026-06-01",
        period_end="2026-06-30",
        pay_date="2026-06-30",
        tax_rate_percent=Decimal("20"),
    )
    base.update(overrides)
    return PayrollRunCreate(**base)


async def test_create_computes_gross_tax_net_per_flat_rate(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A run computes gross = base_salary, tax = gross × rate, net = gross − tax per employee, and
    the maintained totals — the flat-tax model (D-055)."""
    setup = await build_payroll_setup(
        db_session, tenant_a, salaries=(Decimal("5000"), Decimal("3000"))
    )
    run = await _run_create(db_session, setup, _payload(setup, tax_rate_percent=Decimal("20")))

    with tenant_context(tenant_a):
        lines = await hr_queries.payroll_lines_for_run(db_session, tenant_a, run.id)
    by_gross = {Decimal(line.gross_amount): line for line in lines}
    # 5000 → tax 1000, net 4000; 3000 → tax 600, net 2400.
    assert Decimal(by_gross[Decimal("5000")].tax_amount) == Decimal("1000")
    assert Decimal(by_gross[Decimal("5000")].net_amount) == Decimal("4000")
    assert Decimal(by_gross[Decimal("3000")].tax_amount) == Decimal("600")
    assert Decimal(by_gross[Decimal("3000")].net_amount) == Decimal("2400")
    assert Decimal(run.total_gross) == Decimal("8000")
    assert Decimal(run.total_tax) == Decimal("1600")
    assert Decimal(run.total_net) == Decimal("6400")
    assert run.employee_count == 2
    assert run.status == PayrollRunStatus.DRAFT.value
    # The balancing invariant holds at the header level too.
    assert Decimal(run.total_gross) == Decimal(run.total_tax) + Decimal(run.total_net)


async def test_create_per_line_balancing_invariant(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Every line satisfies gross == tax + net (D-055) even with a fractional, quantizing rate."""
    setup = await build_payroll_setup(
        db_session, tenant_a, salaries=(Decimal("3333.33"),)
    )
    run = await _run_create(
        db_session, setup, _payload(setup, tax_rate_percent=Decimal("12.5"))
    )
    with tenant_context(tenant_a):
        lines = await hr_queries.payroll_lines_for_run(db_session, tenant_a, run.id)
    for line in lines:
        assert Decimal(line.gross_amount) == Decimal(line.tax_amount) + Decimal(line.net_amount)
    assert Decimal(run.total_gross) == Decimal(run.total_tax) + Decimal(run.total_net)


async def test_default_tax_rate_applies_when_omitted(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Omitting tax_rate_percent applies the per-tenant flat default (20%) (D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("1000"),))
    run = await _run_create(
        db_session, setup, _payload(setup, tax_rate_percent=None)
    )
    assert Decimal(run.tax_rate_percent) == Decimal("20")
    assert Decimal(run.total_tax) == Decimal("200")
    assert Decimal(run.total_net) == Decimal("800")


async def test_create_skips_employees_without_a_salary(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An active employee with NO base_salary produces no line and is not counted (D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("4000"),))
    await build_unsalaried_employee(db_session, tenant_a, setup.department_id)
    run = await _run_create(db_session, setup, _payload(setup))
    assert run.employee_count == 1
    with tenant_context(tenant_a):
        lines = await hr_queries.payroll_lines_for_run(db_session, tenant_a, run.id)
    assert len(lines) == 1
    assert Decimal(run.total_gross) == Decimal("4000")


async def test_create_resolves_employee_cost_center(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Each line carries the employee's department cost centre for the salary-expense allocation
    (D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("5000"),))
    run = await _run_create(db_session, setup, _payload(setup))
    with tenant_context(tenant_a):
        lines = await hr_queries.payroll_lines_for_run(db_session, tenant_a, run.id)
    assert lines[0].cost_center_id == setup.cost_center_id


async def test_create_cost_center_none_when_department_has_no_cost_center(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An employee whose department carries no cost centre gets a None cost-centre line (D-055)."""
    setup = await build_payroll_setup(
        db_session, tenant_a, salaries=(Decimal("5000"),), with_cost_center=False
    )
    run = await _run_create(db_session, setup, _payload(setup))
    with tenant_context(tenant_a):
        lines = await hr_queries.payroll_lines_for_run(db_session, tenant_a, run.id)
    assert lines[0].cost_center_id is None


async def test_create_specific_employee_ids_subset(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """``employee_ids`` selects exactly those employees (D-055)."""
    setup = await build_payroll_setup(
        db_session, tenant_a, salaries=(Decimal("5000"), Decimal("3000"))
    )
    run = await _run_create(
        db_session, setup, _payload(setup, employee_ids=[setup.employee_ids[0]])
    )
    assert run.employee_count == 1
    assert Decimal(run.total_gross) == Decimal("5000")


async def test_create_no_payable_employees_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A run matching no salaried employee is a 422 (an empty run has nothing to post, D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=())
    await build_unsalaried_employee(db_session, tenant_a, setup.department_id)
    with pytest.raises(ValidationFailedError) as exc:
        await _run_create(db_session, setup, _payload(setup))
    assert exc.value.code == "hr.payroll_no_payable_employees"


async def test_create_invalid_period_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """period_end before period_start is a 422 (D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("1000"),))
    with pytest.raises(ValidationFailedError) as exc:
        await _run_create(
            db_session,
            setup,
            _payload(setup, period_start="2026-06-30", period_end="2026-06-01"),
        )
    assert exc.value.code == "hr.payroll_period_invalid"


async def test_create_invalid_rate_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A tax rate outside [0, 100] is a 422 (D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("1000"),))
    with pytest.raises(ValidationFailedError) as exc:
        await _run_create(db_session, setup, _payload(setup, tax_rate_percent=Decimal("150")))
    assert exc.value.code == "hr.payroll_tax_rate_invalid"


async def test_cancel_draft_run(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """A DRAFT run cancels to CANCELLED (D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("1000"),))
    run = await _run_create(db_session, setup, _payload(setup))
    run_id = run.id

    async def work() -> None:
        with tenant_context(tenant_a):
            await service.cancel_payroll_run(db_session, tenant_a, run_id)

    with tenant_context(tenant_a):
        await run_in_uow(db_session, work)
    with tenant_context(tenant_a):
        reloaded = await hr_queries.get_payroll_run(db_session, tenant_a, run_id)
    assert reloaded.status == PayrollRunStatus.CANCELLED.value


async def test_cancel_non_draft_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Cancelling an already-CANCELLED run is a conflict (D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("1000"),))
    run = await _run_create(db_session, setup, _payload(setup))
    run_id = run.id

    async def cancel() -> None:
        with tenant_context(tenant_a):
            await service.cancel_payroll_run(db_session, tenant_a, run_id)

    with tenant_context(tenant_a):
        await run_in_uow(db_session, cancel)
    with pytest.raises(ConflictError) as exc, tenant_context(tenant_a):
        await run_in_uow(db_session, cancel)
    assert exc.value.code == "hr.payroll_run_not_draft"

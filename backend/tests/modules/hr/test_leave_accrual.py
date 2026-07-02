"""Leave accrual run (PLAN 10.2, D-053): grants the right amount, caps at max_balance, is idempotent
for the same period (a re-run grants nothing), and only touches ACTIVE employees + ACTIVE leave
types of the run's frequency.

Driven through the real service under the tenant context (D-025).
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.hr import queries as hr_queries
from app.modules.hr import service
from app.modules.hr.constants import AccrualFrequency, EmploymentStatus
from tests.modules.hr.conftest import HrSetup
from tests.modules.hr.factories import build_employee, build_leave_type

_JUNE = date(2026, 6, 15)


async def _balance(
    session: AsyncSession, tenant_id, employee_id, leave_type_id
) -> Decimal | None:
    with tenant_context(tenant_id):
        bal = await hr_queries.get_leave_balance(session, tenant_id, employee_id, leave_type_id)
    return bal.balance_days if bal is not None else None


async def test_accrual_grants_the_amount(db_session: AsyncSession, hr_setup: HrSetup) -> None:
    employee = await build_employee(db_session, hr_setup.tenant_id, employee_code="EMP-ACC1")
    leave_type = await build_leave_type(
        db_session, hr_setup.tenant_id, code="LT-G", accrual_amount=Decimal("2")
    )
    with tenant_context(hr_setup.tenant_id):
        period, accrued = await service.accrue_leave(
            db_session, hr_setup.tenant_id, as_of=_JUNE, frequency=AccrualFrequency.MONTHLY
        )
        await db_session.commit()
    assert period == "2026-06"
    assert accrued == 1
    bal = await _balance(db_session, hr_setup.tenant_id, employee.id, leave_type.id)
    assert bal == Decimal("2")


async def test_accrual_caps_at_max_balance(db_session: AsyncSession, hr_setup: HrSetup) -> None:
    employee = await build_employee(db_session, hr_setup.tenant_id, employee_code="EMP-ACC2")
    leave_type = await build_leave_type(
        db_session,
        hr_setup.tenant_id,
        code="LT-CAP",
        accrual_amount=Decimal("8"),
        max_balance=Decimal("10"),
    )
    # First run: 0 -> 8.
    with tenant_context(hr_setup.tenant_id):
        await service.accrue_leave(
            db_session,
            hr_setup.tenant_id,
            as_of=date(2026, 6, 1),
            frequency=AccrualFrequency.MONTHLY,
        )
        await db_session.commit()
    # Next month: 8 + 8 would be 16, clamped to the cap 10.
    with tenant_context(hr_setup.tenant_id):
        await service.accrue_leave(
            db_session,
            hr_setup.tenant_id,
            as_of=date(2026, 7, 1),
            frequency=AccrualFrequency.MONTHLY,
        )
        await db_session.commit()
    assert await _balance(
        db_session, hr_setup.tenant_id, employee.id, leave_type.id
    ) == Decimal("10")


async def test_accrual_idempotent_same_period(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await build_employee(db_session, hr_setup.tenant_id, employee_code="EMP-ACC3")
    leave_type = await build_leave_type(
        db_session, hr_setup.tenant_id, code="LT-IDEM", accrual_amount=Decimal("2")
    )
    with tenant_context(hr_setup.tenant_id):
        await service.accrue_leave(
            db_session, hr_setup.tenant_id, as_of=_JUNE, frequency=AccrualFrequency.MONTHLY
        )
        await db_session.commit()
    # A second run for the SAME month grants nothing (the last_accrual_period guard).
    with tenant_context(hr_setup.tenant_id):
        _, accrued = await service.accrue_leave(
            db_session,
            hr_setup.tenant_id,
            as_of=date(2026, 6, 28),
            frequency=AccrualFrequency.MONTHLY,
        )
        await db_session.commit()
    assert accrued == 0
    bal = await _balance(db_session, hr_setup.tenant_id, employee.id, leave_type.id)
    assert bal == Decimal("2")


async def test_accrual_skips_inactive_employees_and_types(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    active = await build_employee(db_session, hr_setup.tenant_id, employee_code="EMP-ON")
    terminated = await build_employee(
        db_session,
        hr_setup.tenant_id,
        employee_code="EMP-OFF",
        status=EmploymentStatus.TERMINATED,
    )
    monthly = await build_leave_type(
        db_session, hr_setup.tenant_id, code="LT-ON", accrual_amount=Decimal("2")
    )
    inactive_type = await build_leave_type(
        db_session,
        hr_setup.tenant_id,
        code="LT-OFF",
        accrual_amount=Decimal("2"),
        is_active=False,
    )
    annual_type = await build_leave_type(
        db_session,
        hr_setup.tenant_id,
        code="LT-ANN",
        accrual_frequency=AccrualFrequency.ANNUAL,
        accrual_amount=Decimal("20"),
    )
    with tenant_context(hr_setup.tenant_id):
        _, accrued = await service.accrue_leave(
            db_session, hr_setup.tenant_id, as_of=_JUNE, frequency=AccrualFrequency.MONTHLY
        )
        await db_session.commit()
    # Only the ACTIVE employee × the ACTIVE MONTHLY type -> one balance granted.
    assert accrued == 1
    assert await _balance(
        db_session, hr_setup.tenant_id, active.id, monthly.id
    ) == Decimal("2")
    # The terminated employee, the inactive type and the (wrong-frequency) annual type got nothing.
    assert await _balance(db_session, hr_setup.tenant_id, terminated.id, monthly.id) is None
    assert await _balance(db_session, hr_setup.tenant_id, active.id, inactive_type.id) is None
    assert await _balance(db_session, hr_setup.tenant_id, active.id, annual_type.id) is None

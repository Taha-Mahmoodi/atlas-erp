"""Leave-request lifecycle (PLAN 10.2, D-053): create → submit → approve (DECREMENTS the balance),
insufficient-balance 422, reject, and cancel-of-approved (RESTORES the balance).

Driven through the real service under the tenant context (D-025). The balance is seeded via the
accrual run, then the request transitions move it.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.hr import queries as hr_queries
from app.modules.hr import service
from app.modules.hr.constants import AccrualFrequency, LeaveRequestStatus
from tests.modules.hr.conftest import HrSetup
from tests.modules.hr.factories import build_employee, build_leave_request, build_leave_type

_APPROVER = uuid.uuid4()


async def _seed_balance(session: AsyncSession, setup: HrSetup, *, amount: Decimal):
    """An employee + a leave type accrued to ``amount`` days, ready to spend."""
    code = f"EMP-{uuid.uuid4().hex[:6]}"
    employee = await build_employee(session, setup.tenant_id, employee_code=code)
    leave_type = await build_leave_type(
        session, setup.tenant_id, code=f"LT-{uuid.uuid4().hex[:6]}", accrual_amount=amount
    )
    with tenant_context(setup.tenant_id):
        await service.accrue_leave(
            session, setup.tenant_id, as_of=date(2026, 6, 1), frequency=AccrualFrequency.MONTHLY
        )
        await session.commit()
    return employee, leave_type


async def _balance(session, setup, employee_id, leave_type_id):
    with tenant_context(setup.tenant_id):
        return await hr_queries.get_leave_balance(
            session, setup.tenant_id, employee_id, leave_type_id
        )


async def test_create_validates_dates_and_days(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee, leave_type = await _seed_balance(db_session, hr_setup, amount=Decimal("10"))
    with tenant_context(hr_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_leave_request(
            db_session,
            hr_setup.tenant_id,
            _payload(employee.id, leave_type.id, start=date(2026, 6, 5), end=date(2026, 6, 1)),
        )
    assert exc.value.code == "hr.leave_dates_invalid"


async def test_submit_then_approve_decrements_balance(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee, leave_type = await _seed_balance(db_session, hr_setup, amount=Decimal("10"))
    request = await build_leave_request(
        db_session,
        hr_setup.tenant_id,
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        days=Decimal("3"),
    )
    assert request.request_number.startswith("LV-")
    with tenant_context(hr_setup.tenant_id):
        await service.submit_leave_request(db_session, hr_setup.tenant_id, request.id)
        approved = await service.approve_leave_request(
            db_session, hr_setup.tenant_id, request.id, approved_by=_APPROVER
        )
        await db_session.commit()
    assert LeaveRequestStatus(approved.status) == LeaveRequestStatus.APPROVED
    assert approved.approved_by == _APPROVER
    assert approved.decided_at is not None
    bal = await _balance(db_session, hr_setup, employee.id, leave_type.id)
    assert bal.balance_days == Decimal("7")  # 10 - 3
    assert bal.taken_to_date == Decimal("3")


async def test_approve_insufficient_balance_422(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee, leave_type = await _seed_balance(db_session, hr_setup, amount=Decimal("2"))
    request = await build_leave_request(
        db_session,
        hr_setup.tenant_id,
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        days=Decimal("5"),  # more than the 2 accrued
    )
    with tenant_context(hr_setup.tenant_id):
        await service.submit_leave_request(db_session, hr_setup.tenant_id, request.id)
        with pytest.raises(ValidationFailedError) as exc:
            await service.approve_leave_request(
                db_session, hr_setup.tenant_id, request.id, approved_by=_APPROVER
            )
    assert exc.value.code == "hr.insufficient_leave_balance"


async def test_reject_has_no_balance_effect(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee, leave_type = await _seed_balance(db_session, hr_setup, amount=Decimal("10"))
    request = await build_leave_request(
        db_session,
        hr_setup.tenant_id,
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        days=Decimal("3"),
    )
    with tenant_context(hr_setup.tenant_id):
        await service.submit_leave_request(db_session, hr_setup.tenant_id, request.id)
        rejected = await service.reject_leave_request(
            db_session, hr_setup.tenant_id, request.id, approved_by=_APPROVER, notes="no"
        )
        await db_session.commit()
    assert LeaveRequestStatus(rejected.status) == LeaveRequestStatus.REJECTED
    bal = await _balance(db_session, hr_setup, employee.id, leave_type.id)
    assert bal.balance_days == Decimal("10")  # untouched


async def test_cancel_approved_restores_balance(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee, leave_type = await _seed_balance(db_session, hr_setup, amount=Decimal("10"))
    request = await build_leave_request(
        db_session,
        hr_setup.tenant_id,
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        days=Decimal("4"),
    )
    with tenant_context(hr_setup.tenant_id):
        await service.submit_leave_request(db_session, hr_setup.tenant_id, request.id)
        await service.approve_leave_request(
            db_session, hr_setup.tenant_id, request.id, approved_by=_APPROVER
        )
        await db_session.commit()
    # Balance is now 6; cancelling the approved request restores it to 10.
    with tenant_context(hr_setup.tenant_id):
        cancelled = await service.cancel_leave_request(db_session, hr_setup.tenant_id, request.id)
        await db_session.commit()
    assert LeaveRequestStatus(cancelled.status) == LeaveRequestStatus.CANCELLED
    bal = await _balance(db_session, hr_setup, employee.id, leave_type.id)
    assert bal.balance_days == Decimal("10")
    assert bal.taken_to_date == Decimal("0")


async def test_approve_requires_submitted(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    """A DRAFT request cannot be approved (the submit gate)."""
    employee, leave_type = await _seed_balance(db_session, hr_setup, amount=Decimal("10"))
    request = await build_leave_request(
        db_session,
        hr_setup.tenant_id,
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        days=Decimal("2"),
    )
    with tenant_context(hr_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.approve_leave_request(
            db_session, hr_setup.tenant_id, request.id, approved_by=_APPROVER
        )
    assert exc.value.code == "hr.leave_request_not_submitted"


def _payload(employee_id, leave_type_id, *, start, end):
    from app.modules.hr.schemas import LeaveRequestCreate

    return LeaveRequestCreate(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        start_date=start,
        end_date=end,
        days=Decimal("1"),
    )

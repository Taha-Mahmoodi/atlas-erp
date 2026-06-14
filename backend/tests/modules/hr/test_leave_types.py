"""Leave-type service behaviour (PLAN 10.2, D-053): CRUD + validation (code uniqueness, accrual
amount >= 0, max_balance >= accrual_amount).

Driven through the real service under the tenant context (D-025).
"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.hr import service
from app.modules.hr.constants import AccrualFrequency
from app.modules.hr.schemas import LeaveTypeCreate, LeaveTypeFilter, LeaveTypeUpdate
from tests.modules.hr.conftest import HrSetup
from tests.modules.hr.factories import build_leave_type


async def test_create_and_get_leave_type(db_session: AsyncSession, hr_setup: HrSetup) -> None:
    leave_type = await build_leave_type(
        db_session, hr_setup.tenant_id, code="LT-SICK", name="Sick leave"
    )
    with tenant_context(hr_setup.tenant_id):
        got = await service.get_leave_type(db_session, hr_setup.tenant_id, leave_type.id)
    assert got.code == "LT-SICK"
    assert got.accrual_frequency == AccrualFrequency.MONTHLY.value
    assert got.is_active is True


async def test_duplicate_code_conflicts(db_session: AsyncSession, hr_setup: HrSetup) -> None:
    await build_leave_type(db_session, hr_setup.tenant_id, code="LT-DUP")
    with tenant_context(hr_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.create_leave_type(
            db_session,
            hr_setup.tenant_id,
            LeaveTypeCreate(code="LT-DUP", name="Other", accrual_amount=Decimal("1")),
        )
    assert exc.value.code == "hr.leave_type_code_conflict"


async def test_negative_accrual_rejected(db_session: AsyncSession, hr_setup: HrSetup) -> None:
    with tenant_context(hr_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_leave_type(
            db_session,
            hr_setup.tenant_id,
            LeaveTypeCreate(code="LT-NEG", name="Bad", accrual_amount=Decimal("-1")),
        )
    assert exc.value.code == "hr.leave_accrual_invalid"


async def test_max_balance_below_accrual_rejected(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    with tenant_context(hr_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_leave_type(
            db_session,
            hr_setup.tenant_id,
            LeaveTypeCreate(
                code="LT-CAP",
                name="Bad cap",
                accrual_amount=Decimal("5"),
                max_balance=Decimal("3"),
            ),
        )
    assert exc.value.code == "hr.leave_max_balance_invalid"


async def test_update_revalidates_accrual(db_session: AsyncSession, hr_setup: HrSetup) -> None:
    leave_type = await build_leave_type(
        db_session,
        hr_setup.tenant_id,
        code="LT-UPD",
        accrual_amount=Decimal("2"),
        max_balance=Decimal("20"),
    )
    with tenant_context(hr_setup.tenant_id):
        updated = await service.update_leave_type(
            db_session,
            hr_setup.tenant_id,
            leave_type.id,
            LeaveTypeUpdate(name="Renamed", accrual_amount=Decimal("3")),
        )
    assert updated.name == "Renamed"
    assert updated.accrual_amount == Decimal("3")

    # An update that pushes the cap below the (resulting) accrual amount is rejected.
    with tenant_context(hr_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.update_leave_type(
            db_session,
            hr_setup.tenant_id,
            leave_type.id,
            LeaveTypeUpdate(max_balance=Decimal("1")),
        )
    assert exc.value.code == "hr.leave_max_balance_invalid"


async def test_list_filters_by_active_and_frequency(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    await build_leave_type(
        db_session, hr_setup.tenant_id, code="LT-M", accrual_frequency=AccrualFrequency.MONTHLY
    )
    await build_leave_type(
        db_session, hr_setup.tenant_id, code="LT-A", accrual_frequency=AccrualFrequency.ANNUAL
    )
    await build_leave_type(
        db_session, hr_setup.tenant_id, code="LT-OFF", is_active=False
    )
    with tenant_context(hr_setup.tenant_id):
        annual = await service.list_leave_types(
            db_session,
            hr_setup.tenant_id,
            filters=LeaveTypeFilter(accrual_frequency=AccrualFrequency.ANNUAL),
        )
        active = await service.list_leave_types(
            db_session, hr_setup.tenant_id, filters=LeaveTypeFilter(is_active=True)
        )
    assert {lt.code for lt in annual.items} == {"LT-A"}
    assert "LT-OFF" not in {lt.code for lt in active.items}

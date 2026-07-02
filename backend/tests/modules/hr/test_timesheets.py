"""Timesheet lifecycle + time-entry rules (PLAN 10.3, D-054): create, add/update/remove entries
(DRAFT only), the maintained ``total_hours``, entry-date-in-period + hours > 0 + cost-centre
existence validations, the project_id-stored-opaque behaviour, and the submit → approve / reject /
cancel lifecycle.

Driven through the real service under the tenant context (D-025).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.hr import queries as hr_queries
from app.modules.hr import service
from app.modules.hr.constants import TimesheetStatus
from app.modules.hr.time_schemas import (
    TimeEntryCreate,
    TimeEntryUpdate,
    TimesheetCreate,
    TimesheetUpdate,
)
from tests.modules.hr.conftest import HrSetup
from tests.modules.hr.factories import build_employee, build_time_entry, build_timesheet

_APPROVER = uuid.uuid4()


async def _employee(session: AsyncSession, setup: HrSetup):
    return await build_employee(
        session, setup.tenant_id, employee_code=f"EMP-{uuid.uuid4().hex[:6]}"
    )


async def test_create_claims_number_and_starts_draft(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    assert timesheet.timesheet_number.startswith("TS-")
    assert TimesheetStatus(timesheet.status) == TimesheetStatus.DRAFT
    assert timesheet.total_hours == Decimal("0")


async def test_create_rejects_invalid_period(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    with tenant_context(hr_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_timesheet(
            db_session,
            hr_setup.tenant_id,
            TimesheetCreate(
                employee_id=employee.id,
                period_start=date(2026, 6, 30),
                period_end=date(2026, 6, 1),
            ),
        )
    assert exc.value.code == "hr.timesheet_period_invalid"


async def test_create_rejects_duplicate_period(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    with tenant_context(hr_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.create_timesheet(
            db_session,
            hr_setup.tenant_id,
            TimesheetCreate(
                employee_id=employee.id,
                period_start=date(2026, 6, 1),
                period_end=date(2026, 6, 30),
            ),
        )
    assert exc.value.code == "hr.timesheet_period_conflict"


async def test_add_entry_maintains_total_hours(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    await build_time_entry(
        db_session, hr_setup.tenant_id, timesheet_id=timesheet.id, hours=Decimal("8")
    )
    await build_time_entry(
        db_session,
        hr_setup.tenant_id,
        timesheet_id=timesheet.id,
        entry_date=date(2026, 6, 3),
        hours=Decimal("4.5"),
    )
    with tenant_context(hr_setup.tenant_id):
        refreshed = await hr_queries.get_timesheet(db_session, hr_setup.tenant_id, timesheet.id)
    assert refreshed.total_hours == Decimal("12.5")


async def test_update_entry_adjusts_total_hours(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    entry = await build_time_entry(
        db_session, hr_setup.tenant_id, timesheet_id=timesheet.id, hours=Decimal("8")
    )
    with tenant_context(hr_setup.tenant_id):
        await service.update_time_entry(
            db_session,
            hr_setup.tenant_id,
            timesheet.id,
            entry.id,
            TimeEntryUpdate(hours=Decimal("5")),
        )
        await db_session.commit()
        refreshed = await hr_queries.get_timesheet(db_session, hr_setup.tenant_id, timesheet.id)
    assert refreshed.total_hours == Decimal("5")


async def test_remove_entry_lowers_total_hours(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    entry = await build_time_entry(
        db_session, hr_setup.tenant_id, timesheet_id=timesheet.id, hours=Decimal("8")
    )
    with tenant_context(hr_setup.tenant_id):
        await service.remove_time_entry(db_session, hr_setup.tenant_id, timesheet.id, entry.id)
        await db_session.commit()
        refreshed = await hr_queries.get_timesheet(db_session, hr_setup.tenant_id, timesheet.id)
    assert refreshed.total_hours == Decimal("0")


async def test_entry_date_must_be_in_period(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(
        db_session,
        hr_setup.tenant_id,
        employee_id=employee.id,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 7),
    )
    with tenant_context(hr_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.add_time_entry(
            db_session,
            hr_setup.tenant_id,
            timesheet.id,
            TimeEntryCreate(entry_date=date(2026, 6, 10), hours=Decimal("8")),
        )
    assert exc.value.code == "hr.time_entry_date_out_of_period"


async def test_entry_hours_must_be_positive(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    with tenant_context(hr_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.add_time_entry(
            db_session,
            hr_setup.tenant_id,
            timesheet.id,
            TimeEntryCreate(entry_date=date(2026, 6, 2), hours=Decimal("0")),
        )
    assert exc.value.code == "hr.time_entry_hours_invalid"


async def test_entry_cost_center_must_exist(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    with tenant_context(hr_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.add_time_entry(
            db_session,
            hr_setup.tenant_id,
            timesheet.id,
            TimeEntryCreate(
                entry_date=date(2026, 6, 2), hours=Decimal("8"), cost_center_id=uuid.uuid4()
            ),
        )
    assert exc.value.code == "hr.cost_center_not_found"


async def test_entry_valid_cost_center_accepted(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    entry = await build_time_entry(
        db_session,
        hr_setup.tenant_id,
        timesheet_id=timesheet.id,
        cost_center_id=hr_setup.cost_center_id,
    )
    assert entry.cost_center_id == hr_setup.cost_center_id


async def test_project_id_stored_opaque_unvalidated(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    """project_id is a free OPAQUE reference in v1 (projects is Phase 11): a random id is accepted
    and stored as-is, NOT validated against any table (D-054)."""
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    project_id = uuid.uuid4()
    entry = await build_time_entry(
        db_session, hr_setup.tenant_id, timesheet_id=timesheet.id, project_id=project_id
    )
    assert entry.project_id == project_id


async def test_submit_then_approve_lifecycle(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    await build_time_entry(db_session, hr_setup.tenant_id, timesheet_id=timesheet.id)
    with tenant_context(hr_setup.tenant_id):
        await service.submit_timesheet(db_session, hr_setup.tenant_id, timesheet.id)
        approved = await service.approve_timesheet(
            db_session, hr_setup.tenant_id, timesheet.id, approved_by=_APPROVER
        )
        await db_session.commit()
    assert TimesheetStatus(approved.status) == TimesheetStatus.APPROVED
    assert approved.approved_by == _APPROVER
    assert approved.approved_at is not None
    assert approved.submitted_at is not None


async def test_reject_lifecycle(db_session: AsyncSession, hr_setup: HrSetup) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    with tenant_context(hr_setup.tenant_id):
        await service.submit_timesheet(db_session, hr_setup.tenant_id, timesheet.id)
        rejected = await service.reject_timesheet(
            db_session, hr_setup.tenant_id, timesheet.id, approved_by=_APPROVER, notes="redo"
        )
        await db_session.commit()
    assert TimesheetStatus(rejected.status) == TimesheetStatus.REJECTED
    assert rejected.notes == "redo"


async def test_cancel_reopens_submitted_to_draft(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    with tenant_context(hr_setup.tenant_id):
        await service.submit_timesheet(db_session, hr_setup.tenant_id, timesheet.id)
        reopened = await service.cancel_timesheet(db_session, hr_setup.tenant_id, timesheet.id)
        await db_session.commit()
    assert TimesheetStatus(reopened.status) == TimesheetStatus.DRAFT
    assert reopened.submitted_at is None


async def test_cannot_add_entry_to_submitted(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    with tenant_context(hr_setup.tenant_id):
        await service.submit_timesheet(db_session, hr_setup.tenant_id, timesheet.id)
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.add_time_entry(
                db_session,
                hr_setup.tenant_id,
                timesheet.id,
                TimeEntryCreate(entry_date=date(2026, 6, 2), hours=Decimal("8")),
            )
    assert exc.value.code == "hr.timesheet_not_draft"


async def test_approve_requires_submitted(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    """A DRAFT timesheet cannot be approved (only a SUBMITTED one)."""
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(db_session, hr_setup.tenant_id, employee_id=employee.id)
    with tenant_context(hr_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.approve_timesheet(
            db_session, hr_setup.tenant_id, timesheet.id, approved_by=_APPROVER
        )
    assert exc.value.code == "hr.timesheet_not_submitted"


async def test_narrowing_period_orphaning_entry_rejected(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    employee = await _employee(db_session, hr_setup)
    timesheet = await build_timesheet(
        db_session,
        hr_setup.tenant_id,
        employee_id=employee.id,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
    )
    await build_time_entry(
        db_session, hr_setup.tenant_id, timesheet_id=timesheet.id, entry_date=date(2026, 6, 20)
    )
    with tenant_context(hr_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.update_timesheet(
            db_session,
            hr_setup.tenant_id,
            timesheet.id,
            TimesheetUpdate(period_end=date(2026, 6, 10)),
        )
    assert exc.value.code == "hr.time_entry_date_out_of_period"


async def test_get_unknown_timesheet_404(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    with tenant_context(hr_setup.tenant_id), pytest.raises(NotFoundError) as exc:
        await service.get_timesheet(db_session, hr_setup.tenant_id, uuid.uuid4())
    assert exc.value.code == "hr.timesheet_not_found"

"""Fiscal year/period rules (D-018): period generation, lookup, and close lifecycle."""

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import PeriodStatus
from app.modules.finance.queries import find_period_for_date
from app.modules.finance.schemas import FiscalYearCreate


def test_generate_periods_are_contiguous_and_non_overlapping() -> None:
    boundaries = service.generate_periods(date(2026, 1, 1), 12)
    assert len(boundaries) == 12
    # First period starts on the year start; last ends the day before next year.
    assert boundaries[0][1] == date(2026, 1, 1)
    assert boundaries[0][2] == date(2026, 1, 31)
    assert boundaries[-1][2] == date(2026, 12, 31)
    # No gaps, no overlaps: each period starts exactly one day after the previous ends.
    for prev, nxt in zip(boundaries, boundaries[1:], strict=False):
        assert (nxt[1] - prev[2]).days == 1


def test_generate_periods_handles_short_months() -> None:
    # A February-anchored year clamps month ends correctly (no Feb 30).
    boundaries = service.generate_periods(date(2026, 1, 31), 2)
    assert boundaries[0] == (1, date(2026, 1, 31), date(2026, 2, 27))
    assert boundaries[1][1] == date(2026, 2, 28)


async def test_create_fiscal_year_creates_twelve_periods(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        year = await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        periods = await service.list_fiscal_periods(db_session, tenant_a, year.id)
    assert len(periods) == 12
    assert year.end_date == date(2026, 12, 31)
    assert [p.period_number for p in periods] == list(range(1, 13))
    assert all(p.status == PeriodStatus.OPEN.value for p in periods)
    assert periods[0].name == "2026-01"


async def test_duplicate_fiscal_year_code_raises_conflict(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        with pytest.raises(ConflictError):
            await service.create_fiscal_year(
                db_session,
                tenant_a,
                FiscalYearCreate(code="2026", name="dup", start_date=date(2027, 1, 1)),
            )


async def test_find_period_for_date_returns_covering_period(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        march = await find_period_for_date(db_session, tenant_a, date(2026, 3, 15))
    assert march is not None
    assert march.period_number == 3
    assert march.start_date == date(2026, 3, 1)


async def test_find_period_for_date_outside_any_period_is_none(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        result = await find_period_for_date(db_session, tenant_a, date(2030, 6, 1))
    assert result is None


async def test_close_then_open_period(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        year = await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        periods = await service.list_fiscal_periods(db_session, tenant_a, year.id)
        first = periods[0]

        closed = await service.close_period(db_session, tenant_a, first.id)
        assert closed.status == PeriodStatus.CLOSED.value

        reopened = await service.open_period(db_session, tenant_a, first.id)
        assert reopened.status == PeriodStatus.OPEN.value


async def test_close_already_closed_period_raises(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        year = await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        period = (await service.list_fiscal_periods(db_session, tenant_a, year.id))[0]
        await service.close_period(db_session, tenant_a, period.id)
        with pytest.raises(ValidationFailedError) as excinfo:
            await service.close_period(db_session, tenant_a, period.id)
    assert excinfo.value.code == "finance.period_already_closed"


async def test_close_fiscal_year_blocked_while_a_period_is_open(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        year = await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        # Close every period but one, then closing the year must still fail.
        periods = await service.list_fiscal_periods(db_session, tenant_a, year.id)
        for period in periods[:-1]:
            await service.close_period(db_session, tenant_a, period.id)
        with pytest.raises(ValidationFailedError) as excinfo:
            await service.close_fiscal_year(db_session, tenant_a, year.id)
    assert excinfo.value.code == "finance.fiscal_year_has_open_periods"


async def test_close_fiscal_year_succeeds_when_all_periods_closed(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        year = await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        for period in await service.list_fiscal_periods(db_session, tenant_a, year.id):
            await service.close_period(db_session, tenant_a, period.id)
        closed_year = await service.close_fiscal_year(db_session, tenant_a, year.id)
    assert closed_year.status == PeriodStatus.CLOSED.value


async def test_reopen_period_blocked_when_year_closed(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        year = await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        periods = await service.list_fiscal_periods(db_session, tenant_a, year.id)
        for period in periods:
            await service.close_period(db_session, tenant_a, period.id)
        await service.close_fiscal_year(db_session, tenant_a, year.id)
        with pytest.raises(ValidationFailedError) as excinfo:
            await service.open_period(db_session, tenant_a, periods[0].id)
    assert excinfo.value.code == "finance.fiscal_year_closed"

"""The finance cross-module read interface (STRUCTURE §5): get_period_status,
find_period_for_date, account_exists return correct, tenant-scoped results."""

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import AccountType, PeriodStatus
from app.modules.finance.queries import account_exists, get_period_status
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate


async def test_get_period_status_reflects_open_and_closed(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        year = await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        in_jan = date(2026, 1, 10)
        assert await get_period_status(db_session, tenant_a, in_jan) == PeriodStatus.OPEN

        january = (
            await service.list_fiscal_periods(db_session, tenant_a, year.id)
        ).items[0]
        await service.close_period(db_session, tenant_a, january.id)
        await db_session.commit()
        assert await get_period_status(db_session, tenant_a, in_jan) == PeriodStatus.CLOSED


async def test_get_period_status_none_outside_any_period(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
        assert await get_period_status(db_session, tenant_a, date(2099, 1, 1)) is None


async def test_account_exists(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a):
        await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="1000", name="Cash", account_type=AccountType.ASSET),
        )
        await db_session.commit()
        assert await account_exists(db_session, tenant_a, "1000") is True
        assert await account_exists(db_session, tenant_a, "9999") is False

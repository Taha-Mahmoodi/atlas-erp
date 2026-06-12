"""Tenant isolation (D-007) for the new finance TenantMixin models: tenant A's accounts and
periods are invisible to tenant B. The mapper-enumerating suite in tests/core/test_tenancy.py
auto-covers these models for the generic guarantees; this is the finance-specific spot check."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import AccountType
from app.modules.finance.models import Account, FiscalPeriod
from app.modules.finance.queries import account_exists, find_period_for_date
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate


async def test_accounts_are_invisible_across_tenants(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="1000", name="Cash", account_type=AccountType.ASSET),
        )
        await db_session.commit()

    # Under tenant B's context, a bare select sees none of tenant A's accounts.
    with tenant_context(tenant_b):
        rows = (await db_session.execute(select(Account))).scalars().all()
        assert rows == []
        assert await account_exists(db_session, tenant_b, "1000") is False


async def test_periods_are_invisible_across_tenants(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()

    with tenant_context(tenant_b):
        rows = (await db_session.execute(select(FiscalPeriod))).scalars().all()
        assert rows == []
        # The cross-module query is tenant-scoped: B finds no period for a date inside A's year.
        assert await find_period_for_date(db_session, tenant_b, date(2026, 3, 15)) is None

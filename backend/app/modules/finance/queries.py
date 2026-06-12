"""Finance's cross-module read interface (STRUCTURE §5).

Finance is the bottom of the dependency order: every other module (inventory, sales, ...)
may import THIS file to read finance state synchronously, and finance imports no other
module's queries. Keep this surface thin and stable — it is a contract. The journal posting
flow (4.2) calls ``find_period_for_date`` to resolve an entry's period from its posting_date;
inventory/sales call ``get_period_status`` to refuse stock/sales documents dated into a closed
period before they reach the GL.

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so
the D-007 filter applies on top of the explicit predicate — these are ordinary tenant-scoped
ORM reads, not a bypass.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import PeriodStatus, RateKind
from app.modules.finance.models import Account, FiscalPeriod
from app.modules.finance.service import fx as _fx


async def find_period_for_date(
    session: AsyncSession, tenant_id: uuid.UUID, on_date: date
) -> FiscalPeriod | None:
    """The fiscal period whose [start_date, end_date] (inclusive) covers ``on_date``, or
    None if no period does. Periods within a year are contiguous and non-overlapping (the
    service enforces that on generation), so at most one matches. This is the date->period
    lookup the journal uses on every posting (4.2)."""
    stmt = select(FiscalPeriod).where(
        FiscalPeriod.tenant_id == tenant_id,
        FiscalPeriod.start_date <= on_date,
        FiscalPeriod.end_date >= on_date,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_period_status(
    session: AsyncSession, tenant_id: uuid.UUID, on_date: date
) -> PeriodStatus | None:
    """The OPEN/CLOSED status of the period covering ``on_date``, or None when no period
    covers it. Callers posting financial or stock documents check this up front: None or
    CLOSED means the date is not in an open period and the document must be rejected
    (the DB-level period trigger on the journal in 4.2 is the bypass-proof backstop)."""
    period = await find_period_for_date(session, tenant_id, on_date)
    if period is None:
        return None
    return PeriodStatus(period.status)


async def account_exists(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> bool:
    """Whether an account with ``code`` exists in the tenant's chart of accounts. Lets
    another module validate a referenced account code without importing finance models."""
    stmt = select(Account.id).where(
        Account.tenant_id == tenant_id, Account.code == code
    )
    return (await session.execute(stmt)).first() is not None


async def get_rate(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    from_code: str,
    to_code: str,
    on_date: date,
    rate_type: RateKind = RateKind.SPOT,
) -> Decimal:
    """The exchange rate to convert ``from_code`` into ``to_code`` on ``on_date`` (D-019). Exposed
    here so other modules price in functional terms (AP/AR/inventory translate at this rate); a
    missing rate raises (postings never guess). Same contract as service/fx.get_rate."""
    return await _fx.get_rate(session, tenant_id, from_code, to_code, on_date, rate_type)


async def functional_currency(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    """The tenant's functional (reporting) currency code (D-019). Exposed so other modules know the
    currency every functional amount is denominated in. Raises if none is configured."""
    return await _fx.functional_currency(session, tenant_id)

"""Fiscal-period lookups (part of finance's cross-module read contract, STRUCTURE §5).

Split out of ``queries/__init__.py`` at the 400-line cap (STRUCTURE §8.4) and re-exported from the
package ``__init__`` so every ``from app.modules.finance.queries import X`` import keeps working
from one surface. The journal posting flow (4.2) calls ``find_period_for_date`` to resolve an
entry's period from its posting_date; inventory/sales call ``get_period_status`` to refuse
stock/sales documents dated into a closed period before they reach the GL.

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import PeriodStatus
from app.modules.finance.models import FiscalPeriod


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

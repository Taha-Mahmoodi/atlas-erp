"""Return read paths (PLAN 7.4), split from the write engine (returns.py) at the 400-line cap
(STRUCTURE §8.4, the delivery_reads.py precedent). The service package + router import these via the
package surface.

Keyset-paginated list (filter by order / status / return-date range) + header/line point reads + the
per-order return history. The list folds its filters into the cursor fingerprint so a cursor cannot
cross filtered views (D-014).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.sales.constants import ReturnStatus
from app.modules.sales.models import SalesReturn, SalesReturnLine


async def get_return(
    session: AsyncSession, tenant_id: uuid.UUID, return_id: uuid.UUID
) -> SalesReturn:
    sales_return = await session.get(SalesReturn, return_id)
    if sales_return is None or sales_return.tenant_id != tenant_id:
        raise NotFoundError(message="Return not found", code="sales.return_not_found")
    return sales_return


async def get_return_lines(
    session: AsyncSession, tenant_id: uuid.UUID, return_id: uuid.UUID
) -> list[SalesReturnLine]:
    stmt = (
        select(SalesReturnLine)
        .where(SalesReturnLine.tenant_id == tenant_id, SalesReturnLine.return_id == return_id)
        .order_by(SalesReturnLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_returns(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    sales_order_id: uuid.UUID | None = None,
    status: ReturnStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[SalesReturn]:
    """Keyset-paginated return list, newest first (D-014). Filters fold into the cursor fingerprint;
    the (tenant, status) / (tenant, sales_order_id) indexes serve it (PERFORMANCE §1)."""
    stmt = select(SalesReturn).where(SalesReturn.tenant_id == tenant_id)
    if sales_order_id is not None:
        stmt = stmt.where(SalesReturn.sales_order_id == sales_order_id)
    if status is not None:
        stmt = stmt.where(SalesReturn.status == ReturnStatus(status).value)
    if date_from is not None:
        stmt = stmt.where(SalesReturn.return_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(SalesReturn.return_date <= date_to)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(SalesReturn.created_at, SortDirection.DESC)],
        pk=SalesReturn.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(sales_order_id, status, date_from, date_to),
    )


async def returns_for_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> list[SalesReturn]:
    """Every return raised against a sales order (PLAN 7.4), newest first — the per-order RMA
    history.
    Index-served by (tenant, sales_order_id)."""
    stmt = (
        select(SalesReturn)
        .where(SalesReturn.tenant_id == tenant_id, SalesReturn.sales_order_id == order_id)
        .order_by(SalesReturn.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())

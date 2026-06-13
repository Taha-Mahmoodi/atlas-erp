"""Billing read paths (PLAN 7.4), split from the write engine (billing.py) at the 400-line cap
(STRUCTURE §8.4, the delivery_reads.py precedent). The service package + router import these via the
package surface.

Keyset-paginated list (filter by order / status / billing-date range) + header/line point reads +
the per-order billing history. The list folds its filters into the cursor fingerprint so a cursor
cannot cross filtered views (D-014).
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
from app.modules.sales.constants import BillingStatus
from app.modules.sales.models import SalesBilling, SalesBillingLine


async def get_billing(
    session: AsyncSession, tenant_id: uuid.UUID, billing_id: uuid.UUID
) -> SalesBilling:
    billing = await session.get(SalesBilling, billing_id)
    if billing is None or billing.tenant_id != tenant_id:
        raise NotFoundError(message="Billing not found", code="sales.billing_not_found")
    return billing


async def get_billing_lines(
    session: AsyncSession, tenant_id: uuid.UUID, billing_id: uuid.UUID
) -> list[SalesBillingLine]:
    stmt = (
        select(SalesBillingLine)
        .where(SalesBillingLine.tenant_id == tenant_id, SalesBillingLine.billing_id == billing_id)
        .order_by(SalesBillingLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_billings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    sales_order_id: uuid.UUID | None = None,
    status: BillingStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[SalesBilling]:
    """Keyset-paginated billing list, newest first (D-014). Filters fold into the cursor
    fingerprint; the (tenant, status) / (tenant, sales_order_id) indexes serve it (PERFORMANCE
    §1)."""
    stmt = select(SalesBilling).where(SalesBilling.tenant_id == tenant_id)
    if sales_order_id is not None:
        stmt = stmt.where(SalesBilling.sales_order_id == sales_order_id)
    if status is not None:
        stmt = stmt.where(SalesBilling.status == BillingStatus(status).value)
    if date_from is not None:
        stmt = stmt.where(SalesBilling.billing_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(SalesBilling.billing_date <= date_to)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(SalesBilling.created_at, SortDirection.DESC)],
        pk=SalesBilling.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(sales_order_id, status, date_from, date_to),
    )


async def billings_for_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> list[SalesBilling]:
    """Every billing raised against a sales order (PLAN 7.4), newest first — the per-order billing
    history. Index-served by (tenant, sales_order_id)."""
    stmt = (
        select(SalesBilling)
        .where(SalesBilling.tenant_id == tenant_id, SalesBilling.sales_order_id == order_id)
        .order_by(SalesBilling.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())

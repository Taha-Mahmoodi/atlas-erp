"""Delivery read paths (PLAN 7.3), split from the write engine (deliveries.py) at the 400-line cap
(STRUCTURE §8.4). The service package and router import these via the package surface.

Keyset-paginated list (filter by order / status / delivery-date range) + header/line point reads.
The list folds its filters into the cursor fingerprint so a cursor cannot cross filtered views
(D-014). Mirrors goods_receipt_reads.py (the outbound twin).
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
from app.modules.sales.constants import DeliveryStatus
from app.modules.sales.models import Delivery, DeliveryLine


async def get_delivery(
    session: AsyncSession, tenant_id: uuid.UUID, delivery_id: uuid.UUID
) -> Delivery:
    delivery = await session.get(Delivery, delivery_id)
    if delivery is None or delivery.tenant_id != tenant_id:
        raise NotFoundError(message="Delivery not found", code="sales.delivery_not_found")
    return delivery


async def get_delivery_lines(
    session: AsyncSession, tenant_id: uuid.UUID, delivery_id: uuid.UUID
) -> list[DeliveryLine]:
    stmt = (
        select(DeliveryLine)
        .where(DeliveryLine.tenant_id == tenant_id, DeliveryLine.delivery_id == delivery_id)
        .order_by(DeliveryLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_deliveries(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    sales_order_id: uuid.UUID | None = None,
    status: DeliveryStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Delivery]:
    """Keyset-paginated delivery list, newest first (D-014). The order / status / date filters fold
    into the cursor fingerprint; the (tenant, status) and (tenant, sales_order_id) indexes serve the
    filtered page (PERFORMANCE §1)."""
    stmt = select(Delivery).where(Delivery.tenant_id == tenant_id)
    if sales_order_id is not None:
        stmt = stmt.where(Delivery.sales_order_id == sales_order_id)
    if status is not None:
        stmt = stmt.where(Delivery.status == DeliveryStatus(status).value)
    if date_from is not None:
        stmt = stmt.where(Delivery.delivery_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Delivery.delivery_date <= date_to)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Delivery.created_at, SortDirection.DESC)],
        pk=Delivery.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(sales_order_id, status, date_from, date_to),
    )


async def deliveries_for_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> list[Delivery]:
    """Every delivery raised against a sales order (PLAN 7.3), newest first — the per-order delivery
    history the order detail / the 7.4 invoice read. Index-served by (tenant, sales_order_id)."""
    stmt = (
        select(Delivery)
        .where(Delivery.tenant_id == tenant_id, Delivery.sales_order_id == order_id)
        .order_by(Delivery.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())

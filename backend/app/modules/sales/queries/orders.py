"""Sales-order header + line reads (part of sales' cross-module read contract).

Split out of ``sales/queries.py`` at the 400-line cap (STRUCTURE §8.4) and re-exported from the
package ``__init__`` so other modules still import the whole surface from
``app.modules.sales.queries``.
These functions read the ``SalesOrder`` header + ``SalesOrderLine`` rows: the point/list reads 7.3
deliveries + 7.4 billing build on, and the per-line open-quantity helpers (ordered/delivered/
invoiced minus the next stage) those flows cap each stage at.

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales.models import SalesOrder, SalesOrderLine


async def get_sales_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> SalesOrder | None:
    """The sales order with ``order_id`` in the tenant, or None. Lets 7.3 (deliveries) and 7.4
    (billing) read an order header — customer, currency, status, totals — without importing sales
    service internals. A point lookup on the PK."""
    stmt = select(SalesOrder).where(
        SalesOrder.tenant_id == tenant_id, SalesOrder.id == order_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _order_line(
    session: AsyncSession, tenant_id: uuid.UUID, order_line_id: uuid.UUID
) -> SalesOrderLine | None:
    """One order line by id in the tenant, or None — the shared point read the three open-quantity
    helpers below subtract maintained columns over (PLAN 7.2–7.4)."""
    return (
        await session.execute(
            select(SalesOrderLine).where(
                SalesOrderLine.tenant_id == tenant_id,
                SalesOrderLine.id == order_line_id,
            )
        )
    ).scalar_one_or_none()


async def so_line_open_to_deliver(
    session: AsyncSession, tenant_id: uuid.UUID, order_line_id: uuid.UUID
) -> Decimal | None:
    """The still-open-to-deliver quantity on an order line — ORDERED minus DELIVERED — or None if
    the line does not exist (PLAN 7.2 → 7.3). A delivery (7.3) caps a pick at this. A point lookup
    on the maintained ``delivered_quantity`` (raised by 7.3), not a SUM over deliveries."""
    line = await _order_line(session, tenant_id, order_line_id)
    if line is None:
        return None
    return Decimal(str(line.ordered_quantity)) - Decimal(str(line.delivered_quantity))


async def get_order_for_delivery(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> tuple[SalesOrder, list[SalesOrderLine]] | None:
    """The order header + its lines (item, ordered/delivered quantities, unit price, tax code) — the
    data a delivery (7.3) builds pick lines from and billing (7.4) invoices. None when the order is
    unknown. Two indexed reads (header by PK, lines by (tenant, order_id)); no N+1."""
    order = await get_sales_order(session, tenant_id, order_id)
    if order is None:
        return None
    lines = list(
        (
            await session.execute(
                select(SalesOrderLine)
                .where(
                    SalesOrderLine.tenant_id == tenant_id,
                    SalesOrderLine.order_id == order_id,
                )
                .order_by(SalesOrderLine.line_number)
            )
        )
        .scalars()
        .all()
    )
    return order, lines


async def so_line_open_to_invoice(
    session: AsyncSession, tenant_id: uuid.UUID, order_line_id: uuid.UUID
) -> Decimal | None:
    """The still-open-to-invoice quantity on an order line — DELIVERED minus INVOICED — or None if
    the line does not exist (PLAN 7.3 → 7.4). 7.4 bills against DELIVERED-but-not-yet-INVOICED
    quantity (you invoice what shipped, not what was ordered), so this caps an invoice line at
    delivered − invoiced, NOT ordered − invoiced. A point lookup on the maintained columns."""
    line = await _order_line(session, tenant_id, order_line_id)
    if line is None:
        return None
    return Decimal(str(line.delivered_quantity)) - Decimal(str(line.invoiced_quantity))


async def so_line_open_to_return(
    session: AsyncSession, tenant_id: uuid.UUID, order_line_id: uuid.UUID
) -> Decimal | None:
    """The still-open-to-return quantity on an order line: INVOICED minus RETURNED, or None if the
    line is unknown (PLAN 7.4). A return caps a line at invoiced-not-yet-returned: a credit note
    reduces a real invoice, so the cap is invoiced, not delivered (D-046). Maintained columns."""
    line = await _order_line(session, tenant_id, order_line_id)
    if line is None:
        return None
    return Decimal(str(line.invoiced_quantity)) - Decimal(str(line.returned_quantity))


async def get_order_for_invoice(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> tuple[SalesOrder, list[SalesOrderLine]] | None:
    """The order header + lines for BILLING / RETURNS (PLAN 7.4): the ``get_order_for_delivery``
    two-read shape named for the billing intent; no N+1. None when the order is unknown."""
    return await get_order_for_delivery(session, tenant_id, order_id)

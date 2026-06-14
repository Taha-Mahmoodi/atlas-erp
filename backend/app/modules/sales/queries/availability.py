"""ATP (available-to-promise) + credit-exposure reads (part of sales' cross-module read contract).

Split out of ``sales/queries.py`` at the 400-line cap (STRUCTURE §8.4) and re-exported from the
package ``__init__`` so other modules still import the whole surface from
``app.modules.sales.queries``.
These functions answer the confirm-gate questions: the COMMITTED quantity + the ATP availability
check (the sanctioned DOWNWARD reads of inventory on-hand + procurement on-order), and the
credit-exposure pair (open confirmed order value + the customer's open AR, the latter a thin alias
over finance's ``customer_open_balance``).

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.procurement import queries as procurement_queries
from app.modules.sales.constants import SalesOrderStatus
from app.modules.sales.models import SalesOrder, SalesOrderLine


async def committed_quantity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    exclude_order_id: uuid.UUID | None = None,
) -> Decimal:
    """The quantity of an item COMMITTED by confirmed-but-undelivered sales orders (PLAN 7.2, D-044)
    — the reservation an ATP scan subtracts from on-hand. Sums ``ordered − delivered`` over order
    lines for ``item_id`` on CONFIRMED / PARTIALLY_DELIVERED orders (a CONFIRMED order has reserved
    its undelivered quantity; a DRAFT / CREDIT_BLOCKED / CANCELLED / fully-DELIVERED / INVOICED /
    CLOSED order commits nothing). ``exclude_order_id`` drops one order from the sum — used when
    confirming so an order's own demand is checked against availability NET of other commitments.
    SET-BASED (no per-order N+1, PERFORMANCE §2): one filtered join, summed in PYTHON over the small
    open set so the exact-decimal QuantityType round-trips identically on both engines (D-015)."""
    stmt = (
        select(SalesOrderLine.ordered_quantity, SalesOrderLine.delivered_quantity)
        .join(
            SalesOrder,
            (SalesOrderLine.tenant_id == SalesOrder.tenant_id)
            & (SalesOrderLine.order_id == SalesOrder.id),
        )
        .where(
            SalesOrderLine.tenant_id == tenant_id,
            SalesOrderLine.item_id == item_id,
            SalesOrder.status.in_(
                [
                    SalesOrderStatus.CONFIRMED.value,
                    SalesOrderStatus.PARTIALLY_DELIVERED.value,
                ]
            ),
            SalesOrderLine.delivered_quantity < SalesOrderLine.ordered_quantity,
        )
    )
    if exclude_order_id is not None:
        stmt = stmt.where(SalesOrder.id != exclude_order_id)
    rows = (await session.execute(stmt)).all()
    return sum(
        (Decimal(str(ordered)) - Decimal(str(delivered)) for ordered, delivered in rows),
        Decimal(0),
    )


async def open_demand_item_ids(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[uuid.UUID]:
    """The distinct items carrying OPEN sales-order demand (PLAN 8.3) — items on undelivered lines
    of CONFIRMED / PARTIALLY_DELIVERED orders. MRP reads this (downward, the sanctioned cross-module
    read) to discover which items have independent sales demand, then sums each via
    ``committed_quantity``. ONE set-based DISTINCT query (no N+1); ordered for a deterministic
    plan."""
    stmt = (
        select(SalesOrderLine.item_id)
        .join(
            SalesOrder,
            (SalesOrderLine.tenant_id == SalesOrder.tenant_id)
            & (SalesOrderLine.order_id == SalesOrder.id),
        )
        .where(
            SalesOrderLine.tenant_id == tenant_id,
            SalesOrder.status.in_(
                [
                    SalesOrderStatus.CONFIRMED.value,
                    SalesOrderStatus.PARTIALLY_DELIVERED.value,
                ]
            ),
            SalesOrderLine.delivered_quantity < SalesOrderLine.ordered_quantity,
        )
        .distinct()
        .order_by(SalesOrderLine.item_id)
    )
    return list((await session.execute(stmt)).scalars().all())


@dataclass(frozen=True)
class AtpResult:
    """The ATP outcome for one item (D-044): ``available`` = on_hand − committed + on_order;
    ``atp_ok`` is ``available >= requested``; ``shortfall`` is ``requested − available`` clamped at
    0. Informational — a shortfall flags a backorder, it does NOT block confirmation."""

    item_id: uuid.UUID
    requested_quantity: Decimal
    on_hand: Decimal
    committed: Decimal
    on_order: Decimal
    available: Decimal
    atp_ok: bool
    shortfall: Decimal


async def atp_check(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    quantity: Decimal,
    on_date: date,
    exclude_order_id: uuid.UUID | None = None,
) -> AtpResult:
    """Available-to-promise for one item (PLAN 7.2, D-044): availability = inventory on-hand −
    committed (confirmed-undelivered sales orders) + on-order (procurement open-incoming). The
    ``on_date`` is the wire contract (v1 is a point-in-time snapshot; date-phased ATP is a later).
    Three bounded cross-module reads, no N+1. ``exclude_order_id`` excludes one order from the
    committed sum (confirm checks an order net of OTHER commitments)."""
    requested = Decimal(str(quantity))
    on_hand = Decimal(str(await inventory_queries.total_on_hand(session, tenant_id, item_id)))
    committed = await committed_quantity(
        session, tenant_id, item_id, exclude_order_id=exclude_order_id
    )
    on_order = Decimal(
        str(await procurement_queries.open_incoming_quantity(session, tenant_id, item_id))
    )
    available = on_hand - committed + on_order
    shortfall = requested - available
    if shortfall < 0:
        shortfall = Decimal(0)
    return AtpResult(
        item_id=item_id,
        requested_quantity=requested,
        on_hand=on_hand,
        committed=committed,
        on_order=on_order,
        available=available,
        atp_ok=available >= requested,
        shortfall=shortfall,
    )


async def open_confirmed_order_value(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    *,
    exclude_order_id: uuid.UUID | None = None,
) -> Decimal:
    """The total value of a customer's OPEN confirmed orders not yet billed (PLAN 7.2, D-044) — the
    open-order side of credit exposure. Sums ``total_amount`` over the customer's CONFIRMED /
    PARTIALLY_DELIVERED / DELIVERED orders (committed but not fully invoiced; an INVOICED order's
    exposure has moved to AR, a CLOSED/CANCELLED/DRAFT/CREDIT_BLOCKED order is nothing).
    ``exclude_order_id`` drops one order (the one being confirmed). SET-BASED (no N+1): a scan on
    the (tenant, customer_id, status) index, summed in Python for exact MoneyType (D-015)."""
    stmt = select(SalesOrder.total_amount).where(
        SalesOrder.tenant_id == tenant_id,
        SalesOrder.customer_id == customer_id,
        SalesOrder.status.in_(
            [
                SalesOrderStatus.CONFIRMED.value,
                SalesOrderStatus.PARTIALLY_DELIVERED.value,
                SalesOrderStatus.DELIVERED.value,
            ]
        ),
    )
    if exclude_order_id is not None:
        stmt = stmt.where(SalesOrder.id != exclude_order_id)
    rows = (await session.execute(stmt)).all()
    return sum((Decimal(str(value)) for (value,) in rows), Decimal(0))


async def customer_open_ar(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> Decimal:
    """The customer's open AR (sum of open_amount on POSTED customer invoices) — the receivables
    side of credit exposure (PLAN 7.2, D-044). A thin alias over finance's ``customer_open_balance``
    keyed by the opaque partner_id (= Customer.id, D-029), named for the credit-check intent so the
    order flow reads it without importing finance models (the bottom-up cross-module read)."""
    return await finance_queries.customer_open_balance(session, tenant_id, customer_id)

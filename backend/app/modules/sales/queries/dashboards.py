"""Sales dashboard KPI aggregates (part of sales' cross-module read contract, STRUCTURE §5 / D-058).

Two SANCTIONED sales/queries additions the REPORTING module (PLAN 13.1) reads DOWNWARD for its
role-based dashboard cards — the tenant-wide OPEN sales-order count + value, and a SIMPLE on-time-
delivery percentage. Reporting imports ONLY this queries surface (never sales/service or models), so
these live beside the per-customer ``open_confirmed_order_value`` (the credit-gate read) as the
tenant-wide rollups the dashboard needs. Each is ONE bounded aggregate, never N+1 (PERFORMANCE §6).

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales.constants import DeliveryStatus, SalesOrderStatus
from app.modules.sales.models import Delivery, SalesOrder

ZERO = Decimal("0")

# OPEN sales orders = confirmed commitments not yet fully delivered (CONFIRMED +
# PARTIALLY_DELIVERED) — a DRAFT order is not yet committed; a DELIVERED/INVOICED/CLOSED/CANCELLED/
# CREDIT_BLOCKED one is off the open-orders worklist (the committed_quantity precedent, D-044).
_OPEN_ORDER_STATUSES = (
    SalesOrderStatus.CONFIRMED.value,
    SalesOrderStatus.PARTIALLY_DELIVERED.value,
)

# A POSTED delivery against an order whose status reached a delivered/closed state is the unit OTD
# measures (a DRAFT/CANCELLED delivery shipped nothing; an undelivered order has no delivery yet).
_DELIVERED_ORDER_STATUSES = (
    SalesOrderStatus.DELIVERED.value,
    SalesOrderStatus.INVOICED.value,
    SalesOrderStatus.CLOSED.value,
)


@dataclass(frozen=True)
class OpenOrders:
    """The open-sales-orders KPI (D-058): how many confirmed-undelivered orders and their summed
    ``total_amount`` (transaction currency). The reporting ``CountValueKpi`` schema maps from
    this."""

    count: int
    total: Decimal


@dataclass(frozen=True)
class OnTimeDelivery:
    """The simple OTD KPI (D-058): of the tenant's POSTED deliveries against an order with a
    ``requested_date``, how many shipped on or before that date (``on_time``) out of ``total``. The
    reporting ``OtdKpi`` schema maps from this and computes the percentage; ``total`` 0 ⇒ no
    measurable deliveries (the router presents 0%)."""

    on_time: int
    total: int


async def open_sales_orders(session: AsyncSession, tenant_id: uuid.UUID) -> OpenOrders:
    """The tenant's OPEN sales orders — count + summed value (PLAN 13.1, D-058): confirmed-but-not-
    fully-delivered orders (CONFIRMED / PARTIALLY_DELIVERED), the open-order dashboard card. ONE
    aggregate over the (tenant, status) index — COUNT(*) + SUM(total_amount); the count is exact and
    the sum rides MoneyType so the exact-decimal total round-trips on both engines (D-015). Returns
    zeros for a tenant with no open orders. A sanctioned sales/queries addition reporting reads
    downward (no cycle — sales never imports reporting)."""
    stmt = select(
        func.count(SalesOrder.id),
        func.coalesce(func.sum(SalesOrder.total_amount), 0),
    ).where(
        SalesOrder.tenant_id == tenant_id,
        SalesOrder.status.in_(_OPEN_ORDER_STATUSES),
    )
    count, total = (await session.execute(stmt)).one()
    return OpenOrders(count=int(count), total=Decimal(str(total)) if total is not None else ZERO)


async def on_time_delivery(
    session: AsyncSession, tenant_id: uuid.UUID, *, date_from: date | None = None
) -> OnTimeDelivery:
    """A SIMPLE on-time-delivery measure (PLAN 13.1, D-058 — best-effort, documented).

    Of the tenant's POSTED deliveries joined to their sales order, counts how many shipped on or
    before the order's ``requested_date`` (``delivery_date <= requested_date``) out of the total
    that HAVE a requested_date. ONE join-aggregate over the (tenant, status) delivery index + order
    join (PERFORMANCE §6: no per-delivery N+1); ``date_from`` optionally bounds it to recent
    deliveries (a date-bounded KPI, PERFORMANCE §1). Deliveries on an order with NO requested_date
    are EXCLUDED from both numerator and denominator (there is no promise to measure against).

    DELIBERATELY SIMPLE (D-058): OTD is measured at the DELIVERY level against the order's single
    requested_date — NOT a line-level promised-date model, NOT confirmed-vs-requested, NOT partial-
    shipment weighting. A best-effort headline metric; a rigorous per-line promised-date OTD is a
    documented later (s4hana-parity)."""
    # Cast the per-row on-time predicate to 0/1 so the SUM counts on-time deliveries (portable on
    # both engines — SQLite has no native boolean SUM).
    on_time_expr = func.sum(
        func.cast(Delivery.delivery_date <= SalesOrder.requested_date, sa.Integer)
    )
    stmt = (
        select(func.count(Delivery.id), func.coalesce(on_time_expr, 0))
        .join(
            SalesOrder,
            (Delivery.tenant_id == SalesOrder.tenant_id)
            & (Delivery.sales_order_id == SalesOrder.id),
        )
        .where(
            Delivery.tenant_id == tenant_id,
            Delivery.status == DeliveryStatus.POSTED.value,
            SalesOrder.requested_date.is_not(None),
        )
    )
    if date_from is not None:
        stmt = stmt.where(Delivery.delivery_date >= date_from)
    total, on_time = (await session.execute(stmt)).one()
    return OnTimeDelivery(on_time=int(on_time or 0), total=int(total))

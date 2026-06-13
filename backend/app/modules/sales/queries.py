"""Sales' cross-module read interface (STRUCTURE §5).

Sales sits above inventory and finance in the dependency order: the O2C documents in 7.2–7.4
(quote → order → delivery → invoice) and finance AR reporting read THIS file to resolve customer
state + prices synchronously; sales imports finance/queries + inventory/queries downward. Keep this
surface thin and stable — it is a contract; it is the ONLY sales file other modules import.

The central D-029 link: finance AR stores a customer on each invoice/receipt as an opaque
``partner_id`` (no FK). ``get_customer_for_partner`` resolves that ``partner_id`` back to a
``Customer`` so AR aging / reporting can render the customer's name and payment terms — the
``partner_id`` IS the ``Customer.id``, so it is a thin alias over ``get_customer`` named for the
reporting intent (the exact mirror of procurement's ``get_vendor_for_partner``).

The PRICE RESOLVER is exposed here too: ``resolve_price`` is the public entry point 7.2's order
entry prices each line through, delegating to ``service/price_resolution.resolve_price`` (the
deterministic best-match picker, D-043). Putting it in queries.py keeps the rule that other modules
import only this file.

PLAN 7.2 adds the ORDER reads 7.3 (deliveries) + 7.4 (billing) call — ``get_sales_order``,
``so_line_open_to_deliver`` (ordered − delivered), ``get_order_for_delivery`` — and the ATP + credit
helpers the confirm gate + order UI use: ``committed_quantity`` (the reservation = confirmed-
undelivered demand per item), ``atp_check`` (availability = on-hand − committed + on-order, D-044),
``open_confirmed_order_value`` + ``customer_open_ar`` (the credit-exposure components).
``atp_check`` + ``customer_open_ar`` make SANCTIONED downward cross-module reads (inventory
on-hand, procurement on-order, finance open AR) — sales is above all three (STRUCTURE §5).

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
from app.modules.sales.constants import CustomerStatus, SalesOrderStatus
from app.modules.sales.models import Customer, SalesOrder, SalesOrderLine
from app.modules.sales.service.price_resolution import ResolvedPrice
from app.modules.sales.service.price_resolution import resolve_price as _resolve_price


async def get_customer(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> Customer | None:
    """The customer with ``customer_id`` in the tenant, or None. Lets another module read a
    customer's master fields (name, status, default currency, payment terms, credit limit) without
    importing sales models directly — the analogue of procurement's ``get_vendor``."""
    stmt = select(Customer).where(
        Customer.tenant_id == tenant_id, Customer.id == customer_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_customer_for_partner(
    session: AsyncSession, tenant_id: uuid.UUID, partner_id: uuid.UUID
) -> Customer | None:
    """The customer an AR document's opaque ``partner_id`` refers to (D-029), or None. AR aging /
    reporting calls this to resolve an invoice's ``partner_id`` to a customer name + payment terms.
    The ``partner_id`` IS the ``Customer.id`` (finance stores it without an FK), so this is
    ``get_customer`` named for the reporting intent — kept as its own function so AR call sites read
    intent-first and the alias survives any future indirection (the vendor precedent)."""
    return await get_customer(session, tenant_id, partner_id)


async def customer_exists(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> bool:
    """Whether a customer with ``customer_id`` exists in the tenant. The cheap existence check a
    quote / order line uses to validate its customer_id (the sales analogue of inventory's
    ``item_exists``)."""
    stmt = select(Customer.id).where(
        Customer.tenant_id == tenant_id, Customer.id == customer_id
    )
    return (await session.execute(stmt)).first() is not None


async def customer_status(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> CustomerStatus | None:
    """The customer's lifecycle status (ACTIVE/BLOCKED/INACTIVE), or None if the customer does not
    exist. 7.2's order flow reads this to refuse a NEW order against a non-ACTIVE customer (the soft
    block, distinct from the credit-limit block)."""
    stmt = select(Customer.status).where(
        Customer.tenant_id == tenant_id, Customer.id == customer_id
    )
    value = (await session.execute(stmt)).scalar_one_or_none()
    return CustomerStatus(value) if value is not None else None


async def customer_credit_limit(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> Decimal | None:
    """The customer's static credit limit = max outstanding AR (D-043), or None if the customer does
    not exist. 7.2's order confirmation reads this for the credit-limit block: 0 = cash-only (no
    open credit allowed), a positive value = the ceiling. Exposed so the order flow need not import
    sales models."""
    stmt = select(Customer.credit_limit).where(
        Customer.tenant_id == tenant_id, Customer.id == customer_id
    )
    value = (await session.execute(stmt)).scalar_one_or_none()
    return Decimal(str(value)) if value is not None else None


async def customer_payment_terms_days(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> int | None:
    """The customer's net-days payment terms (e.g. 30 = NET30), or None if the customer does not
    exist. The order→invoice flow (7.4) reads this to default an invoice's due date (invoice_date +
    days), the same math AR uses today — exposed so the chain need not import sales models."""
    stmt = select(Customer.payment_terms_days).where(
        Customer.tenant_id == tenant_id, Customer.id == customer_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def customer_default_currency(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> str | None:
    """The customer's default currency code (ISO alpha-3), or None if the customer does not exist.
    The quote/order flow (7.2) defaults a document's currency from this; exposed so the chain need
    not import sales models."""
    stmt = select(Customer.default_currency_code).where(
        Customer.tenant_id == tenant_id, Customer.id == customer_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def resolve_price(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    customer_id: uuid.UUID,
    on_date: date,
    quantity: Decimal,
    currency: str,
) -> ResolvedPrice:
    """The applicable base unit price for an item/customer/date/quantity/currency (PLAN 7.1, D-043).

    The public entry point 7.2's order entry prices each line through. Delegates to the
    deterministic best-match resolver in ``service/price_resolution`` (documented there); returns a
    :class:`ResolvedPrice` whose ``matched`` is False when no ACTIVE price list applies. Bounded to
    two queries — no N+1. Exposed here so other modules import only ``sales/queries``."""
    return await _resolve_price(
        session,
        tenant_id,
        item_id=item_id,
        customer_id=customer_id,
        on_date=on_date,
        quantity=quantity,
        currency=currency,
    )


# --- Sales-order reads (PLAN 7.2 → consumed by 7.3 deliveries + 7.4 billing) ------------------


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


async def so_line_open_to_deliver(
    session: AsyncSession, tenant_id: uuid.UUID, order_line_id: uuid.UUID
) -> Decimal | None:
    """The still-open-to-deliver quantity on an order line — ORDERED minus DELIVERED — or None if
    the line does not exist (PLAN 7.2 → 7.3). A delivery (7.3) caps a pick at this. A point lookup
    on the maintained ``delivered_quantity`` (raised by 7.3), not a SUM over deliveries."""
    line = (
        await session.execute(
            select(SalesOrderLine).where(
                SalesOrderLine.tenant_id == tenant_id,
                SalesOrderLine.id == order_line_id,
            )
        )
    ).scalar_one_or_none()
    if line is None:
        return None
    return Decimal(str(line.ordered_quantity)) - Decimal(str(line.delivered_quantity))


async def get_order_for_delivery(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> tuple[SalesOrder, list[SalesOrderLine]] | None:
    """The order header + its lines (item, ordered/delivered quantities, unit price, tax code) — the
    data a delivery (7.3) needs to build pick lines and billing (7.4) needs to invoice. None when
    the order is unknown to this tenant. Two indexed reads (header by PK, lines by (tenant,
    order_id)); no N+1 over lines."""
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
    line = (
        await session.execute(
            select(SalesOrderLine).where(
                SalesOrderLine.tenant_id == tenant_id,
                SalesOrderLine.id == order_line_id,
            )
        )
    ).scalar_one_or_none()
    if line is None:
        return None
    return Decimal(str(line.delivered_quantity)) - Decimal(str(line.invoiced_quantity))


async def get_order_for_invoice(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> tuple[SalesOrder, list[SalesOrderLine]] | None:
    """The order header + its lines for BILLING (PLAN 7.3 → 7.4): the data 7.4's invoice run needs
    to bill the DELIVERED-but-not-yet-invoiced quantity (delivered − invoiced per line). None when
    the order is unknown to this tenant. The same two-read shape as ``get_order_for_delivery``
    (header by PK, lines by (tenant, order_id)), named for the billing intent; no N+1 over lines."""
    return await get_order_for_delivery(session, tenant_id, order_id)


# --- ATP: committed quantity + the availability check (PLAN 7.2, D-044) -----------------------


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

    SET-BASED (no per-order N+1, PERFORMANCE §2): one join over order lines filtered by the order's
    status + a positive open quantity, summed in PYTHON over the (small) open set so the
    exact-decimal QuantityType round-trips identically on both engines (D-015: SQL never subtracts
    two scaled quantity columns for the result value)."""
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
    """Available-to-promise for one item (PLAN 7.2, D-044): availability = inventory on-hand
    (``total_on_hand``) − committed (confirmed-undelivered sales orders) + on-order (procurement
    ``open_incoming_quantity``). ``on_date`` is accepted for the wire contract (v1 availability is
    a point-in-time snapshot — date-phased ATP is the documented later). Three bounded cross-module
    reads (inventory on-hand, sales committed, procurement on-order); no N+1. ``exclude_order_id``
    excludes one order from the committed sum (confirm checks an order net of OTHER commitments)."""
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


# --- Credit exposure (PLAN 7.2, D-044) --------------------------------------------------------


async def open_confirmed_order_value(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    *,
    exclude_order_id: uuid.UUID | None = None,
) -> Decimal:
    """The total value of a customer's OPEN confirmed orders not yet billed (PLAN 7.2, D-044) — the
    open-order side of credit exposure. Sums ``total_amount`` over the customer's CONFIRMED /
    PARTIALLY_DELIVERED / DELIVERED orders (committed but not yet fully invoiced; an INVOICED
    order's exposure has moved to AR, a CLOSED/CANCELLED/DRAFT/CREDIT_BLOCKED order is nothing).
    ``exclude_order_id`` drops one order (the one being confirmed, counted separately).

    SET-BASED (no per-order N+1): one filtered scan on the (tenant, customer_id, status) index,
    summed in Python so the exact-decimal MoneyType round-trips identically on both engines
    (D-015)."""
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

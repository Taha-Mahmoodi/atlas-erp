"""Customer-master reads + the price resolver (part of sales' cross-module read contract).

Split out of ``sales/queries.py`` at the 400-line cap (STRUCTURE §8.4) and re-exported from the
package ``__init__`` so other modules still import the whole surface from
``app.modules.sales.queries``.
These functions read the ``Customer`` master (name, status, currency, payment terms, credit limit)
and the per-customer/item price (``resolve_price``, the public entry 7.2 prices lines through).

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales.constants import CustomerStatus
from app.modules.sales.models import Customer
from app.modules.sales.service.price_resolution import ResolvedPrice
from app.modules.sales.service.price_resolution import resolve_list_prices as _resolve_list_prices
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
    ``get_customer`` named for the reporting intent (the vendor precedent)."""
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


async def resolve_list_prices(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_ids: Iterable[uuid.UUID],
    on_date: date,
    currency: str | None = None,
    quantity: Decimal = Decimal(1),
) -> dict[uuid.UUID, ResolvedPrice]:
    """The GENERAL (customer-less) list price for MANY items in ONE query (PLAN 19, spec Q6).

    The walk-in counterpart to ``resolve_price``: a property's website has no customer record for
    the guest ordering dinner, so only GENERAL price lists apply. Absent key = no ACTIVE general
    list prices that item on that date. Delegates to ``service/price_resolution``, which documents
    the rule and why ``currency`` is optional on a read and mandatory in spirit on a write."""
    return await _resolve_list_prices(
        session,
        tenant_id,
        item_ids=item_ids,
        on_date=on_date,
        currency=currency,
        quantity=quantity,
    )

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

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales.constants import CustomerStatus
from app.modules.sales.models import Customer
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

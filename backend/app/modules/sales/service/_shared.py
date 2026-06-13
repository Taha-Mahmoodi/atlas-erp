"""Shared validation + numbering + line-pricing helpers for the O2C document services (PLAN 7.2).

Kept in one private module so the quote / order / conversion services stay small and the
cross-module validation rules (item exists, currency exists, customer exists/ACTIVE) + the line
pricing math (resolver default, discount, line amount) live in ONE place — greppable and consistent.
Every cross-module check goes through the owning module's queries contract (D-029), never a
cross-module FK. The numbering helper wraps ensure_sequence + claim_number so both documents claim
their gapless number at creation identically (D-012/D-040).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.core.money import quantize_for_currency
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.sales import queries as sales_queries
from app.modules.sales.constants import CustomerStatus, DiscountType


@dataclass(frozen=True)
class LineInput:
    """The validated, currency-resolved input for one quote/order line — produced by the create /
    convert paths and consumed by the document writers. ``unit_price`` is already resolved (the
    payload value or the price-resolver default); ``line_amount`` is the computed net."""

    item_id: uuid.UUID
    description: str | None
    quantity: Decimal
    uom_id: uuid.UUID
    unit_price: Decimal
    discount_type: str | None
    discount_value: Decimal | None
    line_amount: Decimal
    tax_code_id: uuid.UUID | None = None


async def validate_currency(
    session: AsyncSession, tenant_id: uuid.UUID, currency_code: str
) -> None:
    """The currency must exist in finance's catalog (D-029, via finance/queries)."""
    if not await finance_queries.currency_exists(session, tenant_id, currency_code):
        raise ValidationFailedError(
            message=f"Currency {currency_code} does not exist in the finance catalog",
            code="sales.currency_not_found",
            details={"currency_code": currency_code},
        )


async def validate_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    """The item must exist in inventory (D-029, via inventory/queries.item_exists)."""
    if not await inventory_queries.item_exists(session, tenant_id, item_id):
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="sales.item_not_found",
            details={"item_id": str(item_id)},
        )


def validate_quantity(quantity: Decimal) -> Decimal:
    """A document line quantity must be > 0 (every quote/order line)."""
    qty = Decimal(str(quantity))
    if qty <= 0:
        raise ValidationFailedError(
            message="A line quantity must be greater than zero",
            code="sales.line_quantity_invalid",
            details={"quantity": str(qty)},
        )
    return qty


async def require_customer_exists(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> None:
    """The customer must exist (a quote may name any existing customer — the ACTIVE gate is an
    ORDER-confirmation rule, not a quote rule). Reads via sales/queries (intra-module)."""
    if not await sales_queries.customer_exists(session, tenant_id, customer_id):
        raise ValidationFailedError(
            message="Referenced customer does not exist",
            code="sales.customer_not_found",
            details={"customer_id": str(customer_id)},
        )


async def require_active_customer(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> None:
    """The customer must exist AND be ACTIVE (not BLOCKED/INACTIVE) — the v1 order source-control
    rule (the soft block, distinct from the credit-limit block). Reads the status via sales/queries.
    Raises 422 sales.customer_not_active otherwise."""
    status = await sales_queries.customer_status(session, tenant_id, customer_id)
    if status is None:
        raise ValidationFailedError(
            message="Referenced customer does not exist",
            code="sales.customer_not_found",
            details={"customer_id": str(customer_id)},
        )
    if status != CustomerStatus.ACTIVE:
        raise ValidationFailedError(
            message=f"Customer is {status.value}; a sales order needs an ACTIVE customer",
            code="sales.customer_not_active",
            details={"customer_id": str(customer_id), "status": status.value},
        )


async def resolve_currency(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    currency_code: str | None,
) -> str:
    """Resolve a document's currency: the supplied code, else the customer's default currency. The
    result is validated to exist in finance (a customer's default is already validated at customer
    create, but a supplied override must be re-checked)."""
    resolved = currency_code or await sales_queries.customer_default_currency(
        session, tenant_id, customer_id
    )
    if resolved is None:
        raise ValidationFailedError(
            message="The customer has no default currency and none was supplied",
            code="sales.currency_unresolved",
            details={"customer_id": str(customer_id)},
        )
    await validate_currency(session, tenant_id, resolved)
    return resolved


def compute_line_amount(
    quantity: Decimal,
    unit_price: Decimal,
    discount_type: str | None,
    discount_value: Decimal | None,
    currency_code: str,
) -> Decimal:
    """The net line amount = qty × unit_price − discount, quantized to the currency (D-015). A
    PERCENT discount takes ``discount_value`` % off the gross (qty × unit_price); an AMOUNT discount
    takes ``discount_value`` off per unit (× qty). The result is clamped at 0 (a discount can zero a
    line but never make it negative)."""
    gross = Decimal(str(quantity)) * Decimal(str(unit_price))
    discount = Decimal(0)
    if discount_type is not None and discount_value is not None:
        value = Decimal(str(discount_value))
        if DiscountType(discount_type) == DiscountType.PERCENT:
            discount = gross * value / Decimal(100)
        else:  # AMOUNT: per-unit amount off
            discount = value * Decimal(str(quantity))
    net = gross - discount
    if net < 0:
        net = Decimal(0)
    return quantize_for_currency(net, currency_code)


async def build_line_input(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    customer_id: uuid.UUID,
    currency_code: str,
    on_date: date,
    item_id: uuid.UUID,
    description: str | None,
    quantity: Decimal,
    uom_id: uuid.UUID,
    unit_price: Decimal | None,
    discount_type: str | None,
    discount_value: Decimal | None,
    tax_code_id: uuid.UUID | None = None,
) -> LineInput:
    """Validate one line + resolve its price into a :class:`LineInput`. The item is validated to
    exist; the quantity to be > 0. When ``unit_price`` is None the price resolver (D-043) defaults
    it
    for this item/customer/date/quantity/currency — and a no-match resolution with no supplied price
    is rejected (the line needs a price). The discount is applied to compute the net line amount."""
    await validate_item(session, tenant_id, item_id)
    qty = validate_quantity(quantity)
    resolved_price = unit_price
    if resolved_price is None:
        resolved = await sales_queries.resolve_price(
            session,
            tenant_id,
            item_id=item_id,
            customer_id=customer_id,
            on_date=on_date,
            quantity=qty,
            currency=currency_code,
        )
        if not resolved.matched or resolved.unit_price is None:
            raise ValidationFailedError(
                message="No price list applies to this item; supply a unit price",
                code="sales.price_unresolved",
                details={"item_id": str(item_id)},
            )
        resolved_price = resolved.unit_price
    price = Decimal(str(resolved_price))
    if price < 0:
        raise ValidationFailedError(
            message="A line unit price cannot be negative",
            code="sales.unit_price_invalid",
            details={"item_id": str(item_id)},
        )
    dtype = discount_type if discount_type is not None else None
    dvalue = (
        Decimal(str(discount_value))
        if discount_type is not None and discount_value is not None
        else None
    )
    line_amount = compute_line_amount(qty, price, dtype, dvalue, currency_code)
    return LineInput(
        item_id=item_id,
        description=description,
        quantity=qty,
        uom_id=uom_id,
        unit_price=price,
        discount_type=dtype,
        discount_value=dvalue,
        line_amount=line_amount,
        tax_code_id=tax_code_id,
    )


async def claim_document_number(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    sequence_name: str,
    prefix: str,
    padding: int,
    on_date: date,
) -> str:
    """Ensure the sequence exists (year-resetting) and claim the next gapless number (D-012/D-040:
    claimed at creation, so a quote/order is referenceable immediately). The claim runs in the
    caller's transaction so gaplessness for committed documents falls out of ACID."""
    await ensure_sequence(session, tenant_id, sequence_name, prefix, padding, year_reset=True)
    return await claim_number(session, tenant_id, sequence_name, on_date=on_date)

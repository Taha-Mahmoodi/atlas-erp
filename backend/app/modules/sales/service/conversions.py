"""O2C conversion (PLAN 7.2): quote → order.

Converting an ACCEPTED quote copies its lines (item, quantity, unit_price, discount) into a new
DRAFT order, links the two registry entries with a docflow edge (the D-012 chain the DocFlowViewer
renders, link_type 'converted_to'), sets the order's ``source_quote_id``, and advances the quote to
CONVERTED. The order is created through the shared writer in ``orders`` so it goes through the SAME
validation + numbering + document registration (no second code path). The order's prices come from
the quote (a quote IS the price offer the customer accepted — they are not re-resolved), so a quote
line's frozen ``unit_price`` carries straight through. Idempotency (D-013) is owned by the endpoint.

Precondition: the quote must be ACCEPTED (a DRAFT/SENT/EXPIRED/REJECTED quote is not a commitment a
customer agreed to; a CONVERTED one already has a successor). The order's customer is the quote's
customer, validated ACTIVE at order creation (a customer blocked after the quote was accepted cannot
receive the order — the same soft block a from-scratch order enforces).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError
from app.modules.sales.constants import (
    QUOTE_CONVERTED_TO_ORDER_LINK,
    QuoteStatus,
)
from app.modules.sales.models import SalesOrder
from app.modules.sales.schemas import ConvertQuoteToOrder
from app.modules.sales.service import orders, quotes
from app.modules.sales.service._shared import (
    LineInput,
    compute_line_amount,
    require_active_customer,
)


async def convert_quote_to_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    payload: ConvertQuoteToOrder,
) -> SalesOrder:
    """Convert an ACCEPTED quote into a DRAFT order (PLAN 7.2): copy lines with the quote's frozen
    prices + discounts, validate the customer is still ACTIVE, write the order (shared writer), link
    docflow quote→order ('converted_to'), set source_quote_id, and mark the quote CONVERTED."""
    quote = await quotes.get_quote(session, tenant_id, quote_id)
    if QuoteStatus(quote.status) != QuoteStatus.ACCEPTED:
        raise ConflictError(
            message="Only an accepted quote can be converted to an order",
            code="sales.quote_not_accepted",
            details={"status": quote.status},
        )
    await require_active_customer(session, tenant_id, quote.customer_id)
    quote_lines = await quotes.get_quote_lines(session, tenant_id, quote_id)

    order_lines: list[LineInput] = []
    for line in quote_lines:
        quantity = Decimal(str(line.quantity))
        unit_price = Decimal(str(line.unit_price))
        discount_value = (
            Decimal(str(line.discount_value)) if line.discount_value is not None else None
        )
        line_amount = compute_line_amount(
            quantity, unit_price, line.discount_type, discount_value, quote.currency_code
        )
        order_lines.append(
            LineInput(
                item_id=line.item_id,
                description=line.description,
                quantity=quantity,
                uom_id=line.uom_id,
                unit_price=unit_price,
                discount_type=line.discount_type,
                discount_value=discount_value,
                line_amount=line_amount,
                tax_code_id=None,
            )
        )

    order = await orders.write_sales_order(
        session,
        tenant_id,
        customer_id=quote.customer_id,
        currency_code=quote.currency_code,
        order_date=payload.order_date or date.today(),
        requested_date=payload.requested_date,
        notes=payload.notes,
        lines=order_lines,
        source_quote_id=quote_id,
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=quote.document_id,
        successor=order.document_id,
        link_type=QUOTE_CONVERTED_TO_ORDER_LINK,
    )
    quote.status = QuoteStatus.CONVERTED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, quote.document_id, status=QuoteStatus.CONVERTED.value
    )
    return order

"""Sales-billing POST (PLAN 7.4, D-046) — the heart — split from ``billing.py`` at the 400-line cap
(STRUCTURE §8.4, the delivery_post precedent). The DRAFT create + helpers + ``cancel_billing`` stay
in ``billing.py``; the reads in ``billing_reads.py``; the post path + its post-only helpers live
here. ``__init__`` re-exports all three as one ``service`` surface (``service.post_billing``).

``post_billing`` is the heart: in ONE transaction it PUBLISHES ``BillingInvoiced`` — finance's
handler
creates + posts the AR customer invoice (Dr AR control / Cr sales-revenue + Cr output tax) — raises
each order line's invoiced_quantity, advances the order status (INVOICED / CLOSED), links docflow
order → billing, and sets the billing POSTED. A closed billing period trips the AR invoice's journal
trigger and rolls the WHOLE post back.

The MIRROR of procurement's ``post_invoice_match``: sales resolves the AR control + sales-revenue
accounts (+ the customer's payment terms snapshot for the due date) from finance/queries UP FRONT
(downward reads — a missing posting default fails the post before any state change, D-046), then
publishes the event with those accounts so finance's handler is a thin builder. Sales never imports
finance/service (STRUCTURE §5).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError
from app.modules.finance import queries as finance_queries
from app.modules.sales import queries as sales_queries
from app.modules.sales.constants import (
    ORDER_BILLED_BY_BILLING_LINK,
    BillingStatus,
    SalesOrderStatus,
)
from app.modules.sales.events import BillingInvoiced, BillingInvoiceLine
from app.modules.sales.models import SalesBilling, SalesBillingLine, SalesOrder, SalesOrderLine
from app.modules.sales.service.billing_reads import get_billing, get_billing_lines
from app.modules.sales.service.orders import get_sales_order, get_sales_order_lines


def _require_postable(billing: SalesBilling, billing_id: uuid.UUID) -> None:
    status = BillingStatus(billing.status)
    if status == BillingStatus.POSTED:
        raise ConflictError(
            message="The billing is already posted",
            code="sales.billing_already_posted",
            details={"billing_id": str(billing_id)},
        )
    if status != BillingStatus.DRAFT:
        raise ConflictError(
            message=f"A {billing.status} billing cannot be posted",
            code="sales.billing_not_postable",
            details={"billing_id": str(billing_id), "status": billing.status},
        )


async def post_billing(
    session: AsyncSession, tenant_id: uuid.UUID, billing_id: uuid.UUID
) -> SalesBilling:
    """Post a DRAFT billing (PLAN 7.4, D-046) — the heart. In ONE transaction: PUBLISH
    ``BillingInvoiced`` so finance's handler creates + posts the AR customer invoice (Dr AR control
    /
    Cr sales-revenue + Cr output tax, partner_id = customer id, due = billing_date + terms); raise
    each order line's invoiced_quantity; advance the order (INVOICED when fully invoiced, CLOSED
    when
    fully delivered AND invoiced); link docflow order → billing; set the billing POSTED. A closed
    billing period trips the AR invoice's journal trigger and rolls it ALL back.

    Only a DRAFT billing posts; a POSTED one is idempotent-rejected (terminal). The caller commits
    via
    uow; the published event drains in the same uow."""
    billing = await get_billing(session, tenant_id, billing_id)
    _require_postable(billing, billing_id)

    # Resolve the AR control + revenue accounts UP FRONT (downward reads) — a missing posting
    # default
    # raises 422 here, so the post fails before any state change (the match-post precedent, D-046).
    ar_account_id = await finance_queries.ar_control_account(session, tenant_id)
    revenue_account_id = await finance_queries.sales_revenue_account(session, tenant_id)

    lines = await get_billing_lines(session, tenant_id, billing_id)
    order_lines = {
        line.id: line
        for line in await get_sales_order_lines(session, tenant_id, billing.sales_order_id)
    }
    invoice_lines = _raise_invoiced_and_build_invoice_lines(lines, order_lines)
    await _advance_order_status(
        session, tenant_id, billing.sales_order_id, order_lines.values()
    )

    customer = await sales_queries.get_customer(session, tenant_id, billing.customer_id)
    partner_name = customer.name if customer is not None else ""
    due_date = billing.billing_date + timedelta(days=billing.payment_terms_days)

    billing.status = BillingStatus.POSTED.value
    billing.posted_at = datetime.now()
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, billing.document_id, status=BillingStatus.POSTED.value
    )
    order = await session.get(SalesOrder, billing.sales_order_id)
    if order is not None:
        await docflow.link_documents(
            session,
            tenant_id,
            predecessor=order.document_id,
            successor=billing.document_id,
            link_type=ORDER_BILLED_BY_BILLING_LINK,
        )

    # Publish AFTER sales' own writes settle: finance's handler creates + posts the AR customer
    # invoice, drained in this same uow (D-011/D-046).
    publish(
        session,
        BillingInvoiced(
            tenant_id=tenant_id,
            billing_id=billing.id,
            billing_number=billing.billing_number,
            document_id=billing.document_id,
            partner_id=billing.customer_id,
            partner_name=partner_name,
            billing_date=billing.billing_date,
            due_date=due_date,
            currency_code=billing.currency_code,
            ar_account_id=ar_account_id,
            revenue_account_id=revenue_account_id,
            lines=tuple(invoice_lines),
        ),
    )
    return billing


def _raise_invoiced_and_build_invoice_lines(
    lines: list[SalesBillingLine],
    order_lines: dict[uuid.UUID, SalesOrderLine],
) -> list[BillingInvoiceLine]:
    """Raise each order line's invoiced_quantity by its billed quantity and build the per-line AR
    invoice payload finance's handler posts (net + tax code, the item as the dimension). The order
    lines are mutated in-session."""
    invoice_lines: list[BillingInvoiceLine] = []
    for line in lines:
        order_line = order_lines[line.sales_order_line_id]
        order_line.invoiced_quantity = Decimal(str(order_line.invoiced_quantity)) + Decimal(
            str(line.quantity)
        )
        invoice_lines.append(
            BillingInvoiceLine(
                item_id=line.item_id,
                net_amount=Decimal(str(line.line_amount)),
                tax_code_id=line.tax_code_id,
            )
        )
    return invoice_lines


async def _advance_order_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    order_lines,
) -> None:
    """Advance the order after a billing raised the lines' invoiced_quantity (PLAN 7.4): CLOSED when
    every line is fully delivered AND fully invoiced (the O2C end state), else INVOICED when every
    line is fully invoiced (but not yet fully delivered — more to ship), else leave the
    delivery-driven status (PARTIALLY_DELIVERED / DELIVERED) untouched (more to invoice). The order
    +
    lines are already loaded/mutated in this session."""
    fully_invoiced = all(
        Decimal(str(line.invoiced_quantity)) >= Decimal(str(line.ordered_quantity))
        for line in order_lines
    )
    fully_delivered = all(
        Decimal(str(line.delivered_quantity)) >= Decimal(str(line.ordered_quantity))
        for line in order_lines
    )
    if not fully_invoiced:
        return
    new_status = (
        SalesOrderStatus.CLOSED if fully_delivered else SalesOrderStatus.INVOICED
    )
    order = await get_sales_order(session, tenant_id, order_id)
    if order is None:
        return
    order.status = new_status.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, order.document_id, status=new_status.value
    )

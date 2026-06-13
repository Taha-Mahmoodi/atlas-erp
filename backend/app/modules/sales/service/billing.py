"""Sales-billing create / cancel + reads (PLAN 7.4, D-046): create a DRAFT billing against a sales
order, cancel a DRAFT, and the list/point reads. The POST path (the heart) + its helpers live in
``billing_post.py`` (split at the 400-line cap, STRUCTURE §8.4); the package ``__init__`` re-exports
both as one ``service`` surface.

A billing records the decision to invoice DELIVERED goods — the AR mirror of the procurement invoice
match. ``create_billing`` writes a DRAFT (validates the order is at least partially delivered, each
billed quantity ≤ the order line's delivered-not-yet-invoiced quantity → over-billing 422
``sales.over_billing``) and claims the BIL number at creation (D-040). No journal yet — that is POST
(``billing_post.post_billing``).

Cross-module rule (STRUCTURE §5 / D-046): sales NEVER calls finance's service — the AR effect goes
through the event bus (POST publishes ``BillingInvoiced``; finance's handler creates + posts the AR
customer invoice). Sales reads only finance/queries (the AR control + revenue accounts, resolved at
POST). The ``bill_all_delivered`` convenience path bills every delivered-not-invoiced order line.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.sales.constants import (
    BILLING_DOC_TYPE,
    BILLING_NUMBER_PADDING,
    BILLING_NUMBER_PREFIX,
    BILLING_SEQUENCE_NAME,
    DELIVERY_INVOICED_BY_BILLING_LINK,
    BillingStatus,
    SalesOrderStatus,
)
from app.modules.sales.models import (
    SalesBilling,
    SalesBillingLine,
    SalesOrder,
    SalesOrderLine,
)
from app.modules.sales.schemas import BillingCreate
from app.modules.sales.service._shared import claim_document_number, compute_line_amount
from app.modules.sales.service.billing_reads import get_billing
from app.modules.sales.service.orders import get_sales_order_lines

# An order is billable once at least partially delivered (you invoice what shipped). DRAFT /
# CONFIRMED-but-undelivered / CREDIT_BLOCKED / CANCELLED start no billing; INVOICED/CLOSED are done.
_BILLABLE_ORDER_STATUSES = frozenset(
    {
        SalesOrderStatus.PARTIALLY_DELIVERED,
        SalesOrderStatus.DELIVERED,
        # INVOICED is reachable when an earlier billing fully invoiced the delivered qty but a later
        # delivery added more open-to-invoice quantity — a follow-up billing completes it.
        SalesOrderStatus.INVOICED,
    }
)


@dataclass(frozen=True)
class _BillingLineInput:
    """One validated billing line: the order line billed, the snapshot item/price/discount/tax from
    it, the optional source delivery line, the billed quantity, and the computed net line amount."""

    sales_order_line_id: uuid.UUID
    delivery_line_id: uuid.UUID | None
    item_id: uuid.UUID
    quantity: Decimal
    unit_price: Decimal
    discount_type: str | None
    discount_value: Decimal | None
    line_amount: Decimal
    tax_code_id: uuid.UUID | None


async def _require_billable_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> SalesOrder:
    order = await session.get(SalesOrder, order_id)
    if order is None or order.tenant_id != tenant_id:
        raise ValidationFailedError(
            message="Referenced sales order does not exist",
            code="sales.order_not_found",
            details={"sales_order_id": str(order_id)},
        )
    if SalesOrderStatus(order.status) not in _BILLABLE_ORDER_STATUSES:
        raise ValidationFailedError(
            message=f"A {order.status} sales order has nothing delivered to bill",
            code="sales.order_not_delivered",
            details={"sales_order_id": str(order_id), "status": order.status},
        )
    return order


def _validate_quantity(quantity: Decimal) -> Decimal:
    qty = Decimal(str(quantity))
    if qty <= 0:
        raise ValidationFailedError(
            message="A billing line quantity must be greater than zero",
            code="sales.line_quantity_invalid",
            details={"quantity": str(qty)},
        )
    return qty


def _build_billing_line(
    order_line: SalesOrderLine,
    *,
    delivery_line_id: uuid.UUID | None,
    qty: Decimal,
    currency_code: str,
) -> _BillingLineInput:
    """Snapshot the priced fields from the order line and compute the net line amount for a billed
    quantity (the order-line discount applies pro-rata via the shared ``compute_line_amount``)."""
    line_amount = compute_line_amount(
        qty,
        Decimal(str(order_line.unit_price)),
        order_line.discount_type,
        Decimal(str(order_line.discount_value))
        if order_line.discount_value is not None
        else None,
        currency_code,
    )
    return _BillingLineInput(
        sales_order_line_id=order_line.id,
        delivery_line_id=delivery_line_id,
        item_id=order_line.item_id,
        quantity=qty,
        unit_price=Decimal(str(order_line.unit_price)),
        discount_type=order_line.discount_type,
        discount_value=Decimal(str(order_line.discount_value))
        if order_line.discount_value is not None
        else None,
        line_amount=line_amount,
        tax_code_id=order_line.tax_code_id,
    )


def _validate_billing_line(
    order_id: uuid.UUID,
    order_lines: dict[uuid.UUID, SalesOrderLine],
    payload_line: object,
    currency_code: str,
) -> _BillingLineInput:
    """Validate one billing line against its order line: the line belongs to the order, the qty is
    > 0 and within the still-open-to-invoice quantity = delivered − invoiced (over-billing REJECTED
    422 ``sales.over_billing`` — you cannot invoice beyond what shipped)."""
    order_line = order_lines.get(payload_line.sales_order_line_id)  # type: ignore[attr-defined]
    if order_line is None:
        raise ValidationFailedError(
            message="The billing line does not belong to this sales order",
            code="sales.billing_line_not_on_order",
            details={
                "sales_order_id": str(order_id),
                "sales_order_line_id": str(
                    payload_line.sales_order_line_id  # type: ignore[attr-defined]
                ),
            },
        )
    qty = _validate_quantity(payload_line.quantity)  # type: ignore[attr-defined]
    open_qty = Decimal(str(order_line.delivered_quantity)) - Decimal(
        str(order_line.invoiced_quantity)
    )
    if qty > open_qty:
        raise ValidationFailedError(
            message="The billed quantity exceeds the delivered-not-yet-invoiced quantity",
            code="sales.over_billing",
            details={
                "sales_order_line_id": str(order_line.id),
                "open_quantity": str(open_qty),
                "quantity": str(qty),
            },
        )
    return _build_billing_line(
        order_line,
        delivery_line_id=payload_line.delivery_line_id,  # type: ignore[attr-defined]
        qty=qty,
        currency_code=currency_code,
    )


def _build_all_delivered_lines(
    order_lines: dict[uuid.UUID, SalesOrderLine], currency_code: str
) -> list[_BillingLineInput]:
    """The convenience path: bill every order line's full delivered-not-yet-invoiced quantity (lines
    with nothing open are skipped). No delivery line is named (the chain is order → billing)."""
    built: list[_BillingLineInput] = []
    for order_line in order_lines.values():
        open_qty = Decimal(str(order_line.delivered_quantity)) - Decimal(
            str(order_line.invoiced_quantity)
        )
        if open_qty <= 0:
            continue
        built.append(
            _build_billing_line(
                order_line, delivery_line_id=None, qty=open_qty, currency_code=currency_code
            )
        )
    return built


async def create_billing(
    session: AsyncSession, tenant_id: uuid.UUID, payload: BillingCreate
) -> SalesBilling:
    """Create a DRAFT billing against a sales order (PLAN 7.4). Validates the order is at least
    partially delivered (else 422 ``sales.order_not_delivered``), each line belongs to it and does
    not over-bill its delivered-not-invoiced quantity (over-billing → 422 ``sales.over_billing``).
    Snapshots the customer + payment terms from the order and the priced fields per line from the
    order line, claims the BIL number (D-040), and links each named delivery → billing. No journal
    yet — that is POST. ``bill_all_delivered`` bills every delivered-not-invoiced line."""
    order = await _require_billable_order(session, tenant_id, payload.sales_order_id)
    order_lines = {
        line.id: line for line in await get_sales_order_lines(session, tenant_id, order.id)
    }
    billing_date = payload.billing_date or date.today()

    if payload.bill_all_delivered:
        validated = _build_all_delivered_lines(order_lines, order.currency_code)
    else:
        if not payload.lines:
            raise ValidationFailedError(
                message="A billing needs at least one line (or bill_all_delivered)",
                code="sales.billing_no_lines",
            )
        validated = [
            _validate_billing_line(order.id, order_lines, line, order.currency_code)
            for line in payload.lines
        ]
    if not validated:
        raise ValidationFailedError(
            message="The order has no delivered-not-yet-invoiced quantity to bill",
            code="sales.nothing_to_bill",
            details={"sales_order_id": str(order.id)},
        )

    total = sum((line.line_amount for line in validated), Decimal(0))
    billing_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        BILLING_DOC_TYPE,
        billing_id,
        doc_number=None,
        status=BillingStatus.DRAFT.value,
    )
    number = await claim_document_number(
        session,
        tenant_id,
        sequence_name=BILLING_SEQUENCE_NAME,
        prefix=BILLING_NUMBER_PREFIX,
        padding=BILLING_NUMBER_PADDING,
        on_date=billing_date,
    )
    billing = SalesBilling(
        id=billing_id,
        tenant_id=tenant_id,
        document_id=document.id,
        billing_number=number,
        status=BillingStatus.DRAFT.value,
        sales_order_id=order.id,
        customer_id=order.customer_id,
        currency_code=order.currency_code,
        billing_date=billing_date,
        payment_terms_days=order.payment_terms_days,
        total_amount=total,
        notes=payload.notes,
    )
    session.add(billing)
    for index, line in enumerate(validated, start=1):
        session.add(
            SalesBillingLine(
                tenant_id=tenant_id,
                billing_id=billing_id,
                line_number=index,
                sales_order_line_id=line.sales_order_line_id,
                delivery_line_id=line.delivery_line_id,
                item_id=line.item_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_type=line.discount_type,
                discount_value=line.discount_value,
                line_amount=line.line_amount,
                tax_code_id=line.tax_code_id,
            )
        )
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=number, status=BillingStatus.DRAFT.value
    )
    await _link_delivery_predecessors(session, tenant_id, billing_id, validated)
    return billing


async def _link_delivery_predecessors(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    billing_id: uuid.UUID,
    lines: list[_BillingLineInput],
) -> None:
    """Link each distinct source delivery → billing ('invoiced_by') for the docflow chain (PLAN
    7.4). A billing line may name no delivery (the convenience path / a bill without a named
    shipment) — those are skipped; the order → billing edge is written at POST."""
    from app.modules.sales.models import DeliveryLine

    linked: set[uuid.UUID] = set()
    billing = await session.get(SalesBilling, billing_id)
    for line in lines:
        if line.delivery_line_id is None:
            continue
        dl = await session.get(DeliveryLine, line.delivery_line_id)
        if dl is None or dl.tenant_id != tenant_id or dl.delivery_id in linked:
            continue
        from app.modules.sales.models import Delivery

        delivery = await session.get(Delivery, dl.delivery_id)
        if delivery is not None and billing is not None:
            await docflow.link_documents(
                session,
                tenant_id,
                predecessor=delivery.document_id,
                successor=billing.document_id,
                link_type=DELIVERY_INVOICED_BY_BILLING_LINK,
            )
            linked.add(dl.delivery_id)


async def cancel_billing(
    session: AsyncSession, tenant_id: uuid.UUID, billing_id: uuid.UUID
) -> SalesBilling:
    """Cancel a DRAFT billing (PLAN 7.4). A POSTED billing is TERMINAL — it triggered an AR invoice
    (recognized revenue + AR), so it is corrected by a return / credit note (7.4), never cancelled.
    Cancelling a DRAFT raises no invoice and changes no invoiced_quantity."""
    billing = await get_billing(session, tenant_id, billing_id)
    if BillingStatus(billing.status) != BillingStatus.DRAFT:
        raise ConflictError(
            message=f"A {billing.status} billing cannot be cancelled",
            code="sales.billing_not_cancellable",
            details={"billing_id": str(billing_id), "status": billing.status},
        )
    billing.status = BillingStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, billing.document_id, status=BillingStatus.CANCELLED.value
    )
    return billing

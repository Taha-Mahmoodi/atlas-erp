"""Outbound-delivery create / cancel (PLAN 7.3, D-045): create a DRAFT against a sales order, cancel
a DRAFT. The POST path (the heart) + its post-only helpers live in ``delivery_post.py`` and the
reads in ``delivery_reads.py`` (split at the 400-line cap, STRUCTURE §8.4); the package ``__init__``
re-exports all three halves as one ``service`` surface.

A delivery records the physical shipment of order goods — the OUTBOUND TWIN of the procurement goods
receipt (service/goods_receipts.py, mirrored). ``create_delivery`` writes a DRAFT (validates the
order is deliverable, each line belongs to it, the shipped quantity is within the open-to-deliver
quantity, the bin checks out and the source bin holds enough stock) and claims the DN number at
creation (D-040). No stock moves yet — that is POST (``delivery_post.post_delivery``).

Cross-module rule (STRUCTURE §5 / D-045): sales NEVER calls inventory's service — the stock effect
goes through the event bus. Sales reads bins / on-hand via inventory/queries (downward reads),
updates its OWN order/delivery rows, and lets inventory's handler own the ISSUE moves.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.inventory import queries as inventory_queries
from app.modules.sales.constants import (
    DELIVERY_DOC_TYPE,
    DELIVERY_NUMBER_PADDING,
    DELIVERY_NUMBER_PREFIX,
    DELIVERY_SEQUENCE_NAME,
    DeliveryStatus,
    SalesOrderStatus,
)
from app.modules.sales.models import Delivery, DeliveryLine, SalesOrder, SalesOrderLine
from app.modules.sales.schemas import DeliveryCreate
from app.modules.sales.service._shared import claim_document_number
from app.modules.sales.service.delivery_reads import get_delivery
from app.modules.sales.service.orders import get_sales_order_lines

# A sales order is deliverable once CONFIRMED, or while partially delivered (a follow-up delivery
# completes a backorder). DRAFT / CREDIT_BLOCKED / CANCELLED / fully-DELIVERED / INVOICED / CLOSED
# cannot start a NEW delivery (D-044: only a firm commitment with open undelivered lines ships).
_DELIVERABLE_ORDER_STATUSES = frozenset(
    {
        SalesOrderStatus.CONFIRMED,
        SalesOrderStatus.PARTIALLY_DELIVERED,
    }
)


@dataclass(frozen=True)
class _DeliveryLineInput:
    """One validated delivery line: the order line it ships against, the snapshot item from that
    line, the SOURCE bin, the shipped quantity, and optional lot/serial."""

    sales_order_line_id: uuid.UUID
    item_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    lot_code: str | None
    serial_code: str | None


async def _require_deliverable_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> SalesOrder:
    order = await session.get(SalesOrder, order_id)
    if order is None or order.tenant_id != tenant_id:
        raise ValidationFailedError(
            message="Referenced sales order does not exist",
            code="sales.order_not_found",
            details={"sales_order_id": str(order_id)},
        )
    if SalesOrderStatus(order.status) not in _DELIVERABLE_ORDER_STATUSES:
        raise ValidationFailedError(
            message=f"A {order.status} sales order cannot ship a delivery",
            code="sales.order_not_confirmed",
            details={"sales_order_id": str(order_id), "status": order.status},
        )
    return order


async def _validate_delivery_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    order_lines: dict[uuid.UUID, SalesOrderLine],
    payload_line: object,
) -> _DeliveryLineInput:
    """Validate one delivery line against its order line: the line belongs to the order, the qty is
    > 0 and within the still-open-to-deliver quantity (over-delivery REJECTED 422 in v1), the
    source bin exists in inventory (D-029), and that bin holds enough stock to issue (a clear
    pre-check; the move's InsufficientStock guard is the backstop at post). Snapshots the item from
    the order line."""
    order_line = order_lines.get(payload_line.sales_order_line_id)  # type: ignore[attr-defined]
    if order_line is None:
        raise ValidationFailedError(
            message="The delivery line does not belong to this sales order",
            code="sales.delivery_line_not_on_order",
            details={
                "sales_order_id": str(order_id),
                "sales_order_line_id": str(
                    payload_line.sales_order_line_id  # type: ignore[attr-defined]
                ),
            },
        )
    qty = _validate_quantity(payload_line.quantity)  # type: ignore[attr-defined]
    open_qty = Decimal(str(order_line.ordered_quantity)) - Decimal(
        str(order_line.delivered_quantity)
    )
    if qty > open_qty:
        raise ValidationFailedError(
            message="The shipped quantity exceeds the order line's open-to-deliver quantity",
            code="sales.over_delivery",
            details={
                "sales_order_line_id": str(order_line.id),
                "open_quantity": str(open_qty),
                "quantity": str(qty),
            },
        )
    bin_id = payload_line.bin_id  # type: ignore[attr-defined]
    if not await inventory_queries.bin_exists(session, tenant_id, bin_id):
        raise ValidationFailedError(
            message="The source bin does not exist in inventory",
            code="sales.delivery_bin_not_found",
            details={"bin_id": str(bin_id)},
        )
    available = await inventory_queries.on_hand(
        session, tenant_id, order_line.item_id, bin_id=bin_id
    )
    if Decimal(str(available)) < qty:
        raise ValidationFailedError(
            message="The source bin does not hold enough stock to ship this quantity",
            code="sales.insufficient_stock",
            details={
                "bin_id": str(bin_id),
                "item_id": str(order_line.item_id),
                "on_hand": str(available),
                "quantity": str(qty),
            },
        )
    return _DeliveryLineInput(
        sales_order_line_id=order_line.id,
        item_id=order_line.item_id,
        bin_id=bin_id,
        quantity=qty,
        lot_code=payload_line.lot_code,  # type: ignore[attr-defined]
        serial_code=payload_line.serial_code,  # type: ignore[attr-defined]
    )


def _validate_quantity(quantity: Decimal) -> Decimal:
    qty = Decimal(str(quantity))
    if qty <= 0:
        raise ValidationFailedError(
            message="A delivery line quantity must be greater than zero",
            code="sales.line_quantity_invalid",
            details={"quantity": str(qty)},
        )
    return qty


async def create_delivery(
    session: AsyncSession, tenant_id: uuid.UUID, payload: DeliveryCreate
) -> Delivery:
    """Create a DRAFT delivery against a sales order (PLAN 7.3). Validates the order is deliverable
    (CONFIRMED / PARTIALLY_DELIVERED → else 422 sales.order_not_confirmed), each line belongs to it,
    the quantity is within the open-to-deliver quantity (over-delivery → 422 sales.over_delivery),
    the source bin exists, and that bin holds enough stock (422 sales.insufficient_stock). Snapshots
    the customer from the order + per-line item from the order line and claims the DN number at
    creation (D-040). No stock moves yet — that is POST."""
    if not payload.lines:
        raise ValidationFailedError(
            message="A delivery needs at least one line",
            code="sales.delivery_no_lines",
        )
    order = await _require_deliverable_order(session, tenant_id, payload.sales_order_id)
    order_lines = {
        line.id: line for line in await get_sales_order_lines(session, tenant_id, order.id)
    }
    delivery_date = payload.delivery_date or date.today()

    validated = [
        await _validate_delivery_line(session, tenant_id, order.id, order_lines, line)
        for line in payload.lines
    ]

    delivery_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        DELIVERY_DOC_TYPE,
        delivery_id,
        doc_number=None,
        status=DeliveryStatus.DRAFT.value,
    )
    number = await claim_document_number(
        session,
        tenant_id,
        sequence_name=DELIVERY_SEQUENCE_NAME,
        prefix=DELIVERY_NUMBER_PREFIX,
        padding=DELIVERY_NUMBER_PADDING,
        on_date=delivery_date,
    )

    delivery = Delivery(
        id=delivery_id,
        tenant_id=tenant_id,
        document_id=document.id,
        delivery_number=number,
        status=DeliveryStatus.DRAFT.value,
        sales_order_id=order.id,
        customer_id=order.customer_id,
        warehouse_id=payload.warehouse_id,
        delivery_date=delivery_date,
        shipping_address=payload.shipping_address,
        notes=payload.notes,
    )
    session.add(delivery)
    for index, line in enumerate(validated, start=1):
        session.add(
            DeliveryLine(
                tenant_id=tenant_id,
                delivery_id=delivery_id,
                line_number=index,
                sales_order_line_id=line.sales_order_line_id,
                item_id=line.item_id,
                bin_id=line.bin_id,
                quantity=line.quantity,
                lot_code=line.lot_code,
                serial_code=line.serial_code,
            )
        )
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=number, status=DeliveryStatus.DRAFT.value
    )
    return delivery


async def cancel_delivery(
    session: AsyncSession, tenant_id: uuid.UUID, delivery_id: uuid.UUID
) -> Delivery:
    """Cancel a DRAFT delivery (PLAN 7.3). A POSTED delivery is TERMINAL — it has issued stock and
    posted COGS, so it is corrected by a return / RMA (7.4), never cancelled (v1 has no reverse-
    delivery; documented). Cancelling a DRAFT moves nothing."""
    delivery = await get_delivery(session, tenant_id, delivery_id)
    if DeliveryStatus(delivery.status) != DeliveryStatus.DRAFT:
        raise ConflictError(
            message=f"A {delivery.status} delivery cannot be cancelled",
            code="sales.delivery_not_cancellable",
            details={"delivery_id": str(delivery_id), "status": delivery.status},
        )
    delivery.status = DeliveryStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, delivery.document_id, status=DeliveryStatus.CANCELLED.value
    )
    return delivery

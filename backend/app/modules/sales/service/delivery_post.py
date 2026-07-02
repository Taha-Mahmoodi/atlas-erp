"""Outbound-delivery POST (PLAN 7.3, D-045) — the heart — split from ``deliveries.py`` at the
400-line cap (STRUCTURE §8.4, the goods_receipts / invoice_match_post precedent). The DRAFT create +
its validation helpers + ``cancel_delivery`` stay in ``deliveries.py``; the post path + the
post-only tracking/status helpers live here. ``__init__`` re-exports both halves as one ``service``
surface (``service.post_delivery`` unchanged).

``post_delivery`` is the heart: in ONE transaction it PUBLISHES ``DeliveryShipped`` — inventory's
handler creates the stock ISSUE moves (Dr COGS / Cr Inventory via the costing event) — raises each
order line's delivered_quantity, advances the order status (PARTIALLY_DELIVERED / DELIVERED), links
docflow order→delivery, and sets the delivery POSTED. A closed delivery period trips a move's
journal trigger and rolls the WHOLE post back; insufficient stock at a bin rolls it ALL back.

Why NO valuation-offset override (vs 6.3's GR/IR override): an ISSUE move's DEFAULT offset is the
item-category COGS account (the costing engine routes an ISSUE to COGS), so a delivery posts Dr COGS
/ Cr Inventory with no account on the event — COGS *is* the issue offset (D-045/D-020).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.inventory import queries as inventory_queries
from app.modules.sales.constants import (
    ORDER_DELIVERED_BY_DELIVERY_LINK,
    DeliveryStatus,
    SalesOrderStatus,
)
from app.modules.sales.events import DeliveryMove, DeliveryShipped
from app.modules.sales.models import Delivery, DeliveryLine, SalesOrder
from app.modules.sales.service.delivery_reads import get_delivery, get_delivery_lines
from app.modules.sales.service.orders import get_sales_order, get_sales_order_lines


async def post_delivery(
    session: AsyncSession, tenant_id: uuid.UUID, delivery_id: uuid.UUID
) -> Delivery:
    """Post a DRAFT delivery (PLAN 7.3, D-045) — the heart. In ONE transaction: PUBLISH
    ``DeliveryShipped`` so inventory's handler creates the stock ISSUE moves (Dr COGS / Cr
    Inventory, COGS being the default ISSUE offset — no override) and finance posts the journals;
    raise each order line's delivered_quantity; advance the order status (PARTIALLY_DELIVERED /
    DELIVERED); link docflow order→delivery; set the delivery POSTED — all here, before commit
    (D-011). A closed delivery period trips a move's COGS-journal trigger and rolls it ALL back;
    insufficient stock at a bin rolls it ALL back.

    Idempotent re-post is rejected (a POSTED delivery is terminal — corrected by a return / RMA,
    7.4). The caller commits via uow; the published event is drained in that same uow."""
    delivery = await get_delivery(session, tenant_id, delivery_id)
    status = DeliveryStatus(delivery.status)
    if status == DeliveryStatus.POSTED:
        raise ConflictError(
            message="The delivery is already posted",
            code="sales.delivery_already_posted",
            details={"delivery_id": str(delivery_id)},
        )
    if status != DeliveryStatus.DRAFT:
        raise ConflictError(
            message=f"A {delivery.status} delivery cannot be posted",
            code="sales.delivery_not_postable",
            details={"delivery_id": str(delivery_id), "status": delivery.status},
        )

    lines = await get_delivery_lines(session, tenant_id, delivery_id)
    order_lines = {
        line.id: line
        for line in await get_sales_order_lines(session, tenant_id, delivery.sales_order_id)
    }

    moves: list[DeliveryMove] = []
    for line in lines:
        order_line = order_lines[line.sales_order_line_id]
        new_delivered = Decimal(str(order_line.delivered_quantity)) + Decimal(
            str(line.quantity)
        )
        # #75: the create-path check reads the persisted column, which another document may
        # have raised since this DRAFT was created — re-check the cap at post time.
        if new_delivered > Decimal(str(order_line.ordered_quantity)):
            raise ValidationFailedError(
                message="Posting this delivery would exceed the order line's ordered quantity",
                code="sales.over_delivery",
                details={
                    "sales_order_line_id": str(order_line.id),
                    "ordered_quantity": str(order_line.ordered_quantity),
                    "delivered_quantity": str(order_line.delivered_quantity),
                    "quantity": str(line.quantity),
                },
            )
        order_line.delivered_quantity = new_delivered
        # An ISSUE references an EXISTING lot/serial BY ID (it creates none), so resolve the line's
        # human lot/serial code to the inventory id through inventory/queries (D-029) — the move
        # would otherwise reject a code on an outbound issue. A tracked line with no resolvable
        # lot/serial fails loud here, rolling the post back.
        lot_id, serial_id = await _resolve_tracking_ids(session, tenant_id, line)
        moves.append(
            DeliveryMove(
                item_id=line.item_id,
                bin_id=line.bin_id,
                quantity=Decimal(str(line.quantity)),
                lot_id=lot_id,
                serial_id=serial_id,
            )
        )

    await _advance_order_status(
        session, tenant_id, delivery.sales_order_id, order_lines.values()
    )

    delivery.status = DeliveryStatus.POSTED.value
    delivery.posted_at = datetime.now()
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, delivery.document_id, status=DeliveryStatus.POSTED.value
    )
    # Link order document → delivery document ('delivered_by') for the docflow chain (the delivery→
    # move edges are written by inventory's handler when it creates the moves — D-045).
    order = await session.get(SalesOrder, delivery.sales_order_id)
    if order is not None:
        await docflow.link_documents(
            session,
            tenant_id,
            predecessor=order.document_id,
            successor=delivery.document_id,
            link_type=ORDER_DELIVERED_BY_DELIVERY_LINK,
        )

    # Publish AFTER sales' own writes settle: inventory's handler creates the ISSUE moves (COGS the
    # default offset) and finance posts the COGS journals, all drained in this same uow
    # (D-011/D-045).
    publish(
        session,
        DeliveryShipped(
            tenant_id=tenant_id,
            delivery_id=delivery.id,
            delivery_number=delivery.delivery_number,
            document_id=delivery.document_id,
            warehouse_id=delivery.warehouse_id,
            move_date=delivery.delivery_date.isoformat(),
            moves=tuple(moves),
        ),
    )
    return delivery


async def _resolve_tracking_ids(
    session: AsyncSession, tenant_id: uuid.UUID, line: DeliveryLine
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Resolve a delivery line's lot/serial CODE to the inventory id an ISSUE move needs (D-045). An
    outbound issue references an existing lot/serial by id (it never creates one), so the code is
    looked up via inventory/queries; a supplied code that does not resolve fails loud (422) so the
    delivery does not post against a non-existent lot/serial. Untracked lines carry no codes ⇒
    (None, None) and the move's tracking validator accepts an item with no lot/serial."""
    lot_id: uuid.UUID | None = None
    serial_id: uuid.UUID | None = None
    if line.lot_code is not None:
        lot_id = await inventory_queries.lot_id_for_code(
            session, tenant_id, line.item_id, line.lot_code
        )
        if lot_id is None:
            raise ValidationFailedError(
                message="The referenced lot does not exist for this item",
                code="sales.delivery_lot_not_found",
                details={"item_id": str(line.item_id), "lot_code": line.lot_code},
            )
    if line.serial_code is not None:
        serial_id = await inventory_queries.serial_id_for_code(
            session, tenant_id, line.item_id, line.serial_code
        )
        if serial_id is None:
            raise ValidationFailedError(
                message="The referenced serial does not exist for this item",
                code="sales.delivery_serial_not_found",
                details={"item_id": str(line.item_id), "serial_code": line.serial_code},
            )
    return lot_id, serial_id


async def _advance_order_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    order_lines,
) -> None:
    """Advance the order status after a delivery raised the lines' delivered_quantity (PLAN 7.3):
    DELIVERED when every line is fully delivered (delivered >= ordered), else PARTIALLY_DELIVERED.
    The order + lines are already loaded/mutated in this session, so this reads the in-memory
    state."""
    fully_delivered = all(
        Decimal(str(line.delivered_quantity)) >= Decimal(str(line.ordered_quantity))
        for line in order_lines
    )
    order = await get_sales_order(session, tenant_id, order_id)
    new_status = (
        SalesOrderStatus.DELIVERED if fully_delivered else SalesOrderStatus.PARTIALLY_DELIVERED
    )
    order.status = new_status.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, order.document_id, status=new_status.value
    )

"""Production-order DRAFT lifecycle (PLAN 8.2, D-048): create+explode, release, cancel + reads.

The issue-to-WIP + finish-to-stock POSTING flows live in ``production_post.py`` (split at the
400-line cap, the sales delivery_post precedent); this file owns the DRAFT side. ``__init__``
re-exports both halves as one ``service`` surface.

Rules enforced here (the service owns them, CLAUDE.md rule 7):

- **create_production_order** — resolves the item's ACTIVE default BOM (or the supplied bom_id),
  EXPLODES its components into ``ProductionOrderComponent`` rows
  (required = quantity_per × order_qty × (1 + scrap_percent/100), quantized to the quantity scale),
  snapshots the active routing's operations into ``ProductionOrderOperation`` rows
  (planned_minutes = setup + run × order_qty), claims the gapless MO- number + registers the
  document, and validates the item is STOCKED, quantity > 0, the warehouse exists. SINGLE-LEVEL
  explosion: a sub-assembly component is itself produced by its OWN order (multi-level via
  references, D-047) — this order issues the sub-assembly as a finished material, it does not
  recurse.
- **release_order** — DRAFT→RELEASED; the component rows ARE the reservation (v1 ATP-style: release
  does NOT block on availability — a shortage is informational, the parity-doc backorder posture).
- **cancel_order** — DRAFT/RELEASED only; once a component is issued the order is POSTED-ish and
  must be FINISHED (issued stock + WIP cannot strand), so an IN_PROGRESS/FINISHED order is not
  cancellable.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.numbering import claim_number, ensure_sequence
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.inventory import queries as inventory_queries
from app.modules.manufacturing import queries as mfg_queries
from app.modules.manufacturing.constants import (
    PRODUCTION_ORDER_DOC_TYPE,
    PRODUCTION_ORDER_NUMBER_PADDING,
    PRODUCTION_ORDER_NUMBER_PREFIX,
    PRODUCTION_ORDER_SEQUENCE_NAME,
    ProductionOrderStatus,
)
from app.modules.manufacturing.models import (
    ProductionOrder,
    ProductionOrderComponent,
    ProductionOrderOperation,
)
from app.modules.manufacturing.schemas import ProductionOrderCreate

# Quantities quantize to the D-015 quantity scale (6 dp) — the explosion's scrap math must not leak
# more precision than the column stores.
_QUANTITY_DP = Decimal(1).scaleb(-6)


def _quantize_qty(value: Decimal) -> Decimal:
    return value.quantize(_QUANTITY_DP, rounding=ROUND_HALF_UP)


async def get_production_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> ProductionOrder:
    order = await session.get(ProductionOrder, order_id)
    if order is None or order.tenant_id != tenant_id:
        raise NotFoundError(
            message="Production order not found",
            code="manufacturing.production_order_not_found",
        )
    return order


async def production_order_components(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> list[ProductionOrderComponent]:
    return await mfg_queries.production_order_components(session, tenant_id, order_id)


async def production_order_operations(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> list[ProductionOrderOperation]:
    stmt = (
        select(ProductionOrderOperation)
        .where(
            ProductionOrderOperation.tenant_id == tenant_id,
            ProductionOrderOperation.production_order_id == order_id,
        )
        .order_by(ProductionOrderOperation.operation_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _require_stocked_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    """The parent item must exist AND be STOCKED — a production order produces stock, so a
    non-stocked item (service/expense) cannot be the parent (D-029, validated via inventory/queries
    so manufacturing never imports inventory models)."""
    item = await inventory_queries.get_item(session, tenant_id, item_id)
    if item is None:
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="manufacturing.item_not_found",
            details={"item_id": str(item_id)},
        )
    if item.item_type != "STOCKED":
        raise ValidationFailedError(
            message="Only a stocked item can be produced by a production order",
            code="manufacturing.item_not_stocked",
            details={"item_id": str(item_id), "item_type": item.item_type},
        )


async def _resolve_bom(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ProductionOrderCreate
):
    """Resolve the BOM to explode: the supplied ``bom_id`` (validated to be for this item) or the
    item's ACTIVE default BOM. 422 ``manufacturing.no_active_bom`` when neither resolves."""
    if payload.bom_id is not None:
        bom = await mfg_queries.get_bom(session, tenant_id, payload.bom_id)
        if bom is None:
            raise ValidationFailedError(
                message="Referenced BOM does not exist",
                code="manufacturing.bom_not_found",
                details={"bom_id": str(payload.bom_id)},
            )
        if bom.item_id != payload.item_id:
            raise ValidationFailedError(
                message="The BOM is for a different item than the order's",
                code="manufacturing.bom_item_mismatch",
                details={"bom_id": str(payload.bom_id), "item_id": str(payload.item_id)},
            )
        return bom
    bom = await mfg_queries.get_active_bom_for_item(session, tenant_id, payload.item_id)
    if bom is None:
        raise ValidationFailedError(
            message="The item has no active default BOM to explode",
            code="manufacturing.no_active_bom",
            details={"item_id": str(payload.item_id)},
        )
    return bom


async def _resolve_routing(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ProductionOrderCreate
):
    """Resolve the routing to snapshot: the supplied ``routing_id`` (validated to be for this item)
    or the item's active default routing. None when the item has no routing (a routingless order is
    allowed — it just snapshots no operations)."""
    if payload.routing_id is not None:
        routing = await mfg_queries.get_routing(session, tenant_id, payload.routing_id)
        if routing is None:
            raise ValidationFailedError(
                message="Referenced routing does not exist",
                code="manufacturing.routing_not_found",
                details={"routing_id": str(payload.routing_id)},
            )
        if routing.item_id != payload.item_id:
            raise ValidationFailedError(
                message="The routing is for a different item than the order's",
                code="manufacturing.routing_item_mismatch",
                details={"routing_id": str(payload.routing_id)},
            )
        return routing
    return await mfg_queries.get_active_routing_for_item(session, tenant_id, payload.item_id)


async def _default_bin(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> uuid.UUID:
    """The default issue bin for the order's warehouse — the component rows pre-fill it so an
    "issue all required" needs no per-line bin. Prefers the warehouse's is_default bin, else any
    bin; 422 when the warehouse has none (a component has nowhere to issue from)."""
    bin_id = await inventory_queries.default_bin_for_warehouse(
        session, tenant_id, warehouse_id
    )
    if bin_id is None:
        raise ValidationFailedError(
            message="The warehouse has no bin to issue components from",
            code="manufacturing.warehouse_no_bin",
            details={"warehouse_id": str(warehouse_id)},
        )
    return bin_id


async def create_production_order(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ProductionOrderCreate
) -> ProductionOrder:
    """Create a DRAFT production order + EXPLODE its BOM into reserved component rows + SNAPSHOT
    its routing (D-048). Validates the parent item is STOCKED, quantity > 0 and the warehouse
    exists; resolves the BOM (active default unless supplied) and explodes required quantities
    (scrap-loaded, quantized); snapshots the routing operations' per-order load; registers the
    document + claims the MO- number. Born DRAFT — release reserves, issue consumes, finish
    produces."""
    quantity = Decimal(payload.quantity)
    if quantity <= 0:
        raise ValidationFailedError(
            message="Production quantity must be greater than zero",
            code="manufacturing.quantity_invalid",
            details={"quantity": str(quantity)},
        )
    await _require_stocked_item(session, tenant_id, payload.item_id)
    bom = await _resolve_bom(session, tenant_id, payload)
    routing = await _resolve_routing(session, tenant_id, payload)
    default_bin = await _default_bin(session, tenant_id, payload.warehouse_id)
    components = await mfg_queries.bom_components(session, tenant_id, bom.id)
    if not components:
        raise ValidationFailedError(
            message="The BOM has no components to explode",
            code="manufacturing.bom_no_components",
            details={"bom_id": str(bom.id)},
        )

    order_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        PRODUCTION_ORDER_DOC_TYPE,
        order_id,
        doc_number=None,
        status=ProductionOrderStatus.DRAFT.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        PRODUCTION_ORDER_SEQUENCE_NAME,
        PRODUCTION_ORDER_NUMBER_PREFIX,
        PRODUCTION_ORDER_NUMBER_PADDING,
        year_reset=True,
    )
    number = await claim_number(
        session, tenant_id, PRODUCTION_ORDER_SEQUENCE_NAME, on_date=date.today()
    )

    order = ProductionOrder(
        id=order_id,
        tenant_id=tenant_id,
        document_id=document.id,
        order_number=number,
        status=ProductionOrderStatus.DRAFT.value,
        item_id=payload.item_id,
        quantity=quantity,
        bom_id=bom.id,
        routing_id=routing.id if routing is not None else None,
        warehouse_id=payload.warehouse_id,
        planned_start_date=payload.planned_start_date,
        planned_end_date=payload.planned_end_date,
        finished_quantity=Decimal(0),
        accumulated_wip_cost=Decimal(0),
        notes=payload.notes,
    )
    session.add(order)
    # The explosion factor scales component quantity_per (per the BOM's base_quantity) up to the
    # order quantity, then scrap loads each line. SINGLE-LEVEL: each direct component becomes one
    # reservation row — a sub-assembly is produced by its own order, this order consumes it as-is.
    base_quantity = Decimal(bom.base_quantity)
    for index, component in enumerate(components, start=1):
        scrap_factor = Decimal(1) + (Decimal(component.scrap_percent) / Decimal(100))
        required = _quantize_qty(
            (Decimal(component.quantity_per) * quantity / base_quantity) * scrap_factor
        )
        session.add(
            ProductionOrderComponent(
                tenant_id=tenant_id,
                production_order_id=order_id,
                line_number=index * 10,
                component_item_id=component.component_item_id,
                required_quantity=required,
                issued_quantity=Decimal(0),
                uom_id=component.uom_id,
                bin_id=default_bin,
            )
        )

    if routing is not None:
        operations = await mfg_queries.routing_operations(session, tenant_id, routing.id)
        for operation in operations:
            planned = _quantize_qty(
                Decimal(operation.setup_time_minutes)
                + Decimal(operation.run_time_minutes_per_unit) * quantity
            )
            session.add(
                ProductionOrderOperation(
                    tenant_id=tenant_id,
                    production_order_id=order_id,
                    operation_number=operation.operation_number,
                    work_center_id=operation.work_center_id,
                    description=operation.description,
                    setup_time_minutes=Decimal(operation.setup_time_minutes),
                    run_time_minutes_per_unit=Decimal(operation.run_time_minutes_per_unit),
                    planned_minutes=planned,
                )
            )

    await session.flush()
    await docflow.set_document_status(
        session,
        tenant_id,
        document.id,
        doc_number=number,
        status=ProductionOrderStatus.DRAFT.value,
    )
    return order


async def release_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> ProductionOrder:
    """Release a DRAFT production order (D-048): DRAFT→RELEASED, materials reserved (the component
    rows ARE the reservation). Idempotent on an already-RELEASED order. The reservation does NOT
    block on availability — a shortage is informational (v1 ATP-style, the parity-doc backorder
    posture); a later phase can flag shortages without changing this transition. An IN_PROGRESS /
    FINISHED / CANCELLED order cannot be released."""
    order = await get_production_order(session, tenant_id, order_id)
    status = ProductionOrderStatus(order.status)
    if status == ProductionOrderStatus.RELEASED:
        return order
    if status != ProductionOrderStatus.DRAFT:
        raise ConflictError(
            message=f"A {order.status} production order cannot be released",
            code="manufacturing.production_order_not_releasable",
            details={"order_id": str(order_id), "status": order.status},
        )
    order.status = ProductionOrderStatus.RELEASED.value
    order.released_at = datetime.now()
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, order.document_id, status=ProductionOrderStatus.RELEASED.value
    )
    return order


async def cancel_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> ProductionOrder:
    """Cancel a DRAFT or RELEASED production order (D-048). Once a component has been issued the
    order is IN_PROGRESS — POSTED-ish: it has consumed stock to WIP, so it must be FINISHED (issued
    stock + WIP cannot strand; v1 has no reverse-issue), never cancelled. A FINISHED/CANCELLED order
    is terminal. Cancelling releases nothing physical (no component was issued)."""
    order = await get_production_order(session, tenant_id, order_id)
    status = ProductionOrderStatus(order.status)
    if status not in (ProductionOrderStatus.DRAFT, ProductionOrderStatus.RELEASED):
        raise ConflictError(
            message=f"A {order.status} production order cannot be cancelled",
            code="manufacturing.production_order_not_cancellable",
            details={"order_id": str(order_id), "status": order.status},
        )
    order.status = ProductionOrderStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, order.document_id, status=ProductionOrderStatus.CANCELLED.value
    )
    return order


async def list_production_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID | None = None,
    status: ProductionOrderStatus | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[ProductionOrder]:
    """Keyset-paginated production orders ordered by order_number (D-014). The item/status filters
    narrow the set (index-served by (tenant, status) / (tenant, item_id)) and fold into the cursor
    fingerprint."""
    stmt = select(ProductionOrder).where(ProductionOrder.tenant_id == tenant_id)
    if item_id is not None:
        stmt = stmt.where(ProductionOrder.item_id == item_id)
    if status is not None:
        stmt = stmt.where(ProductionOrder.status == status.value)
    fingerprint = filter_fingerprint(item_id, status)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(ProductionOrder.order_number, SortDirection.ASC)],
        pk=ProductionOrder.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )

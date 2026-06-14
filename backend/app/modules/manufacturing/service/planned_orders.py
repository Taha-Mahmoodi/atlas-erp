"""Planned-order lifecycle (PLAN 8.3, D-049): firm, convert (→ production order / requisition),
cancel + the run / planned-order / capacity reads.

A PLANNED ORDER is the MRP run's net proposal. A planner FIRMS it (a re-run keeps it + nets it as
supply), CONVERTS it into a real document, or CANCELS it:

- **firm_planned_order** — PLANNED → FIRMED. A re-run no longer supersedes it (it survives and nets
  as supply via ``planned_make_supply``). Idempotent on an already-FIRMED order.
- **convert_planned_order** — PLANNED/FIRMED → CONVERTED. A MAKE order creates a real PRODUCTION
  ORDER (``create_production_order``, intra-module — manufacturing's own service); a BUY order
  PUBLISHES ``PlannedBuyConverted`` so procurement's handler creates a DRAFT requisition (the
  §5-clean cross-module mechanism, D-049). The run document → 'planned_to' → the created document is
  the docflow link. ``converted_document_id`` is recorded for MAKE (the production order's document,
  available intra-module); for BUY the docflow 'planned_to' edge from the run document is the
  converted link (the billing→invoice precedent — the requisition is procurement-owned, created
  cross-module). Idempotent on an already-CONVERTED order.
- **cancel_planned_order** — PLANNED/FIRMED → CANCELLED. The row survives (history) but adds no
  supply. Idempotent on an already-CANCELLED order. A CONVERTED order cannot be cancelled (the real
  document exists).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.manufacturing import queries as mfg_queries
from app.modules.manufacturing.constants import (
    PLANNED_ORDER_CONVERTED_LINK,
    MrpRunStatus,
    PlannedOrderStatus,
    PlannedOrderType,
)
from app.modules.manufacturing.events import PlannedBuyConverted
from app.modules.manufacturing.models import CapacityLoad, MrpRun, PlannedOrder
from app.modules.manufacturing.schemas import ProductionOrderCreate
from app.modules.manufacturing.service.mrp_capacity import capacity_for_run as _capacity_read
from app.modules.manufacturing.service.production_orders import create_production_order


async def get_mrp_run(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> MrpRun:
    run = await mfg_queries.get_mrp_run(session, tenant_id, run_id)
    if run is None:
        raise NotFoundError(message="MRP run not found", code="manufacturing.mrp_run_not_found")
    return run


async def get_planned_order(
    session: AsyncSession, tenant_id: uuid.UUID, planned_order_id: uuid.UUID
) -> PlannedOrder:
    order = await session.get(PlannedOrder, planned_order_id)
    if order is None or order.tenant_id != tenant_id:
        raise NotFoundError(
            message="Planned order not found", code="manufacturing.planned_order_not_found"
        )
    return order


async def list_mrp_runs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: MrpRunStatus | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[MrpRun]:
    """Keyset-paginated MRP runs, newest run_number first (D-014)."""
    stmt = select(MrpRun).where(MrpRun.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(MrpRun.status == status.value)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(MrpRun.run_number, SortDirection.DESC)],
        pk=MrpRun.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status),
    )


async def planned_orders_for_run(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    order_type: PlannedOrderType | None = None,
    status: PlannedOrderStatus | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[PlannedOrder]:
    """Keyset-paginated planned orders for a run, ordered by (level, id) so finished goods precede
    components (D-014). The type/status filters fold into the cursor fingerprint."""
    stmt = select(PlannedOrder).where(
        PlannedOrder.tenant_id == tenant_id, PlannedOrder.mrp_run_id == run_id
    )
    if order_type is not None:
        stmt = stmt.where(PlannedOrder.order_type == order_type.value)
    if status is not None:
        stmt = stmt.where(PlannedOrder.status == status.value)
    return await paginate(
        session,
        stmt,
        order_by=[
            OrderKey(PlannedOrder.level, SortDirection.ASC),
            OrderKey(PlannedOrder.item_id, SortDirection.ASC),
        ],
        pk=PlannedOrder.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(order_type, status),
    )


async def capacity_for_run(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> list[CapacityLoad]:
    """The run's rough-capacity loads, overloaded first (PLAN 8.3) — a thin pass-through to the
    capacity service read so the router imports one ``service`` surface."""
    return await _capacity_read(session, tenant_id, run_id)


async def firm_planned_order(
    session: AsyncSession, tenant_id: uuid.UUID, planned_order_id: uuid.UUID
) -> PlannedOrder:
    """FIRM a planned order (PLAN 8.3): PLANNED → FIRMED. A FIRMED order survives a re-run and nets
    as supply. Idempotent on FIRMED; a CONVERTED/CANCELLED order cannot be firmed."""
    order = await get_planned_order(session, tenant_id, planned_order_id)
    status = PlannedOrderStatus(order.status)
    if status == PlannedOrderStatus.FIRMED:
        return order
    if status != PlannedOrderStatus.PLANNED:
        raise ConflictError(
            message=f"A {order.status} planned order cannot be firmed",
            code="manufacturing.planned_order_not_firmable",
            details={"planned_order_id": str(planned_order_id), "status": order.status},
        )
    order.status = PlannedOrderStatus.FIRMED.value
    await session.flush()
    return order


async def cancel_planned_order(
    session: AsyncSession, tenant_id: uuid.UUID, planned_order_id: uuid.UUID
) -> PlannedOrder:
    """CANCEL a planned order (PLAN 8.3): PLANNED/FIRMED → CANCELLED. The row survives but adds no
    supply. Idempotent on CANCELLED; a CONVERTED order (a real document exists) cannot be
    cancelled."""
    order = await get_planned_order(session, tenant_id, planned_order_id)
    status = PlannedOrderStatus(order.status)
    if status == PlannedOrderStatus.CANCELLED:
        return order
    if status == PlannedOrderStatus.CONVERTED:
        raise ConflictError(
            message="A converted planned order cannot be cancelled",
            code="manufacturing.planned_order_not_cancellable",
            details={"planned_order_id": str(planned_order_id), "status": order.status},
        )
    order.status = PlannedOrderStatus.CANCELLED.value
    await session.flush()
    return order


async def convert_planned_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    planned_order_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID | None = None,
) -> PlannedOrder:
    """CONVERT a planned order to a real document (PLAN 8.3, D-049): PLANNED/FIRMED → CONVERTED. A
    MAKE order creates a PRODUCTION ORDER (intra-module); a BUY order publishes
    ``PlannedBuyConverted`` so procurement creates a requisition (the §5-clean mechanism). Records
    ``converted_document_id`` (MAKE: the production order's document; BUY: the docflow 'planned_to'
    edge from the run is the link). Idempotent on an already-CONVERTED order."""
    order = await get_planned_order(session, tenant_id, planned_order_id)
    status = PlannedOrderStatus(order.status)
    if status == PlannedOrderStatus.CONVERTED:
        return order
    if status not in (PlannedOrderStatus.PLANNED, PlannedOrderStatus.FIRMED):
        raise ConflictError(
            message=f"A {order.status} planned order cannot be converted",
            code="manufacturing.planned_order_not_convertible",
            details={"planned_order_id": str(planned_order_id), "status": order.status},
        )
    run = await get_mrp_run(session, tenant_id, order.mrp_run_id)
    if order.order_type == PlannedOrderType.MAKE.value:
        await _convert_make(session, tenant_id, order, run, warehouse_id)
    else:
        await _convert_buy(session, tenant_id, order, run)
    order.status = PlannedOrderStatus.CONVERTED.value
    await session.flush()
    return order


async def _convert_make(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: PlannedOrder,
    run: MrpRun,
    warehouse_id: uuid.UUID | None,
) -> None:
    """MAKE conversion: create a real production order for the net quantity (intra-module). The
    warehouse is the caller's (or the run's scope); 422 when none can be resolved (a production
    order must issue/finish somewhere)."""
    target_warehouse = warehouse_id or run.warehouse_id
    if target_warehouse is None:
        raise ValidationFailedError(
            message="A warehouse is required to convert a MAKE planned order",
            code="manufacturing.planned_order_warehouse_required",
            details={"planned_order_id": str(order.id)},
        )
    production_order = await create_production_order(
        session,
        tenant_id,
        ProductionOrderCreate(
            item_id=order.item_id,
            quantity=Decimal(str(order.quantity)),
            warehouse_id=target_warehouse,
            notes=f"Converted from MRP run {run.run_number}",
        ),
    )
    order.converted_document_id = production_order.document_id
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=run.document_id,
        successor=production_order.document_id,
        link_type=PLANNED_ORDER_CONVERTED_LINK,
    )


async def _convert_buy(
    session: AsyncSession, tenant_id: uuid.UUID, order: PlannedOrder, run: MrpRun
) -> None:
    """BUY conversion (D-049): publish ``PlannedBuyConverted`` so procurement's handler creates the
    DRAFT requisition in this same transaction (the §5-clean mechanism). Resolves the item's base
    UoM (inventory/queries) + the tenant functional currency (finance/queries) downward — the
    reorder scan's defaults — before publishing. The docflow run → 'planned_to' → requisition (the
    handler writes it) is the converted link."""
    base_uom_id = await inventory_queries.get_base_uom(session, tenant_id, order.item_id)
    if base_uom_id is None:
        raise ValidationFailedError(
            message="The planned item has no base UoM to build a requisition line",
            code="manufacturing.planned_order_no_base_uom",
            details={"item_id": str(order.item_id)},
        )
    currency_code = (
        await finance_queries.functional_currency_or_none(session, tenant_id) or "USD"
    )
    publish(
        session,
        PlannedBuyConverted(
            tenant_id=tenant_id,
            run_document_id=run.document_id,
            item_id=order.item_id,
            uom_id=base_uom_id,
            quantity=Decimal(str(order.quantity)),
            currency_code=currency_code,
            description=f"MRP planned buy (run {run.run_number})",
        ),
    )

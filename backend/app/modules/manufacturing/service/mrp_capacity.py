"""The rough capacity check (PLAN 8.3, D-049, parity capacity = PARTIAL: evaluation only).

For an MRP run's planned MAKE orders PLUS the tenant's open production orders, this sums each work
centre's operation LOAD (minutes) and compares it to the work centre's AVAILABLE minutes over the
planning horizon, writing one ``CapacityLoad`` row per loaded work centre and flagging the
overloaded ones. NO leveling / finite scheduling — a rough infinite-capacity load picture only.

LOAD (minutes) per work centre:
- **Planned MAKE orders** — each planned MAKE order's item resolves its ACTIVE default routing; each
  operation contributes ``setup_time_minutes + run_time_minutes_per_unit × planned_quantity``
  (the create_production_order load math, applied to the planned quantity).
- **Open production orders** — each open order's snapshot operations already carry a precomputed
  ``planned_minutes`` (setup + run × order qty); summed per work centre directly.

AVAILABLE (minutes) per work centre = ``capacity_hours_per_day × (efficiency_percent/100) ×
horizon_days × 60``. ``utilization_percent`` = load / available × 100 (0 when available is 0);
``is_overloaded`` = load > available.

SET-BASED (PERFORMANCE §2): the planned MAKE orders' routings are batched (one query for the active
routings, one for their operations); the open production orders' operation minutes are aggregated in
ONE grouped query; the work centres are read in ONE query. No per-order N+1.
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.manufacturing.constants import (
    PlannedOrderStatus,
    PlannedOrderType,
    ProductionOrderStatus,
    RoutingStatus,
)
from app.modules.manufacturing.models import (
    CapacityLoad,
    PlannedOrder,
    ProductionOrder,
    ProductionOrderOperation,
    Routing,
    RoutingOperation,
    WorkCenter,
)

_QUANTITY_DP = Decimal(1).scaleb(-6)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTITY_DP, rounding=ROUND_HALF_UP)


async def _planned_make_load(
    session: AsyncSession, tenant_id: uuid.UUID, mrp_run_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Per-work-centre minutes from a run's planned MAKE orders (module docstring). Batches the
    planned MAKE orders, their items' ACTIVE routings (one query) and those routings' operations
    (one query), then loads ``setup + run × planned_qty`` per operation. ``{work_center_id:
    minutes}``."""
    planned = (
        await session.execute(
            select(PlannedOrder.item_id, PlannedOrder.quantity).where(
                PlannedOrder.tenant_id == tenant_id,
                PlannedOrder.mrp_run_id == mrp_run_id,
                PlannedOrder.order_type == PlannedOrderType.MAKE.value,
                PlannedOrder.status == PlannedOrderStatus.PLANNED.value,
            )
        )
    ).all()
    if not planned:
        return {}
    # An item may be planned at one level only, but sum defensively per item.
    qty_by_item: dict[uuid.UUID, Decimal] = {}
    for item_id, qty in planned:
        qty_by_item[item_id] = qty_by_item.get(item_id, Decimal(0)) + Decimal(str(qty))

    routings = (
        await session.execute(
            select(Routing).where(
                Routing.tenant_id == tenant_id,
                Routing.item_id.in_(list(qty_by_item)),
                Routing.status == RoutingStatus.ACTIVE.value,
                Routing.is_default.is_(True),
            )
        )
    ).scalars().all()
    routing_to_item = {routing.id: routing.item_id for routing in routings}
    if not routing_to_item:
        return {}
    operations = (
        await session.execute(
            select(RoutingOperation).where(
                RoutingOperation.tenant_id == tenant_id,
                RoutingOperation.routing_id.in_(list(routing_to_item)),
            )
        )
    ).scalars().all()

    load: dict[uuid.UUID, Decimal] = {}
    for operation in operations:
        item_id = routing_to_item[operation.routing_id]
        quantity = qty_by_item[item_id]
        minutes = _quantize(
            Decimal(str(operation.setup_time_minutes))
            + Decimal(str(operation.run_time_minutes_per_unit)) * quantity
        )
        load[operation.work_center_id] = load.get(operation.work_center_id, Decimal(0)) + minutes
    return load


async def _open_order_load(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Per-work-centre minutes from the tenant's OPEN production orders (module docstring): the
    precomputed ``planned_minutes`` on each open order's snapshot operations, aggregated in ONE
    grouped query (no per-order N+1)."""
    open_statuses = (
        ProductionOrderStatus.DRAFT.value,
        ProductionOrderStatus.RELEASED.value,
        ProductionOrderStatus.IN_PROGRESS.value,
    )
    rows = (
        await session.execute(
            select(
                ProductionOrderOperation.work_center_id,
                func.coalesce(func.sum(ProductionOrderOperation.planned_minutes), 0),
            )
            .join(
                ProductionOrder,
                (ProductionOrderOperation.tenant_id == ProductionOrder.tenant_id)
                & (ProductionOrderOperation.production_order_id == ProductionOrder.id),
            )
            .where(
                ProductionOrderOperation.tenant_id == tenant_id,
                ProductionOrder.status.in_(open_statuses),
            )
            .group_by(ProductionOrderOperation.work_center_id)
        )
    ).all()
    return {work_center_id: Decimal(str(minutes)) for work_center_id, minutes in rows}


async def rough_capacity_check(
    session: AsyncSession, tenant_id: uuid.UUID, mrp_run_id: uuid.UUID, horizon_days: int
) -> list[CapacityLoad]:
    """Write the run's rough capacity loads (module docstring). Sums planned-MAKE + open-order load
    per work centre, compares to available minutes over ``horizon_days``, and bulk-inserts one
    ``CapacityLoad`` per LOADED work centre with the overloaded flag. Returns the rows. Set-based;
    the work centres are read once. Caller commits via uow (D-011)."""
    planned_load = await _planned_make_load(session, tenant_id, mrp_run_id)
    open_load = await _open_order_load(session, tenant_id)
    total_load: dict[uuid.UUID, Decimal] = dict(planned_load)
    for work_center_id, minutes in open_load.items():
        total_load[work_center_id] = total_load.get(work_center_id, Decimal(0)) + minutes
    if not total_load:
        return []

    centres = (
        await session.execute(
            select(WorkCenter).where(
                WorkCenter.tenant_id == tenant_id,
                WorkCenter.id.in_(list(total_load)),
            )
        )
    ).scalars().all()
    centre_by_id = {centre.id: centre for centre in centres}

    rows: list[CapacityLoad] = []
    for work_center_id, load_minutes in total_load.items():
        centre = centre_by_id.get(work_center_id)
        if centre is None:
            continue
        available = _quantize(
            Decimal(str(centre.capacity_hours_per_day))
            * (Decimal(str(centre.efficiency_percent)) / Decimal(100))
            * Decimal(horizon_days)
            * Decimal(60)
        )
        utilization = (
            _quantize(load_minutes / available * Decimal(100)) if available > 0 else Decimal(0)
        )
        row = CapacityLoad(
            tenant_id=tenant_id,
            mrp_run_id=mrp_run_id,
            work_center_id=work_center_id,
            planned_load_minutes=_quantize(load_minutes),
            available_minutes=available,
            utilization_percent=utilization,
            is_overloaded=load_minutes > available,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def capacity_for_run(
    session: AsyncSession, tenant_id: uuid.UUID, mrp_run_id: uuid.UUID
) -> list[CapacityLoad]:
    """A run's capacity-load rows, overloaded ones first then by utilisation (PLAN 8.3) — the
    capacity read the API exposes. One indexed read by (tenant, mrp_run_id)."""
    stmt = (
        select(CapacityLoad)
        .where(CapacityLoad.tenant_id == tenant_id, CapacityLoad.mrp_run_id == mrp_run_id)
        .order_by(CapacityLoad.is_overloaded.desc(), CapacityLoad.utilization_percent.desc())
    )
    return list((await session.execute(stmt)).scalars().all())

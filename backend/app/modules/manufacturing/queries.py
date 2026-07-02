"""Manufacturing's cross-module read interface (STRUCTURE §5).

Manufacturing sits above inventory/procurement/sales in the dependency order. PLAN 8.2 (production
orders) and 8.3 (MRP + rough capacity) read THIS file to resolve an item's active BOM/routing and a
work centre's capacity; it is the ONLY manufacturing file those flows import. Keep it thin and
stable — it is a contract.

The "active" resolvers return the ACTIVE + ``is_default`` version of a BOM/routing for an item (the
one the service guarantees is unique per item). ``bom_components`` / ``routing_operations`` return
the lines an exploder/scheduler walks. Every function takes an explicit ``tenant_id`` and runs under
the caller's tenant context, so the D-007 filter applies on top — ordinary tenant-scoped reads.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.manufacturing.constants import (
    BomStatus,
    PlannedOrderStatus,
    ProductionOrderStatus,
    RoutingStatus,
)
from app.modules.manufacturing.models import (
    Bom,
    BomComponent,
    MrpRun,
    PlannedOrder,
    ProductionOrder,
    ProductionOrderComponent,
    Routing,
    RoutingOperation,
    WorkCenter,
)


async def get_bom(
    session: AsyncSession, tenant_id: uuid.UUID, bom_id: uuid.UUID
) -> Bom | None:
    """The BOM header with ``bom_id`` in the tenant, or None."""
    stmt = select(Bom).where(Bom.tenant_id == tenant_id, Bom.id == bom_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_active_bom_for_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> Bom | None:
    """The ACTIVE default BOM version for an item (D-047), or None if the item has no active
    default. The single version 8.2/8.3 explode against. Index-served by (tenant, item_id,
    status)."""
    stmt = select(Bom).where(
        Bom.tenant_id == tenant_id,
        Bom.item_id == item_id,
        Bom.status == BomStatus.ACTIVE.value,
        Bom.is_default.is_(True),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def bom_components(
    session: AsyncSession, tenant_id: uuid.UUID, bom_id: uuid.UUID
) -> list[BomComponent]:
    """A BOM's direct components, ordered by line_number (the explosion input). One indexed read."""
    stmt = (
        select(BomComponent)
        .where(BomComponent.tenant_id == tenant_id, BomComponent.bom_id == bom_id)
        .order_by(BomComponent.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_routing(
    session: AsyncSession, tenant_id: uuid.UUID, routing_id: uuid.UUID
) -> Routing | None:
    """The routing header with ``routing_id`` in the tenant, or None."""
    stmt = select(Routing).where(Routing.tenant_id == tenant_id, Routing.id == routing_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_active_routing_for_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> Routing | None:
    """The ACTIVE default routing version for an item (D-047), or None. The version 8.2 schedules
    and 8.3 loads. Index-served by (tenant, item_id, status)."""
    stmt = select(Routing).where(
        Routing.tenant_id == tenant_id,
        Routing.item_id == item_id,
        Routing.status == RoutingStatus.ACTIVE.value,
        Routing.is_default.is_(True),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def routing_operations(
    session: AsyncSession, tenant_id: uuid.UUID, routing_id: uuid.UUID
) -> list[RoutingOperation]:
    """A routing's operations, ordered by operation_number (the scheduling/load input). One indexed
    read."""
    stmt = (
        select(RoutingOperation)
        .where(
            RoutingOperation.tenant_id == tenant_id,
            RoutingOperation.routing_id == routing_id,
        )
        .order_by(RoutingOperation.operation_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_work_center(
    session: AsyncSession, tenant_id: uuid.UUID, work_center_id: uuid.UUID
) -> WorkCenter | None:
    """The work centre with ``work_center_id`` in the tenant, or None."""
    stmt = select(WorkCenter).where(
        WorkCenter.tenant_id == tenant_id, WorkCenter.id == work_center_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def work_center_capacity(
    session: AsyncSession, tenant_id: uuid.UUID, work_center_id: uuid.UUID
) -> Decimal | None:
    """A work centre's available hours/day (the number 8.3's rough capacity check compares load
    against), or None if the work centre does not exist. Does NOT apply efficiency — the caller
    decides whether to scale; this returns the raw declared capacity."""
    stmt = select(WorkCenter.capacity_hours_per_day).where(
        WorkCenter.tenant_id == tenant_id, WorkCenter.id == work_center_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# --- Production orders (PLAN 8.2, D-048) --------------------------------------


async def get_production_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> ProductionOrder | None:
    """The production-order header with ``order_id`` in the tenant, or None."""
    stmt = select(ProductionOrder).where(
        ProductionOrder.tenant_id == tenant_id, ProductionOrder.id == order_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def production_order_components(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> list[ProductionOrderComponent]:
    """A production order's exploded component requirements, ordered by line_number (the issue input
    + the nested list). One indexed read by (tenant, production_order_id)."""
    stmt = (
        select(ProductionOrderComponent)
        .where(
            ProductionOrderComponent.tenant_id == tenant_id,
            ProductionOrderComponent.production_order_id == order_id,
        )
        .order_by(ProductionOrderComponent.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def order_wip_balance(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> Decimal | None:
    """A production order's ACCUMULATED WIP cost (D-048): the running WIP debit raised by each
    component issue and consumed at finish. The maintained header figure (not a journal recompute)
    so the finish flow derives the finished unit cost from it; the WIP-nets-to-zero SSOT. None if
    the order does not exist."""
    stmt = select(ProductionOrder.accumulated_wip_cost).where(
        ProductionOrder.tenant_id == tenant_id, ProductionOrder.id == order_id
    )
    value = (await session.execute(stmt)).scalar_one_or_none()
    return Decimal(value) if value is not None else None


async def open_production_orders(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[ProductionOrder]:
    """The OPEN production orders (DRAFT / RELEASED / IN_PROGRESS) — not yet FINISHED or CANCELLED
    (PLAN 8.2). 8.3's capacity load + a shop-floor dashboard read these. Index-served by
    (tenant, status); ordered by order_number for a stable scan."""
    open_statuses = (
        ProductionOrderStatus.DRAFT.value,
        ProductionOrderStatus.RELEASED.value,
        ProductionOrderStatus.IN_PROGRESS.value,
    )
    stmt = (
        select(ProductionOrder)
        .where(
            ProductionOrder.tenant_id == tenant_id,
            ProductionOrder.status.in_(open_statuses),
        )
        .order_by(ProductionOrder.order_number)
    )
    return list((await session.execute(stmt)).scalars().all())


# --- MRP supply + planned-order reads (PLAN 8.3, D-049) ------------------------


async def open_production_order_supply(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> Decimal:
    """The UN-FINISHED quantity an item's OPEN production orders will yield (PLAN 8.3) — the
    in-house-supply side of the MRP net (the production analogue of procurement's
    ``open_incoming_quantity``). Sums ``quantity − finished_quantity`` over the item's
    DRAFT/RELEASED/IN_PROGRESS orders (a FINISHED/CANCELLED order yields nothing more). SET-BASED
    (no per-order N+1, PERFORMANCE §2): one filtered scan on (tenant, item_id), summed in PYTHON so
    the exact-decimal QuantityType round-trips identically on both engines (D-015)."""
    open_statuses = (
        ProductionOrderStatus.DRAFT.value,
        ProductionOrderStatus.RELEASED.value,
        ProductionOrderStatus.IN_PROGRESS.value,
    )
    stmt = select(ProductionOrder.quantity, ProductionOrder.finished_quantity).where(
        ProductionOrder.tenant_id == tenant_id,
        ProductionOrder.item_id == item_id,
        ProductionOrder.status.in_(open_statuses),
    )
    rows = (await session.execute(stmt)).all()
    return sum(
        (Decimal(str(qty)) - Decimal(str(finished)) for qty, finished in rows),
        Decimal(0),
    )


async def get_mrp_run(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> MrpRun | None:
    """The MRP run with ``run_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(MrpRun).where(MrpRun.tenant_id == tenant_id, MrpRun.id == run_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def planned_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    mrp_run_id: uuid.UUID,
) -> list[PlannedOrder]:
    """A run's planned orders, ordered by (level, item) so finished goods (level 0) precede their
    components (PLAN 8.3). One indexed read by (tenant, mrp_run_id); the capacity scan + the nested
    list read these."""
    stmt = (
        select(PlannedOrder)
        .where(
            PlannedOrder.tenant_id == tenant_id,
            PlannedOrder.mrp_run_id == mrp_run_id,
        )
        .order_by(PlannedOrder.level, PlannedOrder.item_id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def planned_make_supply(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> Decimal:
    """The quantity an item's still-open FIRMED/CONVERTED planned orders contribute as supply across
    ALL runs (PLAN 8.3, the regeneration policy, D-049). A FIRMED/CONVERTED planned order is a
    committed replenishment a fresh run must NOT re-propose — so the run nets it as supply.
    SET-BASED, summed in Python (D-015)."""
    stmt = select(PlannedOrder.quantity).where(
        PlannedOrder.tenant_id == tenant_id,
        PlannedOrder.item_id == item_id,
        PlannedOrder.status.in_(
            (PlannedOrderStatus.FIRMED.value, PlannedOrderStatus.CONVERTED.value)
        ),
    )
    rows = (await session.execute(stmt)).all()
    return sum((Decimal(str(qty)) for (qty,) in rows), Decimal(0))

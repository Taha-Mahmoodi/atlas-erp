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

from app.modules.manufacturing.constants import BomStatus, RoutingStatus
from app.modules.manufacturing.models import (
    Bom,
    BomComponent,
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

"""Maintenance's cross-module read interface (STRUCTURE §5 / D-051).

Maintenance sits ABOVE finance in the dependency order; nothing imports this yet (it is the newest
module), but it is the ONLY maintenance file a later module may import — kept thin and stable. The
service and router use these reads too. Every function takes an explicit ``tenant_id`` and runs
under the caller's tenant context, so the D-007 filter applies on top — ordinary tenant-scoped
reads.

``due_plans`` is the SET-BASED scan the preventive-generation run drives (PERFORMANCE §2): one query
returns every ACTIVE plan due on/before ``as_of``, ordered by code for a deterministic generation
order — no per-plan N+1 in the run beyond the order creation.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.maintenance.constants import MaintenancePlanStatus
from app.modules.maintenance.models import Equipment, MaintenanceOrder, MaintenancePlan


async def get_equipment(
    session: AsyncSession, tenant_id: uuid.UUID, equipment_id: uuid.UUID
) -> Equipment | None:
    """The equipment with ``equipment_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(Equipment).where(
        Equipment.tenant_id == tenant_id, Equipment.id == equipment_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def equipment_exists(
    session: AsyncSession, tenant_id: uuid.UUID, equipment_id: uuid.UUID
) -> bool:
    """Whether a piece of equipment with ``equipment_id`` exists in the tenant (a cheap id probe the
    plan/order create paths use)."""
    stmt = select(Equipment.id).where(
        Equipment.tenant_id == tenant_id, Equipment.id == equipment_id
    )
    return (await session.execute(stmt)).first() is not None


async def get_maintenance_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> MaintenanceOrder | None:
    """The maintenance order with ``order_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(MaintenanceOrder).where(
        MaintenanceOrder.tenant_id == tenant_id, MaintenanceOrder.id == order_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def orders_for_equipment(
    session: AsyncSession, tenant_id: uuid.UUID, equipment_id: uuid.UUID
) -> list[MaintenanceOrder]:
    """The maintenance orders raised against one piece of equipment (D-051), ordered by
    order_number. The set an equipment detail / history view reads. Index-served by (tenant,
    equipment_id, status)."""
    stmt = (
        select(MaintenanceOrder)
        .where(
            MaintenanceOrder.tenant_id == tenant_id,
            MaintenanceOrder.equipment_id == equipment_id,
        )
        .order_by(MaintenanceOrder.order_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_maintenance_plan(
    session: AsyncSession, tenant_id: uuid.UUID, plan_id: uuid.UUID
) -> MaintenancePlan | None:
    """The maintenance plan with ``plan_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(MaintenancePlan).where(
        MaintenancePlan.tenant_id == tenant_id, MaintenancePlan.id == plan_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def due_plans(
    session: AsyncSession, tenant_id: uuid.UUID, as_of: date
) -> list[MaintenancePlan]:
    """Every ACTIVE maintenance plan due on/before ``as_of`` (D-051) — the SET-BASED scan the
    preventive-generation run drives (PERFORMANCE §2: ONE query, no per-plan N+1). Ordered by code
    so the generation order is deterministic. Index-served by (tenant, status, next_due_date)."""
    stmt = (
        select(MaintenancePlan)
        .where(
            MaintenancePlan.tenant_id == tenant_id,
            MaintenancePlan.status == MaintenancePlanStatus.ACTIVE.value,
            MaintenancePlan.next_due_date <= as_of,
        )
        .order_by(MaintenancePlan.code)
    )
    return list((await session.execute(stmt)).scalars().all())

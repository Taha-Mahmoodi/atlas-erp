"""Quality's cross-module read interface (STRUCTURE §5 / D-050).

Quality sits ABOVE inventory and procurement in the dependency order; nothing imports this yet (it
is
the newest module), but it is the ONLY quality file a later module may import — kept thin and
stable.
The service and router use these reads too. Every function takes an explicit ``tenant_id`` and runs
under the caller's tenant context, so the D-007 filter applies on top — ordinary tenant-scoped
reads.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.constants import InspectionLotStatus
from app.modules.quality.models import InspectionLot


async def get_inspection_lot(
    session: AsyncSession, tenant_id: uuid.UUID, lot_id: uuid.UUID
) -> InspectionLot | None:
    """The inspection lot with ``lot_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(InspectionLot).where(
        InspectionLot.tenant_id == tenant_id, InspectionLot.id == lot_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def open_lots_for_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> list[InspectionLot]:
    """An item's OPEN (undecided) inspection lots (D-050). The set a quality dashboard / a future
    "is this stock cleared?" check reads. Index-served by (tenant, item_id); ordered by lot_number
    for a stable scan."""
    stmt = (
        select(InspectionLot)
        .where(
            InspectionLot.tenant_id == tenant_id,
            InspectionLot.item_id == item_id,
            InspectionLot.status == InspectionLotStatus.OPEN.value,
        )
        .order_by(InspectionLot.lot_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def lots_for_goods_receipt(
    session: AsyncSession, tenant_id: uuid.UUID, source_document_id: uuid.UUID
) -> list[InspectionLot]:
    """The inspection lots created from one goods receipt (D-050), by the GR's core_documents id.
    The
    set the GR detail / docflow render reads. Index-served by (tenant, source_document_id); ordered
    by lot_number."""
    stmt = (
        select(InspectionLot)
        .where(
            InspectionLot.tenant_id == tenant_id,
            InspectionLot.source_document_id == source_document_id,
        )
        .order_by(InspectionLot.lot_number)
    )
    return list((await session.execute(stmt)).scalars().all())

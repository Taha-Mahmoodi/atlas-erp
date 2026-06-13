"""Unit-of-measure business logic (PLAN 5.1): CRUD on the unit definitions.

Base-ness is NOT here — which UoM is an item's base is on the item, and per-item alternate-UoM
factors live in service/conversions.py. ``from __future__ import annotations`` keeps ``Page[Uom]``
(the ORM model) a string at import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, paginate
from app.core.schemas import Page
from app.modules.inventory.models import Uom
from app.modules.inventory.schemas import UomCreate, UomUpdate


async def _uom_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> Uom | None:
    stmt = select(Uom).where(Uom.tenant_id == tenant_id, Uom.code == code)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_uom(session: AsyncSession, tenant_id: uuid.UUID, uom_id: uuid.UUID) -> Uom:
    uom = await session.get(Uom, uom_id)
    if uom is None or uom.tenant_id != tenant_id:
        raise NotFoundError(message="Unit of measure not found", code="inventory.uom_not_found")
    return uom


async def create_uom(
    session: AsyncSession, tenant_id: uuid.UUID, payload: UomCreate
) -> Uom:
    """Create a unit of measure. Rejects a duplicate code (the DB UNIQUE is the backstop)."""
    if await _uom_by_code(session, tenant_id, payload.code) is not None:
        raise ConflictError(
            message=f"A unit of measure with code {payload.code} already exists",
            code="inventory.uom_code_conflict",
            details={"code": payload.code},
        )
    uom = Uom(tenant_id=tenant_id, code=payload.code, name=payload.name)
    session.add(uom)
    await session.flush()
    return uom


async def update_uom(
    session: AsyncSession, tenant_id: uuid.UUID, uom_id: uuid.UUID, payload: UomUpdate
) -> Uom:
    """Partial update of a UoM's display name (D-010: mutate the loaded object). code is immutable
    and absent from the schema."""
    uom = await get_uom(session, tenant_id, uom_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(uom, field, value)
    await session.flush()
    return uom


async def list_uoms(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Uom]:
    """Keyset-paginated UoMs ordered by code (D-014)."""
    stmt = select(Uom).where(Uom.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Uom.code, SortDirection.ASC)],
        pk=Uom.id,
        cursor=cursor,
        limit=limit,
    )

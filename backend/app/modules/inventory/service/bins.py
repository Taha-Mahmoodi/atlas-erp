"""Bin business logic (PLAN 5.2): CRUD on storage bins within a warehouse.

A bin belongs to a warehouse (validated to exist + active on create); its code is unique per
(tenant, warehouse). Like warehouses, bins are reference data and are deactivated, never deleted
(moves/quants reference them). ``from __future__ import annotations`` keeps ``Page[Bin]`` (the ORM
model) a string at import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.inventory.models import Bin
from app.modules.inventory.schemas import BinCreate, BinUpdate
from app.modules.inventory.service.warehouses import get_warehouse


async def get_bin(session: AsyncSession, tenant_id: uuid.UUID, bin_id: uuid.UUID) -> Bin:
    bin_row = await session.get(Bin, bin_id)
    if bin_row is None or bin_row.tenant_id != tenant_id:
        raise NotFoundError(message="Bin not found", code="inventory.bin_not_found")
    return bin_row


async def _bin_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID, code: str
) -> Bin | None:
    stmt = select(Bin).where(
        Bin.tenant_id == tenant_id,
        Bin.warehouse_id == warehouse_id,
        Bin.code == code,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_bin(
    session: AsyncSession, tenant_id: uuid.UUID, payload: BinCreate
) -> Bin:
    """Create a bin in a warehouse (PLAN 5.2). Validates the warehouse exists and is active;
    rejects a duplicate (warehouse, code). The DB UNIQUE + composite FK are the backstops."""
    warehouse = await get_warehouse(session, tenant_id, payload.warehouse_id)
    if not warehouse.is_active:
        raise ValidationFailedError(
            message="Cannot add a bin to an inactive warehouse",
            code="inventory.warehouse_inactive",
            details={"warehouse_id": str(payload.warehouse_id)},
        )
    if await _bin_by_code(session, tenant_id, payload.warehouse_id, payload.code) is not None:
        raise ConflictError(
            message=f"A bin with code {payload.code} already exists in this warehouse",
            code="inventory.bin_code_conflict",
            details={"code": payload.code, "warehouse_id": str(payload.warehouse_id)},
        )
    bin_row = Bin(
        tenant_id=tenant_id,
        warehouse_id=payload.warehouse_id,
        code=payload.code,
        name=payload.name,
        is_default=payload.is_default,
        is_active=payload.is_active,
    )
    session.add(bin_row)
    await session.flush()
    return bin_row


async def update_bin(
    session: AsyncSession, tenant_id: uuid.UUID, bin_id: uuid.UUID, payload: BinUpdate
) -> Bin:
    """Partial update of a bin (D-010: mutate the loaded object). ``code``/``warehouse_id`` are
    immutable and absent; ``is_active=False`` is the soft-delete."""
    bin_row = await get_bin(session, tenant_id, bin_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(bin_row, field, value)
    await session.flush()
    return bin_row


async def list_bins(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Bin]:
    """Keyset-paginated bins ordered by code (D-014), optionally filtered to one warehouse. The
    warehouse filter folds into the cursor fingerprint so a cursor cannot bleed across views."""
    stmt = select(Bin).where(Bin.tenant_id == tenant_id)
    if warehouse_id is not None:
        stmt = stmt.where(Bin.warehouse_id == warehouse_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Bin.code, SortDirection.ASC)],
        pk=Bin.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(warehouse_id),
    )

"""Warehouse business logic (PLAN 5.2): CRUD on the stock topology's top level.

Warehouses are reference data (codes, not gapless numbers). A warehouse is never hard-deleted —
moves and quants reference its bins, so deactivation (``is_active=False``) is the only removal path
(documented soft-delete convention). ``from __future__ import annotations`` keeps
``Page[Warehouse]`` (the ORM model) a string at import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, paginate
from app.core.schemas import Page
from app.modules.inventory.models import Warehouse
from app.modules.inventory.schemas import WarehouseCreate, WarehouseUpdate


async def _warehouse_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> Warehouse | None:
    stmt = select(Warehouse).where(
        Warehouse.tenant_id == tenant_id, Warehouse.code == code
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> Warehouse:
    warehouse = await session.get(Warehouse, warehouse_id)
    if warehouse is None or warehouse.tenant_id != tenant_id:
        raise NotFoundError(
            message="Warehouse not found", code="inventory.warehouse_not_found"
        )
    return warehouse


async def create_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, payload: WarehouseCreate
) -> Warehouse:
    """Create a warehouse. Rejects a duplicate code (the DB UNIQUE is the backstop)."""
    if await _warehouse_by_code(session, tenant_id, payload.code) is not None:
        raise ConflictError(
            message=f"A warehouse with code {payload.code} already exists",
            code="inventory.warehouse_code_conflict",
            details={"code": payload.code},
        )
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    session.add(warehouse)
    await session.flush()
    return warehouse


async def update_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    payload: WarehouseUpdate,
) -> Warehouse:
    """Partial update of a warehouse (D-010: mutate the loaded object so the audit diff is
    captured). ``code`` is immutable and absent from the schema; ``is_active=False`` is the
    soft-delete (a warehouse is never hard-deleted while moves reference its bins)."""
    warehouse = await get_warehouse(session, tenant_id, warehouse_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(warehouse, field, value)
    await session.flush()
    return warehouse


async def list_warehouses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Warehouse]:
    """Keyset-paginated warehouses ordered by code (D-014)."""
    stmt = select(Warehouse).where(Warehouse.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Warehouse.code, SortDirection.ASC)],
        pk=Warehouse.id,
        cursor=cursor,
        limit=limit,
    )

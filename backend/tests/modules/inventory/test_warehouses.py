"""Warehouse service tests (PLAN 5.2): CRUD, duplicate-code conflict, deactivation, tenant scope."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.tenancy import tenant_context
from app.modules.inventory import service
from app.modules.inventory.schemas import WarehouseCreate, WarehouseUpdate


async def test_create_and_get_warehouse(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a):
        warehouse = await service.create_warehouse(
            db_session, tenant_a, WarehouseCreate(code="WH-1", name="Warehouse 1")
        )
        await db_session.commit()
        got = await service.get_warehouse(db_session, tenant_a, warehouse.id)
    assert got.code == "WH-1"
    assert got.is_active is True


async def test_duplicate_warehouse_code_conflicts(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_warehouse(
            db_session, tenant_a, WarehouseCreate(code="DUP", name="First")
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.create_warehouse(
                db_session, tenant_a, WarehouseCreate(code="DUP", name="Second")
            )
    assert exc.value.code == "inventory.warehouse_code_conflict"


async def test_deactivate_warehouse(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """Removal is soft: is_active=False, never a hard delete (moves reference bins)."""
    with tenant_context(tenant_a):
        warehouse = await service.create_warehouse(
            db_session, tenant_a, WarehouseCreate(code="WH-OFF", name="To deactivate")
        )
        await db_session.commit()
        updated = await service.update_warehouse(
            db_session, tenant_a, warehouse.id, WarehouseUpdate(is_active=False)
        )
        await db_session.commit()
    assert updated.is_active is False


async def test_get_missing_warehouse_raises(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError) as exc:
        await service.get_warehouse(db_session, tenant_a, uuid.uuid4())
    assert exc.value.code == "inventory.warehouse_not_found"

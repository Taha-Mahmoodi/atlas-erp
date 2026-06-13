"""Bin service tests (PLAN 5.2): CRUD, warehouse validation, per-warehouse code uniqueness."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.inventory import service
from app.modules.inventory.schemas import BinCreate, WarehouseUpdate
from tests.modules.inventory.factories import build_warehouse


async def test_create_bin_in_warehouse(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    warehouse = await build_warehouse(db_session, tenant_a)
    with tenant_context(tenant_a):
        bin_row = await service.create_bin(
            db_session,
            tenant_a,
            BinCreate(warehouse_id=warehouse.id, code="A1", name="Bin A1", is_default=True),
        )
        await db_session.commit()
    assert bin_row.code == "A1"
    assert bin_row.is_default is True


async def test_bin_code_unique_per_warehouse_not_globally(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The same bin code is allowed in two different warehouses; a dup within ONE conflicts."""
    wh1 = await build_warehouse(db_session, tenant_a, code="WH-1")
    wh2 = await build_warehouse(db_session, tenant_a, code="WH-2")
    with tenant_context(tenant_a):
        await service.create_bin(
            db_session, tenant_a, BinCreate(warehouse_id=wh1.id, code="A1", name="A1")
        )
        await db_session.commit()
        # Same code, different warehouse — allowed.
        await service.create_bin(
            db_session, tenant_a, BinCreate(warehouse_id=wh2.id, code="A1", name="A1")
        )
        await db_session.commit()
        # Same code, SAME warehouse — conflict.
        with pytest.raises(ConflictError) as exc:
            await service.create_bin(
                db_session, tenant_a, BinCreate(warehouse_id=wh1.id, code="A1", name="dup")
            )
    assert exc.value.code == "inventory.bin_code_conflict"


async def test_create_bin_missing_warehouse_raises(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError) as exc:
        await service.create_bin(
            db_session, tenant_a, BinCreate(warehouse_id=uuid.uuid4(), code="A1", name="A1")
        )
    assert exc.value.code == "inventory.warehouse_not_found"


async def test_create_bin_in_inactive_warehouse_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    warehouse = await build_warehouse(db_session, tenant_a)
    with tenant_context(tenant_a):
        await service.update_warehouse(
            db_session, tenant_a, warehouse.id, WarehouseUpdate(is_active=False)
        )
        await db_session.commit()
        with pytest.raises(ValidationFailedError) as exc:
            await service.create_bin(
                db_session, tenant_a, BinCreate(warehouse_id=warehouse.id, code="A1", name="A1")
            )
    assert exc.value.code == "inventory.warehouse_inactive"


async def test_list_bins_filtered_by_warehouse(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    wh1 = await build_warehouse(db_session, tenant_a, code="WH-1")
    wh2 = await build_warehouse(db_session, tenant_a, code="WH-2")
    with tenant_context(tenant_a):
        await service.create_bin(
            db_session, tenant_a, BinCreate(warehouse_id=wh1.id, code="A1", name="A1")
        )
        await service.create_bin(
            db_session, tenant_a, BinCreate(warehouse_id=wh2.id, code="B1", name="B1")
        )
        await db_session.commit()
        page = await service.list_bins(db_session, tenant_a, warehouse_id=wh1.id)
    assert {b.code for b in page.items} == {"A1"}

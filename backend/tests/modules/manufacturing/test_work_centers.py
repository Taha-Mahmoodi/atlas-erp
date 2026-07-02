"""Work-centre service tests (PLAN 8.1): CRUD + code-conflict + cost-centre validation.

Exercises the service directly under the tenant context (the inventory test_warehouses precedent),
so the rules (duplicate code, optional cost-centre existence via finance/queries, partial update)
are pinned without the HTTP layer.
"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.manufacturing import queries, service
from app.modules.manufacturing.schemas import WorkCenterCreate, WorkCenterUpdate
from tests.modules.manufacturing.factories import build_cost_center, build_work_center


async def test_create_and_get_work_center(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    tenant_id = manufacturing_setup.tenant_id
    wc = await build_work_center(
        db_session, tenant_id, code="WC-1", capacity_hours_per_day=Decimal(16)
    )
    with tenant_context(tenant_id):
        fetched = await service.get_work_center(db_session, tenant_id, wc.id)
    assert fetched.code == "WC-1"
    assert fetched.capacity_hours_per_day == Decimal(16)
    assert fetched.efficiency_percent == Decimal(100)
    assert fetched.is_active is True


async def test_work_center_capacity_query(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    tenant_id = manufacturing_setup.tenant_id
    wc = await build_work_center(db_session, tenant_id, capacity_hours_per_day=Decimal("7.5"))
    with tenant_context(tenant_id):
        capacity = await queries.work_center_capacity(db_session, tenant_id, wc.id)
    assert capacity == Decimal("7.5")


async def test_duplicate_code_conflicts(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    tenant_id = manufacturing_setup.tenant_id
    await build_work_center(db_session, tenant_id, code="WC-DUP")
    with tenant_context(tenant_id), pytest.raises(ConflictError) as excinfo:
        await service.create_work_center(
            db_session, tenant_id, WorkCenterCreate(code="WC-DUP", name="Other")
        )
    assert excinfo.value.code == "manufacturing.work_center_code_conflict"


async def test_cost_center_must_exist(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    """An opaque finance cost-centre id is validated to exist (D-029): a real id is accepted, a
    random one is rejected."""
    tenant_id = manufacturing_setup.tenant_id
    cost_center_id = await build_cost_center(db_session, tenant_id)
    wc = await build_work_center(
        db_session, tenant_id, code="WC-CC", cost_center_id=cost_center_id
    )
    assert wc.cost_center_id == cost_center_id

    import uuid

    with tenant_context(tenant_id), pytest.raises(ValidationFailedError) as excinfo:
        await service.create_work_center(
            db_session,
            tenant_id,
            WorkCenterCreate(code="WC-BAD", name="Bad", cost_center_id=uuid.uuid4()),
        )
    assert excinfo.value.code == "manufacturing.cost_center_not_found"


async def test_update_work_center(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    tenant_id = manufacturing_setup.tenant_id
    wc = await build_work_center(db_session, tenant_id, code="WC-UPD")
    with tenant_context(tenant_id):
        updated = await service.update_work_center(
            db_session,
            tenant_id,
            wc.id,
            WorkCenterUpdate(name="Renamed", is_active=False, efficiency_percent=Decimal(80)),
        )
    assert updated.name == "Renamed"
    assert updated.is_active is False
    assert updated.efficiency_percent == Decimal(80)


async def test_get_missing_work_center_raises(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    import uuid

    tenant_id = manufacturing_setup.tenant_id
    with tenant_context(tenant_id), pytest.raises(NotFoundError):
        await service.get_work_center(db_session, tenant_id, uuid.uuid4())

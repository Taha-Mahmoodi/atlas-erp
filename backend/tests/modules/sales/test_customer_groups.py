"""Customer-group service tests (PLAN 7.1): CRUD + the code-unique rule."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.tenancy import tenant_context
from app.modules.sales import service
from app.modules.sales.schemas import CustomerGroupCreate, CustomerGroupUpdate
from tests.modules.sales.factories import build_customer_group


async def test_create_and_get_group(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    group = await build_customer_group(db_session, tenant_a, code="GRP-1", name="Wholesale")
    with tenant_context(tenant_a):
        got = await service.get_customer_group(db_session, tenant_a, group.id)
    assert got.code == "GRP-1"
    assert got.name == "Wholesale"


async def test_duplicate_code_conflicts(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await build_customer_group(db_session, tenant_a, code="GRP-1")
    with tenant_context(tenant_a), pytest.raises(ConflictError):
        await service.create_customer_group(
            db_session, tenant_a, CustomerGroupCreate(code="GRP-1", name="Other")
        )


async def test_update_name_only(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    group = await build_customer_group(db_session, tenant_a, name="Wholesale")
    with tenant_context(tenant_a):
        updated = await service.update_customer_group(
            db_session, tenant_a, group.id, CustomerGroupUpdate(name="Retail")
        )
    assert updated.name == "Retail"
    assert updated.code == group.code


async def test_get_missing_group_raises(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await service.get_customer_group(db_session, tenant_a, uuid.uuid4())

"""Item-category service rules (PLAN 5.1, D-020/D-029): CRUD, unique code, GL-account validation."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.inventory import service
from app.modules.inventory.constants import CostingMethod
from app.modules.inventory.schemas import ItemCategoryCreate, ItemCategoryUpdate
from tests.modules.inventory.factories import build_item_category


async def test_create_category_persists_and_reads_back(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        created = await service.create_category(
            db_session,
            tenant_a,
            ItemCategoryCreate(code="CAT-1", name="Finished goods"),
        )
        await db_session.commit()
        fetched = await service.get_category(db_session, tenant_a, created.id)
    assert fetched.code == "CAT-1"
    assert fetched.default_costing_method == CostingMethod.MOVING_AVERAGE.value


async def test_default_costing_method_stored(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        category = await service.create_category(
            db_session,
            tenant_a,
            ItemCategoryCreate(
                code="FIFO-CAT", name="x", default_costing_method=CostingMethod.FIFO
            ),
        )
    assert category.default_costing_method == CostingMethod.FIFO.value


async def test_duplicate_code_raises_conflict(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_category(
            db_session, tenant_a, ItemCategoryCreate(code="DUP", name="first")
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as excinfo:
            await service.create_category(
                db_session, tenant_a, ItemCategoryCreate(code="DUP", name="second")
            )
    assert excinfo.value.code == "inventory.category_code_conflict"


async def test_unknown_gl_account_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A category referencing a non-existent finance GL account is rejected (D-029): the service
    validates the opaque id through finance/queries before storing it."""
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as excinfo:
        await service.create_category(
            db_session,
            tenant_a,
            ItemCategoryCreate(
                code="BAD-ACCT", name="x", cogs_account_id=uuid.uuid4()
            ),
        )
    assert excinfo.value.code == "inventory.gl_account_not_found"


async def test_real_gl_accounts_accepted(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A category wired to REAL finance accounts (seeded by the builder) is accepted and the opaque
    ids are stored on the category for the COGS handler to resolve later (D-020)."""
    category = await build_item_category(
        db_session, tenant_a, code="WIRED", with_accounts=True
    )
    with tenant_context(tenant_a):
        fetched = await service.get_category(db_session, tenant_a, category.id)
    assert fetched.inventory_account_id is not None
    assert fetched.cogs_account_id is not None
    assert fetched.price_difference_account_id is not None


async def test_update_category_changes_costing_method(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    category = await build_item_category(db_session, tenant_a, code="UPD")
    with tenant_context(tenant_a):
        updated = await service.update_category(
            db_session,
            tenant_a,
            category.id,
            ItemCategoryUpdate(default_costing_method=CostingMethod.FIFO, name="Renamed"),
        )
    assert updated.default_costing_method == CostingMethod.FIFO.value
    assert updated.name == "Renamed"


async def test_get_missing_category_raises_not_found(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError) as excinfo:
        await service.get_category(db_session, tenant_a, uuid.uuid4())
    assert excinfo.value.code == "inventory.category_not_found"

"""Price-list service tests (PLAN 7.1): price-list + price-list-item CRUD and validation."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.sales import service
from app.modules.sales.constants import PriceListStatus
from app.modules.sales.schemas import PriceListCreate, PriceListItemCreate, PriceListUpdate
from tests.modules.sales.factories import (
    build_customer_group,
    build_price_list,
    build_price_list_item,
    build_sales_setup,
    seed_currency,
)


async def test_create_price_list_defaults(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await seed_currency(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a)
    assert pl.status == PriceListStatus.ACTIVE.value
    assert pl.priority == 0
    assert pl.customer_group_id is None
    assert pl.valid_to is None


async def test_duplicate_code_conflicts(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await seed_currency(db_session, tenant_a)
    await build_price_list(db_session, tenant_a, code="PL-1")
    with tenant_context(tenant_a), pytest.raises(ConflictError):
        await service.create_price_list(
            db_session,
            tenant_a,
            PriceListCreate(
                code="PL-1", name="x", currency_code="USD", valid_from=date(2026, 1, 1)
            ),
        )


async def test_unknown_currency_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError):
        await service.create_price_list(
            db_session,
            tenant_a,
            PriceListCreate(
                code="PL-1", name="x", currency_code="EUR", valid_from=date(2026, 1, 1)
            ),
        )


async def test_unknown_group_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await seed_currency(db_session, tenant_a)
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await service.create_price_list(
            db_session,
            tenant_a,
            PriceListCreate(
                code="PL-1",
                name="x",
                currency_code="USD",
                valid_from=date(2026, 1, 1),
                customer_group_id=uuid.uuid4(),
            ),
        )


async def test_targeted_group_list(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await seed_currency(db_session, tenant_a)
    group = await build_customer_group(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a, customer_group_id=group.id)
    assert pl.customer_group_id == group.id


async def test_update_invalid_window_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await seed_currency(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a, valid_from=date(2026, 1, 1))
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError):
        await service.update_price_list(
            db_session, tenant_a, pl.id, PriceListUpdate(valid_to=date(2025, 12, 31))
        )


async def test_add_and_list_items(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a)
    item = await build_price_list_item(
        db_session, tenant_a, pl.id, setup.item_id, unit_price="12.50", min_quantity="5"
    )
    assert Decimal(str(item.unit_price)) == Decimal("12.50")
    assert Decimal(str(item.min_quantity)) == Decimal("5")
    with tenant_context(tenant_a):
        rows = await service.list_price_list_items(db_session, tenant_a, pl.id)
    assert len(rows) == 1


async def test_item_unknown_inventory_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await seed_currency(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a)
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError):
        await service.add_price_list_item(
            db_session,
            tenant_a,
            pl.id,
            PriceListItemCreate(item_id=uuid.uuid4(), unit_price=Decimal("1")),
        )


async def test_item_duplicate_conflicts(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a)
    await build_price_list_item(db_session, tenant_a, pl.id, setup.item_id)
    with tenant_context(tenant_a), pytest.raises(ConflictError):
        await service.add_price_list_item(
            db_session,
            tenant_a,
            pl.id,
            PriceListItemCreate(item_id=setup.item_id, unit_price=Decimal("9")),
        )


async def test_remove_item(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a)
    await build_price_list_item(db_session, tenant_a, pl.id, setup.item_id)
    with tenant_context(tenant_a):
        await service.remove_price_list_item(db_session, tenant_a, pl.id, setup.item_id)
        rows = await service.list_price_list_items(db_session, tenant_a, pl.id)
    assert rows == []


async def test_list_items_missing_list_raises(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await service.list_price_list_items(db_session, tenant_a, uuid.uuid4())

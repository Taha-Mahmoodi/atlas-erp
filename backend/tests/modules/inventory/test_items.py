"""Item service rules (PLAN 5.1, D-020): CRUD, type rules, tracking-only-on-stocked, costing
default from category, and the inventory/queries cross-module read interface."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.inventory import queries, service
from app.modules.inventory.constants import CostingMethod, ItemType, TrackingMode
from app.modules.inventory.schemas import ItemCreate, ItemUpdate
from tests.modules.inventory.factories import (
    InventorySetup,
    build_item,
    build_item_category,
    seed_uom,
)


async def test_create_item_persists_and_reads_back(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    with tenant_context(tenant_a):
        created = await service.create_item(
            db_session,
            tenant_a,
            ItemCreate(
                item_code="WIDGET-1",
                name="Widget",
                item_type=ItemType.STOCKED,
                category_id=inventory_setup.category_id,
                base_uom_id=inventory_setup.ea_uom_id,
            ),
        )
        await db_session.commit()
        fetched = await service.get_item(db_session, tenant_a, created.id)
    assert fetched.item_code == "WIDGET-1"
    assert fetched.item_type == ItemType.STOCKED.value


async def test_costing_method_defaults_from_category(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An item with no costing_method inherits its category default (D-020), stored on the item."""
    ea = await seed_uom(db_session, tenant_a, "EA", "Each")
    category = await build_item_category(
        db_session, tenant_a, code="FIFO-CAT", costing=CostingMethod.FIFO
    )
    with tenant_context(tenant_a):
        item = await service.create_item(
            db_session,
            tenant_a,
            ItemCreate(
                item_code="FIFO-ITEM",
                name="x",
                item_type=ItemType.STOCKED,
                category_id=category.id,
                base_uom_id=ea.id,
            ),
        )
    assert item.costing_method == CostingMethod.FIFO.value


async def test_explicit_costing_method_overrides_category(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    with tenant_context(tenant_a):
        item = await service.create_item(
            db_session,
            tenant_a,
            ItemCreate(
                item_code="OVERRIDE",
                name="x",
                item_type=ItemType.STOCKED,
                category_id=inventory_setup.category_id,
                base_uom_id=inventory_setup.ea_uom_id,
                costing_method=CostingMethod.FIFO,
            ),
        )
    assert item.costing_method == CostingMethod.FIFO.value


@pytest.mark.parametrize("item_type", [ItemType.NON_STOCKED, ItemType.SERVICE])
async def test_tracking_rejected_on_non_stocked(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    inventory_setup: InventorySetup,
    item_type: ItemType,
) -> None:
    """Only STOCKED items can be lot/serial tracked (D-020)."""
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as excinfo:
        await service.create_item(
            db_session,
            tenant_a,
            ItemCreate(
                item_code=f"NT-{item_type.value}",
                name="x",
                item_type=item_type,
                category_id=inventory_setup.category_id,
                base_uom_id=inventory_setup.ea_uom_id,
                tracking_mode=TrackingMode.LOT,
            ),
        )
    assert excinfo.value.code == "inventory.tracking_requires_stocked"


async def test_stocked_item_accepts_lot_tracking(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    with tenant_context(tenant_a):
        item = await service.create_item(
            db_session,
            tenant_a,
            ItemCreate(
                item_code="LOT-ITEM",
                name="x",
                item_type=ItemType.STOCKED,
                category_id=inventory_setup.category_id,
                base_uom_id=inventory_setup.ea_uom_id,
                tracking_mode=TrackingMode.SERIAL,
            ),
        )
    assert item.tracking_mode == TrackingMode.SERIAL.value


async def test_service_item_allows_none_tracking(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    """A SERVICE item with tracking NONE is fine — the rule only forbids NON-NONE tracking."""
    with tenant_context(tenant_a):
        item = await service.create_item(
            db_session,
            tenant_a,
            ItemCreate(
                item_code="SVC-1",
                name="Consulting",
                item_type=ItemType.SERVICE,
                category_id=inventory_setup.category_id,
                base_uom_id=inventory_setup.ea_uom_id,
            ),
        )
    assert item.tracking_mode == TrackingMode.NONE.value


async def test_duplicate_item_code_conflict(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    await build_item(
        db_session,
        tenant_a,
        item_code="DUP-ITEM",
        category_id=inventory_setup.category_id,
        base_uom_id=inventory_setup.ea_uom_id,
    )
    with tenant_context(tenant_a), pytest.raises(ConflictError) as excinfo:
        await service.create_item(
            db_session,
            tenant_a,
            ItemCreate(
                item_code="DUP-ITEM",
                name="other",
                item_type=ItemType.STOCKED,
                category_id=inventory_setup.category_id,
                base_uom_id=inventory_setup.ea_uom_id,
            ),
        )
    assert excinfo.value.code == "inventory.item_code_conflict"


async def test_unknown_category_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError) as excinfo:
        await service.create_item(
            db_session,
            tenant_a,
            ItemCreate(
                item_code="NO-CAT",
                name="x",
                item_type=ItemType.STOCKED,
                category_id=uuid.uuid4(),
                base_uom_id=inventory_setup.ea_uom_id,
            ),
        )
    assert excinfo.value.code == "inventory.category_not_found"


async def test_unknown_base_uom_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError) as excinfo:
        await service.create_item(
            db_session,
            tenant_a,
            ItemCreate(
                item_code="NO-UOM",
                name="x",
                item_type=ItemType.STOCKED,
                category_id=inventory_setup.category_id,
                base_uom_id=uuid.uuid4(),
            ),
        )
    assert excinfo.value.code == "inventory.uom_not_found"


async def test_update_item_rejects_tracking_on_service(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    """A PATCH that would lot-track a SERVICE item is rejected — item_type is immutable, so the
    rule still applies against the stored type."""
    item = await build_item(
        db_session,
        tenant_a,
        item_code="SVC-UPD",
        category_id=inventory_setup.category_id,
        base_uom_id=inventory_setup.ea_uom_id,
        item_type="SERVICE",
    )
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as excinfo:
        await service.update_item(
            db_session, tenant_a, item.id, ItemUpdate(tracking_mode=TrackingMode.LOT)
        )
    assert excinfo.value.code == "inventory.tracking_requires_stocked"


async def test_update_item_changes_reorder_point(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    item = await build_item(
        db_session,
        tenant_a,
        item_code="REORDER",
        category_id=inventory_setup.category_id,
        base_uom_id=inventory_setup.ea_uom_id,
    )
    with tenant_context(tenant_a):
        updated = await service.update_item(
            db_session,
            tenant_a,
            item.id,
            ItemUpdate(reorder_point=Decimal("10.5"), reorder_quantity=Decimal(100)),
        )
    assert updated.reorder_point == Decimal("10.5")
    assert updated.reorder_quantity == Decimal(100)


# --- inventory/queries cross-module read interface ----------------------------


async def test_queries_expose_item_master(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The queries surface other modules consume: base UoM, costing method, and the category's GL
    accounts (D-020). Built on a wired category so get_category_accounts returns real ids."""
    ea = await seed_uom(db_session, tenant_a, "EA", "Each")
    category = await build_item_category(
        db_session, tenant_a, code="Q-CAT", with_accounts=True
    )
    item = await build_item(
        db_session,
        tenant_a,
        item_code="Q-ITEM",
        category_id=category.id,
        base_uom_id=ea.id,
    )
    with tenant_context(tenant_a):
        assert await queries.item_exists(db_session, tenant_a, item.id) is True
        assert await queries.get_base_uom(db_session, tenant_a, item.id) == ea.id
        method = await queries.get_costing_method(db_session, tenant_a, item.id)
        accounts = await queries.get_category_accounts(db_session, tenant_a, item.id)
    assert method == CostingMethod.MOVING_AVERAGE
    assert accounts is not None
    inventory_acct, cogs_acct, price_diff_acct = accounts
    assert inventory_acct is not None and cogs_acct is not None and price_diff_acct is not None


async def test_queries_item_exists_false_for_missing(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        assert await queries.item_exists(db_session, tenant_a, uuid.uuid4()) is False
        assert await queries.get_base_uom(db_session, tenant_a, uuid.uuid4()) is None
        assert await queries.get_category_accounts(db_session, tenant_a, uuid.uuid4()) is None

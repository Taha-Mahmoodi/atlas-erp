"""UoM definitions, per-item conversions, and the pure ``convert_quantity`` math (PLAN 5.1)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.inventory import service
from app.modules.inventory.schemas import UomConversionCreate, UomCreate
from tests.modules.inventory.factories import InventorySetup, build_item


async def test_create_uom_and_duplicate_conflict(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        uom = await service.create_uom(db_session, tenant_a, UomCreate(code="KG", name="Kilogram"))
        await db_session.commit()
        assert uom.code == "KG"
        with pytest.raises(ConflictError) as excinfo:
            await service.create_uom(db_session, tenant_a, UomCreate(code="KG", name="Kilo"))
    assert excinfo.value.code == "inventory.uom_code_conflict"


async def test_conversion_create_and_list(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    """An item's BOX = 12 EA conversion persists and lists back."""
    item = await build_item(
        db_session,
        tenant_a,
        item_code="ITEM-CONV",
        category_id=inventory_setup.category_id,
        base_uom_id=inventory_setup.ea_uom_id,
    )
    with tenant_context(tenant_a):
        await service.create_conversion(
            db_session,
            tenant_a,
            item.id,
            UomConversionCreate(alt_uom_id=inventory_setup.box_uom_id, factor_to_base=Decimal(12)),
        )
        await db_session.commit()
        conversions = await service.list_conversions(db_session, tenant_a, item.id)
    assert len(conversions) == 1
    assert conversions[0].factor_to_base == Decimal(12)


async def test_conversion_alt_cannot_be_base(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    item = await build_item(
        db_session,
        tenant_a,
        item_code="ITEM-BASE",
        category_id=inventory_setup.category_id,
        base_uom_id=inventory_setup.ea_uom_id,
    )
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as excinfo:
        await service.create_conversion(
            db_session,
            tenant_a,
            item.id,
            UomConversionCreate(
                alt_uom_id=inventory_setup.ea_uom_id, factor_to_base=Decimal(1)
            ),
        )
    assert excinfo.value.code == "inventory.conversion_alt_is_base"


async def test_conversion_factor_must_be_positive(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    item = await build_item(
        db_session,
        tenant_a,
        item_code="ITEM-ZERO",
        category_id=inventory_setup.category_id,
        base_uom_id=inventory_setup.ea_uom_id,
    )
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as excinfo:
        await service.create_conversion(
            db_session,
            tenant_a,
            item.id,
            UomConversionCreate(
                alt_uom_id=inventory_setup.box_uom_id, factor_to_base=Decimal(0)
            ),
        )
    assert excinfo.value.code == "inventory.conversion_factor_invalid"


async def test_duplicate_conversion_conflict(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    item = await build_item(
        db_session,
        tenant_a,
        item_code="ITEM-DUP-CONV",
        category_id=inventory_setup.category_id,
        base_uom_id=inventory_setup.ea_uom_id,
    )
    with tenant_context(tenant_a):
        payload = UomConversionCreate(
            alt_uom_id=inventory_setup.box_uom_id, factor_to_base=Decimal(12)
        )
        await service.create_conversion(db_session, tenant_a, item.id, payload)
        await db_session.commit()
        with pytest.raises(ConflictError) as excinfo:
            await service.create_conversion(db_session, tenant_a, item.id, payload)
    assert excinfo.value.code == "inventory.conversion_conflict"


# --- convert_quantity: pure math (base BOX=12 EA, base CASE=24 EA on the same item) ----------

_BASE = uuid.uuid4()  # EA (base)
_BOX = uuid.uuid4()  # 12 EA
_CASE = uuid.uuid4()  # 24 EA
_FACTORS = {_BASE: Decimal(1), _BOX: Decimal(12), _CASE: Decimal(24)}


def test_convert_alt_to_base() -> None:
    """2 BOX -> 24 EA (multiply by factor-to-base)."""
    result = service.convert_quantity(Decimal(2), _BOX, _BASE, _BASE, _FACTORS)
    assert result == Decimal("24.000000")


def test_convert_base_to_alt() -> None:
    """24 EA -> 2 BOX (divide by factor-to-base)."""
    result = service.convert_quantity(Decimal(24), _BASE, _BOX, _BASE, _FACTORS)
    assert result == Decimal("2.000000")


def test_convert_round_trip_is_identity() -> None:
    """EA -> BOX -> EA returns the original quantity (no precision loss at scale 6)."""
    to_box = service.convert_quantity(Decimal(36), _BASE, _BOX, _BASE, _FACTORS)
    back_to_ea = service.convert_quantity(to_box, _BOX, _BASE, _BASE, _FACTORS)
    assert back_to_ea == Decimal("36.000000")


def test_convert_alt_to_alt() -> None:
    """2 CASE -> 4 BOX (alt<->alt derives from both per-alternate factors: 2*24/12 = 4)."""
    result = service.convert_quantity(Decimal(2), _CASE, _BOX, _BASE, _FACTORS)
    assert result == Decimal("4.000000")


def test_convert_same_uom_is_noop() -> None:
    result = service.convert_quantity(Decimal("5.5"), _BOX, _BOX, _BASE, _FACTORS)
    assert result == Decimal("5.500000")


def test_convert_unknown_uom_raises() -> None:
    """A UoM with no factor for this item is not convertible (conversions are per item)."""
    unknown = uuid.uuid4()
    with pytest.raises(ValidationFailedError) as excinfo:
        service.convert_quantity(Decimal(1), unknown, _BASE, _BASE, _FACTORS)
    assert excinfo.value.code == "inventory.conversion_undefined"


async def test_get_conversion_factors_includes_base(
    db_session: AsyncSession, tenant_a: uuid.UUID, inventory_setup: InventorySetup
) -> None:
    """The loaded factor table maps the base UoM to 1 and each alternate to its factor — the input
    convert_quantity consumes."""
    item = await build_item(
        db_session,
        tenant_a,
        item_code="ITEM-FACTORS",
        category_id=inventory_setup.category_id,
        base_uom_id=inventory_setup.ea_uom_id,
    )
    with tenant_context(tenant_a):
        await service.create_conversion(
            db_session,
            tenant_a,
            item.id,
            UomConversionCreate(alt_uom_id=inventory_setup.box_uom_id, factor_to_base=Decimal(12)),
        )
        await db_session.commit()
        factors = await service.get_conversion_factors(db_session, tenant_a, item.id)
    assert factors[inventory_setup.ea_uom_id] == Decimal(1)
    assert factors[inventory_setup.box_uom_id] == Decimal(12)

"""Per-item UoM-conversion business logic + the pure ``convert_quantity`` helper (PLAN 5.1).

The chosen UoM convention (per-item base + alternates): each item has one base UoM, and a
conversion expresses an ALTERNATE UoM as ``factor_to_base`` — multiplying an alternate-UoM quantity
by the factor yields the base-UoM quantity. ``convert_quantity`` is a PURE function over a loaded
factor table, so it is fully unit-testable and reused by stock moves later (PLAN 5.2+).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.inventory.models import UomConversion
from app.modules.inventory.schemas import UomConversionCreate
from app.modules.inventory.service.items import get_item
from app.modules.inventory.service.uoms import get_uom

# Quantization quantum for converted quantities: scale 6, matching QuantityType storage (D-015).
_QUANTITY_QUANTUM = Decimal(10) ** -6


async def create_conversion(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: UomConversionCreate,
) -> UomConversion:
    """Add an alternate UoM for an item (PLAN 5.1). Validates the item + alternate UoM exist, that
    the alternate is not the item's base UoM, and that the factor is positive (mirrors the DB
    CHECK). A duplicate (item, alternate) → ConflictError (the DB UNIQUE is the backstop)."""
    item = await get_item(session, tenant_id, item_id)
    await get_uom(session, tenant_id, payload.alt_uom_id)
    if payload.alt_uom_id == item.base_uom_id:
        raise ValidationFailedError(
            message="The alternate UoM cannot be the item's base UoM",
            code="inventory.conversion_alt_is_base",
        )
    if payload.factor_to_base <= 0:
        raise ValidationFailedError(
            message="The conversion factor must be greater than zero",
            code="inventory.conversion_factor_invalid",
        )
    existing = (
        await session.execute(
            select(UomConversion.id).where(
                UomConversion.tenant_id == tenant_id,
                UomConversion.item_id == item_id,
                UomConversion.alt_uom_id == payload.alt_uom_id,
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message="A conversion for this alternate UoM already exists on the item",
            code="inventory.conversion_conflict",
        )
    conversion = UomConversion(
        tenant_id=tenant_id,
        item_id=item_id,
        alt_uom_id=payload.alt_uom_id,
        factor_to_base=payload.factor_to_base,
    )
    session.add(conversion)
    await session.flush()
    return conversion


async def list_conversions(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> list[UomConversion]:
    """All alternate-UoM conversions for an item, ordered by id for stable output. The item must
    exist (404 otherwise). The set is small (a handful of alternates per item), so it is returned
    whole rather than paginated."""
    await get_item(session, tenant_id, item_id)
    stmt = (
        select(UomConversion)
        .where(UomConversion.tenant_id == tenant_id, UomConversion.item_id == item_id)
        .order_by(UomConversion.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_conversion_factors(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Map of alt_uom_id -> factor_to_base for an item (PLAN 5.1). The base UoM maps to factor 1.
    Loaded once so ``convert_quantity`` is a pure function over the resulting table — the shape
    stock moves (5.2+) reuse when converting a document line's UoM to the item's base."""
    item = await get_item(session, tenant_id, item_id)
    conversions = await list_conversions(session, tenant_id, item_id)
    factors: dict[uuid.UUID, Decimal] = {item.base_uom_id: Decimal(1)}
    for conversion in conversions:
        factors[conversion.alt_uom_id] = Decimal(str(conversion.factor_to_base))
    return factors


def convert_quantity(
    quantity: Decimal,
    from_uom_id: uuid.UUID,
    to_uom_id: uuid.UUID,
    base_uom_id: uuid.UUID,
    factors: dict[uuid.UUID, Decimal],
) -> Decimal:
    """Convert ``quantity`` from ``from_uom_id`` to ``to_uom_id`` for one item — PURE (no I/O), so
    it is fully unit-testable and reused by stock moves later (PLAN 5.2+).

    Convention: ``factors[u]`` is u's factor-to-base (base maps to 1). A quantity in any UoM ``u``
    equals ``quantity * factors[u]`` base units; dividing by the target's factor lands it in the
    target UoM. So base<->alt and alt<->alt both fall out of the single per-alternate factor:
    ``to_qty = quantity * factors[from] / factors[to]``. Result quantizes to scale 6 (QuantityType
    storage, D-015). An unknown UoM for this item raises — conversions are per item, so a UoM with
    no factor is not convertible against this item."""
    for uom_id in (from_uom_id, to_uom_id):
        if uom_id not in factors:
            raise ValidationFailedError(
                message="No conversion is defined for this UoM on the item",
                code="inventory.conversion_undefined",
                details={"uom_id": str(uom_id), "base_uom_id": str(base_uom_id)},
            )
    if from_uom_id == to_uom_id:
        return Decimal(quantity).quantize(_QUANTITY_QUANTUM)
    base_quantity = Decimal(quantity) * factors[from_uom_id]
    return (base_quantity / factors[to_uom_id]).quantize(_QUANTITY_QUANTUM)

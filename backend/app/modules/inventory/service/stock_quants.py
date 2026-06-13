"""Quant maintenance + lot/serial resolution for the stock-move engine (PLAN 5.2, D-036).

This file owns the side-effect helpers ``create_move`` orchestrates, kept separate so
``stock_moves.py`` stays the readable orchestration and both stay under the STRUCTURE §3 cap:

- ``apply_bin_delta``: increment/decrement ONE (item, bin, lot) quant in the SAME transaction as
  the move. A decrement that would go negative raises InsufficientStockError BEFORE writing (the
  pre-flight half of D-020's no-negative-stock rule; the ``CHECK (on_hand_qty >= 0)`` is the DB
  backstop). Uses ``with_for_update`` to take the row lock on Postgres (serializing concurrent
  movers); on SQLite the dialect OMITS the clause (a no-op, not an error — D-020) and the
  single-writer lock serializes. A quant that reaches exactly 0 is DELETED so the projection holds
  only live stock and ``on_hand_by_bin`` never lists empty bins.

- ``resolve_lot`` / ``resolve_serial``: turn a move's lot/serial intent into a master-row id,
  CREATING the master instance on a RECEIPT (5.1 deferred instance creation to receipts) and
  REQUIRING it to already exist with stock on an ISSUE/TRANSFER.

Deadlock avoidance (D-020): a transfer touches two quant rows; the move engine locks them in a
deterministic order (it computes from/to deltas and calls ``apply_bin_delta`` for the lower bin id
first) so two concurrent movers never lock the same pair in opposite orders.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.modules.inventory.constants import LotStatus, SerialStatus, TrackingMode
from app.modules.inventory.models import Item, Lot, SerialNumber, StockQuant


class InsufficientStockError(ValidationFailedError):
    """A move would drive an (item, bin, lot) on-hand below zero (D-020: negative stock forbidden).
    422 ``inventory.insufficient_stock`` — the pre-flight service check; the ``CHECK (on_hand_qty
    >= 0)`` on inv_stock_quants is the DB backstop that fires if the service check is bypassed."""

    def __init__(
        self,
        *,
        item_id: uuid.UUID,
        bin_id: uuid.UUID,
        requested: Decimal,
        available: Decimal,
    ) -> None:
        super().__init__(
            message="Insufficient stock to issue from this bin",
            code="inventory.insufficient_stock",
            details={
                "item_id": str(item_id),
                "bin_id": str(bin_id),
                "requested": str(requested),
                "available": str(available),
            },
        )


async def _locked_quant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    bin_id: uuid.UUID,
    lot_id: uuid.UUID | None,
) -> StockQuant | None:
    """Load the (item, bin, lot) quant row FOR UPDATE, or None if it does not exist yet. The
    ``with_for_update`` takes the row lock on Postgres (D-020 concurrency path); SQLite omits it as
    a no-op. ``lot_id IS NULL`` is matched explicitly (a NULL lot is the fungible-stock quant)."""
    stmt = (
        select(StockQuant)
        .where(
            StockQuant.tenant_id == tenant_id,
            StockQuant.item_id == item_id,
            StockQuant.bin_id == bin_id,
            StockQuant.lot_id.is_(lot_id) if lot_id is None else StockQuant.lot_id == lot_id,
        )
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def apply_bin_delta(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    bin_id: uuid.UUID,
    lot_id: uuid.UUID | None,
    delta: Decimal,
) -> None:
    """Add ``delta`` (signed) to the (item, bin, lot) quant in this transaction (D-036). A positive
    delta upserts/increments; a negative delta decrements and raises InsufficientStockError if the
    result would be < 0 (pre-flight, before any write). A row reaching exactly 0 is deleted. Locks
    the row FOR UPDATE first (PG serialization; SQLite no-op, D-020)."""
    quant = await _locked_quant(session, tenant_id, item_id, bin_id, lot_id)
    current = Decimal(quant.on_hand_qty) if quant is not None else Decimal(0)
    new_qty = current + delta
    if new_qty < 0:
        raise InsufficientStockError(
            item_id=item_id, bin_id=bin_id, requested=-delta, available=current
        )
    if quant is None:
        session.add(
            StockQuant(
                tenant_id=tenant_id,
                item_id=item_id,
                bin_id=bin_id,
                lot_id=lot_id,
                on_hand_qty=new_qty,
            )
        )
    elif new_qty == 0:
        await session.delete(quant)
    else:
        quant.on_hand_qty = new_qty
    await session.flush()


async def resolve_lot(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item: Item,
    *,
    lot_id: uuid.UUID | None,
    lot_code: str | None,
    create_if_missing: bool,
) -> uuid.UUID | None:
    """Resolve the lot a move applies to (PLAN 5.2). For a LOT-tracked item a lot is REQUIRED (by
    id, or by a new ``lot_code`` on a receipt when ``create_if_missing``). For an untracked item a
    lot is forbidden. Returns the lot id (None for untracked). Creating happens only on a receipt —
    an ISSUE/TRANSFER must reference an existing lot (its stock is then checked by the quant)."""
    tracking = TrackingMode(item.tracking_mode)
    if tracking != TrackingMode.LOT:
        if lot_id is not None or lot_code is not None:
            raise ValidationFailedError(
                message="This item is not lot-tracked; a lot must not be supplied",
                code="inventory.lot_not_applicable",
                details={"item_id": str(item.id)},
            )
        return None

    if lot_id is not None:
        lot = await session.get(Lot, lot_id)
        if lot is None or lot.tenant_id != tenant_id or lot.item_id != item.id:
            raise ValidationFailedError(
                message="The referenced lot does not exist for this item",
                code="inventory.lot_not_found",
                details={"lot_id": str(lot_id)},
            )
        return lot.id
    if lot_code is not None and create_if_missing:
        return await _get_or_create_lot(session, tenant_id, item.id, lot_code)
    raise ValidationFailedError(
        message="A lot is required for this lot-tracked item",
        code="inventory.lot_required",
        details={"item_id": str(item.id)},
    )


async def _get_or_create_lot(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, lot_code: str
) -> uuid.UUID:
    existing = (
        await session.execute(
            select(Lot).where(
                Lot.tenant_id == tenant_id, Lot.item_id == item_id, Lot.lot_code == lot_code
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    lot = Lot(
        tenant_id=tenant_id,
        item_id=item_id,
        lot_code=lot_code,
        status=LotStatus.AVAILABLE.value,
        received_at=datetime.now(UTC),
    )
    session.add(lot)
    await session.flush()
    return lot.id


async def resolve_serial(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item: Item,
    *,
    serial_id: uuid.UUID | None,
    serial_code: str | None,
    create_if_missing: bool,
) -> uuid.UUID | None:
    """Resolve the serial a move applies to (PLAN 5.2). For a SERIAL-tracked item a serial is
    REQUIRED (by id, or a new ``serial_code`` on a receipt); for an untracked item it is forbidden.
    A serial moves wholesale (the caller enforces quantity == 1). Returns the serial id (None for
    untracked). Creating happens only on a receipt."""
    tracking = TrackingMode(item.tracking_mode)
    if tracking != TrackingMode.SERIAL:
        if serial_id is not None or serial_code is not None:
            raise ValidationFailedError(
                message="This item is not serial-tracked; a serial must not be supplied",
                code="inventory.serial_not_applicable",
                details={"item_id": str(item.id)},
            )
        return None

    if serial_id is not None:
        serial = await session.get(SerialNumber, serial_id)
        if serial is None or serial.tenant_id != tenant_id or serial.item_id != item.id:
            raise ValidationFailedError(
                message="The referenced serial does not exist for this item",
                code="inventory.serial_not_found",
                details={"serial_id": str(serial_id)},
            )
        return serial.id
    if serial_code is not None and create_if_missing:
        return await _get_or_create_serial(session, tenant_id, item.id, serial_code)
    raise ValidationFailedError(
        message="A serial number is required for this serial-tracked item",
        code="inventory.serial_required",
        details={"item_id": str(item.id)},
    )


async def _get_or_create_serial(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, serial_code: str
) -> uuid.UUID:
    existing = (
        await session.execute(
            select(SerialNumber).where(
                SerialNumber.tenant_id == tenant_id,
                SerialNumber.item_id == item_id,
                SerialNumber.serial_code == serial_code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    serial = SerialNumber(
        tenant_id=tenant_id,
        item_id=item_id,
        serial_code=serial_code,
        status=SerialStatus.IN_STOCK.value,
        received_at=datetime.now(UTC),
    )
    session.add(serial)
    await session.flush()
    return serial.id

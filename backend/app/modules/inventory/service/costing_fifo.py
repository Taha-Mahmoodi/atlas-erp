"""FIFO costing mechanics (PLAN 5.3, D-020): create layers on receipt, consume oldest-first on
issue, replay consumptions backward on reversal. Split from ``costing.py`` to keep both <400 lines.

The moving-average engine and the orchestration live in ``costing.py``; this file owns ONLY the
layer-table reads/writes so the two halves stay readable. Every function runs in the move's
transaction; the consumption scan locks layers ``with_for_update`` (PG row lock serializing
concurrent issuers; SQLite no-op + single-writer lock, D-020).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.money import quantize_for_currency
from app.modules.inventory.models import CostLayer, LayerConsumption


async def create_layer(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    receipt_move_id: uuid.UUID,
    received_at: date,
    qty: Decimal,
    unit_cost: Decimal,
) -> CostLayer:
    """Create a FIFO layer for a RECEIPT (D-020): original_qty == remaining_qty == qty at unit_cost.
    Flushed so its id exists for the consumption/reversal links."""
    layer = CostLayer(
        tenant_id=tenant_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        receipt_move_id=receipt_move_id,
        received_at=received_at,
        original_qty=qty,
        remaining_qty=qty,
        unit_cost=unit_cost,
    )
    session.add(layer)
    await session.flush()
    return layer


async def consume_layers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    issue_move_id: uuid.UUID,
    qty: Decimal,
    currency_code: str,
) -> Decimal:
    """Consume ``qty`` from the (item, warehouse) FIFO layers oldest-first (D-020), writing one
    LayerConsumption per touched layer and decrementing its remaining_qty. Returns the COGS =
    Σ per-layer ``quantize(qty_from_layer × unit_cost)`` (HALF_UP at the currency's decimals,
    D-015).

    The issue quantity is guaranteed available by the 5.2 quant pre-flight (no negative stock,
    D-020),
    so the layers must cover it; if a costing/quant divergence ever left them short this raises
    rather
    than under-cost. Layers are locked ``with_for_update`` in (received_at, id) order (FIFO +
    deadlock
    avoidance, D-020)."""
    remaining_to_consume = qty
    cogs = Decimal(0)
    stmt = (
        select(CostLayer)
        .where(
            CostLayer.tenant_id == tenant_id,
            CostLayer.item_id == item_id,
            CostLayer.warehouse_id == warehouse_id,
            CostLayer.remaining_qty > 0,
        )
        # FIFO order: by received_at, then created_at (each receipt is its own transaction, so
        # created_at strictly increases between receipts and is the insertion-order tiebreaker when
        # received_at ties — uuid4 ids are not monotonic), then id as the final deterministic break.
        .order_by(CostLayer.received_at.asc(), CostLayer.created_at.asc(), CostLayer.id.asc())
        .with_for_update()
    )
    layers = (await session.execute(stmt)).scalars().all()
    for layer in layers:
        if remaining_to_consume <= 0:
            break
        take = min(Decimal(layer.remaining_qty), remaining_to_consume)
        line_cost = quantize_for_currency(take * Decimal(layer.unit_cost), currency_code)
        session.add(
            LayerConsumption(
                tenant_id=tenant_id,
                issue_move_id=issue_move_id,
                layer_id=layer.id,
                qty=take,
                cost=line_cost,
            )
        )
        layer.remaining_qty = Decimal(layer.remaining_qty) - take
        cogs += line_cost
        remaining_to_consume -= take
    await session.flush()
    if remaining_to_consume > 0:
        # The quant said the stock was there but the layers did not cover it — a costing/quant
        # divergence, never reachable on the happy path (5.2 forbids negative stock).
        raise ValidationFailedError(
            message="FIFO layers do not cover the issued quantity",
            code="inventory.costing_layers_short",
            details={
                "item_id": str(item_id),
                "warehouse_id": str(warehouse_id),
                "shortfall": str(remaining_to_consume),
            },
        )
    return cogs


async def reverse_issue_consumptions(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    original_issue_move_id: uuid.UUID,
    currency_code: str,
) -> Decimal:
    """Replay an issue's LayerConsumption rows BACKWARD onto the exact layers (D-020): add each
    consumed ``qty`` back to its layer's remaining_qty, restoring the precise FIFO state. Returns
    the
    restored COGS (Σ stored consumption ``cost``) so the reversing move records the same value it
    undoes. The consumption rows are append-only (kept as the audit trail); the reversal is replay,
    never recompute."""
    consumptions = (
        await session.execute(
            select(LayerConsumption).where(
                LayerConsumption.tenant_id == tenant_id,
                LayerConsumption.issue_move_id == original_issue_move_id,
            )
        )
    ).scalars().all()
    restored = Decimal(0)
    for consumption in consumptions:
        layer = await session.get(CostLayer, consumption.layer_id)
        if layer is None or layer.tenant_id != tenant_id:
            raise ConflictError(
                message="The consumed cost layer no longer exists",
                code="inventory.costing_layer_missing",
            )
        layer.remaining_qty = Decimal(layer.remaining_qty) + Decimal(consumption.qty)
        restored += Decimal(consumption.cost)
    await session.flush()
    return restored


async def reverse_receipt_layer(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    original_receipt_move_id: uuid.UUID,
) -> Decimal:
    """Remove the FIFO layer a RECEIPT created (D-020) — only valid while it is UNCONSUMED (still
    full). A partly/fully consumed layer cannot be reversed (the stock it backed has already left;
    reverse the issues first), so this raises rather than corrupt the FIFO history. Returns the
    layer's value (original_qty × unit_cost) so the reversing move records what it removes."""
    layer = (
        await session.execute(
            select(CostLayer).where(
                CostLayer.tenant_id == tenant_id,
                CostLayer.receipt_move_id == original_receipt_move_id,
            )
        )
    ).scalar_one_or_none()
    if layer is None:
        raise ConflictError(
            message="The receipt has no cost layer to reverse",
            code="inventory.costing_layer_missing",
        )
    if Decimal(layer.remaining_qty) != Decimal(layer.original_qty):
        raise ConflictError(
            message="Cannot reverse a receipt whose stock has already been consumed",
            code="inventory.receipt_layer_consumed",
            details={
                "remaining_qty": str(layer.remaining_qty),
                "original_qty": str(layer.original_qty),
            },
        )
    value = Decimal(layer.original_qty) * Decimal(layer.unit_cost)
    await session.delete(layer)
    await session.flush()
    return value


__all__ = [
    "consume_layers",
    "create_layer",
    "reverse_issue_consumptions",
    "reverse_receipt_layer",
]

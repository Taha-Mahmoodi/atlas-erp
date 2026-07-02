"""Inventory VALUATION tables — the value single source of truth (PLAN 5.3, D-020/D-037).

The move ledger (``inv_stock_moves``) and the quant projection (``inv_stock_quants``) remain the
QUANTITY SSOT; these three tables are the VALUE SSOT, updated in the SAME transaction as every move
(D-037). Which engine a (item, warehouse) uses is the item's ``costing_method``:

- ``ItemValuation`` (``inv_item_valuations``) — the MOVING-AVERAGE state per (item, warehouse):
  on_hand_qty, avg_unit_cost (full precision) and total_value, with ``UNIQUE(tenant, item,
  warehouse)`` as the upsert/lock target and ``CHECK(on_hand_qty >= 0)`` (value and quantity never
  disagree — the zero-quantity flush keeps total_value at 0 exactly when on_hand hits 0, D-020).
- ``CostLayer`` (``inv_cost_layers``) — one FIFO layer per RECEIPT: original_qty, remaining_qty
  (``CHECK 0 <= remaining_qty <= original_qty``) and unit_cost, keyed back to its
  ``receipt_move_id`` and ordered by ``received_at`` then id. Issues consume the oldest first.
- ``LayerConsumption`` (``inv_layer_consumptions``) — one row per layer an ISSUE touches: qty +
  cost. The audit trail AND the exact-reversal record (reversing an issue replays these rows
  backward onto the same layers, restoring remaining_qty — D-020).

Valuation is per (item, WAREHOUSE), not per bin: transfers within one warehouse are value-neutral
(no journal), while a transfer BETWEEN warehouses moves value with the stock (D-037). All tables
follow the D-007 composite-tenant-FK backstop (``tenant_unique()`` + ``tenant_fk()`` composites) so
a child can never point at another tenant's parent. Enum-free; money/quantity are MoneyType/
QuantityType (exact on both engines, D-015). NOT AuditMixin — valuation is a derived projection of
the audited moves (the quant-table reasoning, D-036); auditing it too would double-record.
"""

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import MoneyType, QuantityType


class ItemValuation(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """The MOVING-AVERAGE valuation state per (item, warehouse) (D-020/D-037).

    Maintained in the move transaction under ``with_for_update`` (PG row lock serializing concurrent
    movers; SQLite no-op + single-writer lock, D-020): a RECEIPT adds ``qty × unit_cost`` to
    total_value and recomputes ``avg_unit_cost = total_value / on_hand_qty`` UNROUNDED (full scale-6
    precision, so successive issues don't drift); an ISSUE subtracts ``quantize(qty × avg)`` and,
    when on_hand_qty reaches exactly 0, FLUSHES the residual total_value to the price-difference
    account so value and quantity never disagree. The ``CHECK(on_hand_qty >= 0)`` backs the
    no-negative-stock rule on the value side (D-020). ``UNIQUE(tenant, item, warehouse)`` is the
    upsert + lock target."""

    __tablename__ = "inv_item_valuations"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "item_id",
            "warehouse_id",
            name="uq_inv_item_valuations_tenant_id_item_id_warehouse_id",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("inv_items", "item_id"),
        tenant_fk("inv_warehouses", "warehouse_id"),
        # Negative on-hand forbidden on the value side too (D-020) — portable single-column CHECK.
        sa.CheckConstraint("on_hand_qty >= 0", name="on_hand_non_negative"),
        sa.Index(
            "ix_inv_item_valuations_tenant_id_item_id", "tenant_id", "item_id"
        ),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    on_hand_qty: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    # Full-precision average (D-015: MoneyType keeps scale 6) — never quantized to currency dp, so
    # repeated issues do not accumulate rounding drift; only the POSTED COGS rounds (zero-qty
    # flush).
    avg_unit_cost: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)


class CostLayer(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """A FIFO cost layer (D-020): one per RECEIPT (or positive ADJUSTMENT) into a (item, warehouse).

    Created with ``original_qty == remaining_qty == qty`` at the receipt's ``unit_cost``; issues
    consume layers oldest-first by ``(received_at, id)`` under ``with_for_update``, decrementing
    ``remaining_qty``. The ``CHECK(remaining_qty >= 0 AND remaining_qty <= original_qty)`` makes a
    layer's consumed amount well-defined on both engines (D-020). ``receipt_move_id`` is a
    composite tenant FK back to the move that created it, so reversing that RECEIPT can find and
    zero its layer (only valid while the layer is unconsumed). The
    ``(tenant, item, warehouse, received_at)`` index serves the FIFO consumption scan
    (PERFORMANCE §1)."""

    __tablename__ = "inv_cost_layers"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("inv_items", "item_id"),
        tenant_fk("inv_warehouses", "warehouse_id"),
        tenant_fk("inv_stock_moves", "receipt_move_id"),
        sa.CheckConstraint(
            "remaining_qty >= 0 AND remaining_qty <= original_qty",
            name="remaining_within_original",
        ),
        # The FIFO consumption scan reads a (item, warehouse)'s layers oldest-first (PERF §1).
        sa.Index(
            "ix_inv_cost_layers_tenant_id_item_id_warehouse_id_received_at",
            "tenant_id",
            "item_id",
            "warehouse_id",
            "received_at",
        ),
        # FK index for "this receipt move's layer" (the receipt-reversal lookup).
        sa.Index(
            "ix_inv_cost_layers_tenant_id_receipt_move_id",
            "tenant_id",
            "receipt_move_id",
        ),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    receipt_move_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Date the layer was received — the FIFO ordering key (id breaks same-date ties). A Date (not
    # datetime) suffices: ordering is (received_at, id) and id is the within-day tiebreaker.
    received_at: Mapped[date] = mapped_column(sa.Date, nullable=False)
    original_qty: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    remaining_qty: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)


class LayerConsumption(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One layer an ISSUE consumed (D-020): qty drawn from the layer + the cost charged for it.

    One row per (issue_move, layer) touched — the per-layer COGS audit trail AND the exact-reversal
    record: reversing an issue replays these rows backward, ADDING ``qty`` back to each named
    layer's remaining_qty (restoring the exact FIFO state), so a reversal is replay, never recompute
    (D-020).
    Composite tenant FKs to both the issue move and the layer keep the link tenant-safe."""

    __tablename__ = "inv_layer_consumptions"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("inv_stock_moves", "issue_move_id"),
        tenant_fk("inv_cost_layers", "layer_id"),
        # "This issue's consumptions" (reversal replay) and "this layer's consumptions" — both
        # FK-indexed (PERFORMANCE §1).
        sa.Index(
            "ix_inv_layer_consumptions_tenant_id_issue_move_id",
            "tenant_id",
            "issue_move_id",
        ),
        sa.Index(
            "ix_inv_layer_consumptions_tenant_id_layer_id", "tenant_id", "layer_id"
        ),
    )

    issue_move_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    layer_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    qty: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    cost: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)


__all__ = ["CostLayer", "ItemValuation", "LayerConsumption"]

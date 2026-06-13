"""Inventory stock topology + the move ledger + the maintained on-hand projection (PLAN 5.2).

This file owns the four STOCK tables (the master tables live in ``models/masters.py``):

- ``Warehouse`` / ``Bin``: the storage topology. A bin belongs to a warehouse; on-hand is tracked
  PER BIN. Both are reference data (codes, not gapless numbers).
- ``StockMove`` (``inv_stock_moves``): the quantity SINGLE SOURCE OF TRUTH (D-020). One append-only
  ledger row per movement, POSTED at creation and IMMUTABLE — corrections are reversing moves,
  never edits (the universal-journal philosophy of D-017 applied to stock). Quantity is ALWAYS
  POSITIVE; the ``move_type`` decides which of from_bin/to_bin participate (the direction), so no
  signed column is needed (constants.MOVE_BIN_SIDES). Carries DocumentMixin (registered in
  core_documents) and a gapless STK number claimed at creation (D-012 claim-at-permanence — a move
  is permanent at create).
- ``StockQuant`` (``inv_stock_quants``): the MAINTAINED PROJECTION of the move ledger — current
  on-hand per (item, bin, lot). Updated in the SAME transaction as every move (the moving-average
  ``inv_item_valuations`` precedent, D-020), so on-hand reads are an indexed point-lookup, not an
  unbounded SUM over history (PERFORMANCE §1). The ledger stays the SSOT/audit trail; the quant is
  reconcilable from it. A DB ``CHECK (on_hand_qty >= 0)`` plus a pre-flight service check forbid
  negative stock outright (D-020) — both engines (a single-column CHECK is portable, D-022).
  Recorded as DECISIONS.md D-036.

Indexes (PERFORMANCE §1) are declared so the on-hand sums and the move-ledger filters are
index-served: moves index (tenant, item, to_bin), (tenant, item, from_bin), (tenant, move_date) and
(tenant, item); quants index (tenant, item) on top of the natural-key UNIQUE.

Enum-valued columns are plain ``sa.String`` storing the StrEnum's UPPER_SNAKE value (the
core/finance/masters convention); the service maps to/from the constants classes. Every table
follows the D-007 composite-tenant-FK backstop (``tenant_unique()`` + ``tenant_fk()`` composites).
"""

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.docflow import DocumentMixin, document_fk
from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import MoneyType, QuantityType


class Warehouse(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A physical or logical stock location grouping bins (parity: plant/storage location).
    ``code`` is user-supplied and unique per tenant. ``is_active`` deactivates a warehouse instead
    of deleting it (a warehouse referenced by moves/quants must never disappear — the soft-delete
    convention). Audited (D-010): topology is master data. ``tenant_unique()`` so bins can reference
    it via the composite tenant FK."""

    __tablename__ = "inv_warehouses"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_inv_warehouses_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )


class Bin(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A storage bin within a warehouse — the granularity on-hand is tracked at (parity: storage
    bin). ``warehouse_id`` is a composite tenant FK to inv_warehouses (a bin can never belong to
    another tenant's warehouse). ``code`` is unique per (tenant, warehouse) — two warehouses may
    both have a bin "A1". ``is_default`` marks the warehouse's default receiving bin (a receipt that
    names only a warehouse can resolve to it later); exactly-one-default-per-warehouse is a service
    convention, not a DB constraint (a partial unique index is a later optimisation). ``is_active``
    deactivates instead of deleting. Audited (D-010)."""

    __tablename__ = "inv_bins"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "warehouse_id", "code", name="uq_inv_bins_tenant_id_warehouse_id_code"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("inv_warehouses", "warehouse_id"),
        # FK index for "this warehouse's bins" — the bins-list-by-warehouse read path.
        sa.Index("ix_inv_bins_tenant_id_warehouse_id", "tenant_id", "warehouse_id"),
    )

    warehouse_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    is_default: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )


class StockMove(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """The quantity SINGLE SOURCE OF TRUTH (D-020): one append-only ledger row per stock movement.

    POSTED at creation and IMMUTABLE — a move is never edited or deleted; a correction is a NEW
    reversing move linked via docflow (the D-017 reversal philosophy applied to stock). ``quantity``
    is ALWAYS POSITIVE; ``move_type`` (constants.MoveType) decides which of ``from_bin_id`` /
    ``to_bin_id`` participate (constants.MOVE_BIN_SIDES) — so direction is structural, not a sign.
    ``quantity`` is stored in the item's BASE UoM (``base_uom_id`` records which, frozen on the move
    so a later UoM change can't reinterpret history). ``lot_id`` / ``serial_id`` carry batch/serial
    identity for tracked items (NULL for fungible). ``reference`` is a free-text link to the driving
    document description (a real docflow link lands when receipts/issues drive moves, 6.x/5.3).

    DocumentMixin registers the move in core_documents; the gapless STK number is claimed AT
    CREATION (D-012 claim-at-permanence — a move is permanent the moment it exists, the
    orders/receipts branch). Audited (D-010): every quantity change is auditable. Indexes per
    PERFORMANCE §1 so the quant maintenance lookups and the ledger filters are index-served."""

    __tablename__ = "inv_stock_moves"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("inv_items", "item_id"),
        tenant_fk("inv_uoms", "base_uom_id"),
        # from_bin / to_bin are both composite tenant FKs to inv_bins. The D-022 column-0 convention
        # would name both identically (collision), so spell out distinct names (the journal
        # self-FK precedent) — they must match migration 0021 exactly.
        sa.ForeignKeyConstraint(
            ["tenant_id", "from_bin_id"],
            ["inv_bins.tenant_id", "inv_bins.id"],
            name="fk_inv_stock_moves_from_bin_id_inv_bins",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "to_bin_id"],
            ["inv_bins.tenant_id", "inv_bins.id"],
            name="fk_inv_stock_moves_to_bin_id_inv_bins",
        ),
        tenant_fk("inv_lots", "lot_id"),
        tenant_fk("inv_serials", "serial_id"),
        # On-hand maintenance + ledger reads filter by item + bin and by date (PERFORMANCE §1):
        # the (tenant, item, to_bin) / (tenant, item, from_bin) indexes serve per-bin lookups, the
        # (tenant, move_date) index serves the ledger date filter, and (tenant, item) the
        # per-item ledger view.
        sa.Index(
            "ix_inv_stock_moves_tenant_id_item_id_to_bin_id",
            "tenant_id",
            "item_id",
            "to_bin_id",
        ),
        sa.Index(
            "ix_inv_stock_moves_tenant_id_item_id_from_bin_id",
            "tenant_id",
            "item_id",
            "from_bin_id",
        ),
        sa.Index("ix_inv_stock_moves_tenant_id_move_date", "tenant_id", "move_date"),
        sa.Index("ix_inv_stock_moves_tenant_id_item_id", "tenant_id", "item_id"),
    )

    move_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    move_type: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    base_uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    from_bin_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    to_bin_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    serial_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    move_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    reference: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    posted: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    # The costing input/output (PLAN 5.3, D-020): the value at which stock enters (REQUIRED on a
    # RECEIPT / positive ADJUSTMENT — the entry cost) or the value the costing engine COMPUTED for
    # the stock that left (ISSUE / negative ADJUSTMENT — moving-average or summed FIFO layers). A
    # TRANSFER carries the current valuation (value-neutral within one inventory account). NULLABLE
    # at the column level because pre-5.3 moves had none and the engine fills it; full scale-6
    # MoneyType so unit costs keep precision (D-015) — only the POSTED COGS rounds to currency dp.
    unit_cost: Mapped[Decimal | None] = mapped_column(MoneyType(), nullable=True)


class StockQuant(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """The MAINTAINED on-hand projection of the move ledger (D-036): current quantity per
    (item, bin, lot). Updated in the SAME transaction as every move (decrement from_bin, increment
    to_bin) so on-hand is an indexed point lookup, not an unbounded SUM over history (PERFORMANCE
    §1) — the moving-average ``inv_item_valuations`` precedent (D-020). The move ledger stays the
    SSOT; the quant is reconcilable from it.

    ``lot_id`` is part of the natural key (NULL for fungible/untracked stock — the same item+bin can
    hold several lots, each its own quant row). The ``CHECK (on_hand_qty >= 0)`` is the DB backstop
    behind the service's pre-flight InsufficientStockError, banning negative stock on BOTH engines
    (D-020; a single-column CHECK is portable, D-022). NOT AuditMixin: the quant is a derived
    projection, not independent business state — the MOVES that change it are audited, so auditing
    the projection too would double-record (the same reasoning core applies to derived/control
    tables). ``UNIQUE(tenant, item, bin, lot)`` is the upsert target; ``(tenant, item)`` indexes the
    total-on-hand aggregate."""

    __tablename__ = "inv_stock_quants"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "item_id",
            "bin_id",
            "lot_id",
            name="uq_inv_stock_quants_tenant_id_item_id_bin_id_lot_id",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("inv_items", "item_id"),
        tenant_fk("inv_bins", "bin_id"),
        tenant_fk("inv_lots", "lot_id"),
        # Bare token (D-022 ck convention wraps it -> ck_inv_stock_quants_on_hand_non_negative).
        # Negative stock forbidden outright (D-020) — exact on both engines (a single-column
        # comparison on the stored representation: NUMERIC on PG, micro-unit INTEGER on SQLite).
        sa.CheckConstraint("on_hand_qty >= 0", name="on_hand_non_negative"),
        # Total-on-hand-for-an-item aggregate (sum across bins/lots) index-served (PERFORMANCE §1).
        sa.Index("ix_inv_stock_quants_tenant_id_item_id", "tenant_id", "item_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    bin_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    on_hand_qty: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)

    # The datetime import is used by the inherited TimestampMixin's mapped columns at class build;
    # referencing it here is unnecessary but the annotation imports above keep ruff/mypy aligned.


__all__ = ["Bin", "StockMove", "StockQuant", "Warehouse"]

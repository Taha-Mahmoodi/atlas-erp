"""Physical & cycle count tables (PLAN 5.4, D-038): the count document + its per-quant lines.

A count captures the team's COUNTED quantity per (item, bin, lot), compares it to system on-hand and
posts the differences as stock ADJUSTMENT moves (which flow through the 5.3 costing engine into the
price-difference journal). This file owns the two COUNT tables:

- ``StockCount`` (``inv_stock_counts``): the count document. Carries DocumentMixin (registered in
  core_documents) and a gapless CNT number claimed at creation (D-012 claim-at-permanence — the
  number is the stable handle the warehouse team references while counting). Audited (D-010): a
  count is real business state, not a derived projection.
- ``StockCountLine`` (``inv_stock_count_lines``): one line per (item, bin, lot) in scope.
  ``system_qty`` is the on-hand SNAPSHOT captured when the line is created/recounted;
  ``counted_qty`` is what the team counted (NULL until counted); ``variance_qty`` (counted − live)
  and
  ``adjustment_move_id`` + ``unit_cost`` are filled AT POST. The line is NOT AuditMixin — the count
  document is audited and the ADJUSTMENT move each line generates is itself audited, so auditing the
  lines too would double-record (the StockQuant/derived-table reasoning, D-036).

The ``system_qty`` snapshot is a convenience for the variance PREVIEW only; ``post_count`` RE-READS
live on-hand at post time (concurrency safety, D-038), so a stale snapshot can never post a wrong
variance. Every table follows the D-007 composite-tenant-FK backstop (``tenant_unique()`` +
``tenant_fk()`` composites).
"""

import uuid
from datetime import date, datetime
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


class StockCount(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A physical or cycle count of a warehouse (PLAN 5.4, D-038). DocumentMixin registers it in
    core_documents; the gapless CNT number is claimed AT CREATION (D-012 claim-at-permanence — a
    count is a referenced document from the moment it exists). ``count_type`` (constants.CountType)
    decides PHYSICAL (whole-warehouse snapshot) vs CYCLE (a chosen items/bins subset); ``status``
    walks DRAFT→COUNTING→POSTED (terminal) | CANCELLED. ``warehouse_id`` is a composite tenant FK to
    inv_warehouses (a count can never target another tenant's warehouse). ``count_date`` is the
    posting date the variance ADJUSTMENT moves use — a closed-period date trips the period trigger
    via the adjustment's journal and rolls the whole post back. Audited (D-010)."""

    __tablename__ = "inv_stock_counts"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("inv_warehouses", "warehouse_id"),
        # The list filters by status + warehouse + type (PERFORMANCE §1); (tenant, warehouse) and
        # (tenant, status) serve those filters index-served.
        sa.Index("ix_inv_stock_counts_tenant_id_warehouse_id", "tenant_id", "warehouse_id"),
        sa.Index("ix_inv_stock_counts_tenant_id_status", "tenant_id", "status"),
    )

    count_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    count_type: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    count_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class StockCountLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One count line per (item, bin, lot) in scope (PLAN 5.4, D-038). ``system_qty`` is the on-hand
    SNAPSHOT captured at line creation/recount (the preview baseline); ``counted_qty`` is the team's
    count (NULL until recorded). AT POST the service re-reads LIVE on-hand and stores
    ``variance_qty`` (counted − live-system), the ``adjustment_move_id`` of the ADJUSTMENT move it
    generated (NULL when variance is zero — no move) and the ``unit_cost`` used for that adjustment.

    NOT AuditMixin: the parent count is audited and each generated ADJUSTMENT move is itself
    audited, so auditing the lines would double-record (D-036 derived-table reasoning).
    ``UNIQUE(tenant,
    count, item, bin, lot)`` makes each (item, bin, lot) appear once per count; ``(tenant, count)``
    indexes the lines-of-a-count read."""

    __tablename__ = "inv_stock_count_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "count_id",
            "item_id",
            "bin_id",
            "lot_id",
            name="uq_inv_stock_count_lines_tenant_id_count_id_item_id_bin_id_lot",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("inv_stock_counts", "count_id"),
        tenant_fk("inv_items", "item_id"),
        tenant_fk("inv_bins", "bin_id"),
        tenant_fk("inv_lots", "lot_id"),
        tenant_fk("inv_stock_moves", "adjustment_move_id"),
        sa.Index("ix_inv_stock_count_lines_tenant_id_count_id", "tenant_id", "count_id"),
    )

    count_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    bin_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    system_qty: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    counted_qty: Mapped[Decimal | None] = mapped_column(QuantityType(), nullable=True)
    variance_qty: Mapped[Decimal | None] = mapped_column(QuantityType(), nullable=True)
    adjustment_move_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(MoneyType(), nullable=True)


__all__ = ["StockCount", "StockCountLine"]

"""Goods receipts (PLAN 6.3): the ``GoodsReceipt`` header + ``GoodsReceiptLine``.

A goods receipt records the physical receipt of goods ordered on a PO. The header mixes in
``DocumentMixin`` and carries a gapless ``gr_number`` claimed at creation (D-040). It is built
DRAFT (a receiving clerk picks PO lines + target bins + quantities) and then POSTED: at POST the
stock RECEIPT moves are created (Dr Inventory / Cr GR-IR via the inventory costing event), the PO
lines' received_quantity rises, the PO advances PARTIALLY_RECEIVED/RECEIVED — all one transaction.

``purchase_order_id`` is a composite tenant FK to proc_purchase_orders (the GR is always against a
PO in v1). ``vendor_id`` is a SNAPSHOT of the PO's vendor (so reporting reads the vendor without
re-resolving the PO). ``warehouse_id`` is an OPAQUE inventory warehouse id (validated via
inventory/queries, never a cross-module FK — D-029); each line's ``bin_id`` is likewise an opaque
inventory bin id (where the stock lands).

Per D-041 the GR↔stock-move linkage is recorded via DOCFLOW (GR document → 'moved_by' → move
document), NOT a cross-module ``stock_move_id`` FK column — inventory owns the move, so a GR line
does not carry a foreign key into another module's table. ``requires_inspection`` is the v1
inspection FLAG only (Phase 9 adds the lot disposition); it flags the received line and does not
block downstream use.
"""

import uuid
from datetime import date, datetime

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
from app.modules.procurement.constants import GoodsReceiptStatus


class GoodsReceipt(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A goods-receipt header (PLAN 6.3). ``gr_number`` is claimed at creation (D-040).
    ``purchase_order_id`` is a composite tenant FK to proc_purchase_orders; ``vendor_id`` is a
    snapshot of the PO's vendor; ``warehouse_id`` is an OPAQUE inventory warehouse id (validated via
    inventory/queries — D-029). ``status`` runs the GoodsReceiptStatus lifecycle (DRAFT → POSTED;
    DRAFT → CANCELLED). ``posted_at`` records when the receipt committed. Audited (D-010)."""

    __tablename__ = "proc_goods_receipts"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("proc_purchase_orders", "purchase_order_id"),
        # PERFORMANCE §1: the GR list filters on (tenant, status) and a PO's receipts.
        sa.Index("ix_proc_goods_receipts_tenant_id_status", "tenant_id", "status"),
        sa.Index(
            "ix_proc_goods_receipts_tenant_id_purchase_order_id",
            "tenant_id",
            "purchase_order_id",
        ),
    )

    gr_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=GoodsReceiptStatus.DRAFT.value,
        server_default="DRAFT",
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Vendor snapshot from the PO at create (reporting reads the vendor without re-resolving PO).
    vendor_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Opaque inventory warehouse id (D-029) the receipt's stock lands in; each line's bin is in it.
    warehouse_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    receipt_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class GoodsReceiptLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One received item on a goods receipt (PLAN 6.3). ``purchase_order_line_id`` is a composite
    tenant FK to proc_purchase_order_lines (the line being received against). ``item_id`` is an
    OPAQUE inventory item id snapshot from the PO line; ``bin_id`` is an OPAQUE inventory bin id
    (where the stock lands — D-029, validated via inventory/queries). ``received_quantity`` is the
    quantity received on this line; ``unit_cost`` is the snapshot from the PO line (the value the
    stock enters inventory at). ``lot_code`` / ``serial_code`` (nullable) are passed to the stock
    move for lot/serial-tracked items. ``requires_inspection`` is the v1 inspection FLAG (Phase 9
    adds the disposition). UNIQUE(tenant_id, gr_id, line_number). NOT AuditMixin (header-line
    exclusion). No stock_move_id column — the GR↔move link is docflow (D-041)."""

    __tablename__ = "proc_goods_receipt_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "gr_id", "line_number", name="uq_proc_goods_receipt_lines_gr_line"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("proc_goods_receipts", "gr_id"),
        tenant_fk("proc_purchase_order_lines", "purchase_order_line_id"),
    )

    gr_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    purchase_order_line_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    bin_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    received_quantity: Mapped[object] = mapped_column(QuantityType(), nullable=False)
    unit_cost: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    lot_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    serial_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    requires_inspection: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )

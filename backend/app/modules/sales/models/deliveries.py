"""Outbound deliveries (PLAN 7.3): the ``Delivery`` header + ``DeliveryLine`` — the O2C fulfilment
document, the OUTBOUND TWIN of the procurement goods receipt (models/goods_receipts.py, mirrored).

A delivery records the physical shipment of goods against a CONFIRMED sales order. The header mixes
in ``DocumentMixin`` and carries a gapless ``delivery_number`` claimed at creation (D-040). It is
built DRAFT (a shipping clerk picks order lines + source bins + quantities) and then POSTED: at POST
the stock ISSUE moves are created (Dr COGS / Cr Inventory via the inventory costing event — COGS is
the DEFAULT ISSUE offset, no override), the order lines' delivered_quantity rises, the order
advances PARTIALLY_DELIVERED/DELIVERED — all one transaction.

``sales_order_id`` is a composite tenant FK to sales_orders (the delivery is always against an
order in v1). ``customer_id`` is a SNAPSHOT of the order's customer (so reporting reads the customer
without re-resolving the order — the GR vendor-snapshot precedent). ``warehouse_id`` is an OPAQUE
inventory warehouse id (validated via inventory/queries, never a cross-module FK — D-029); each
line's ``bin_id`` is likewise an opaque inventory bin id (where the stock is issued FROM).

Per D-041 the delivery↔stock-move linkage is recorded via DOCFLOW (delivery document → 'moved_by' →
move document), NOT a cross-module ``stock_move_id`` FK column — inventory owns the move, so a
delivery line does not carry a foreign key into another module's table (the goods-receipt
precedent).
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
from app.core.money import QuantityType
from app.modules.sales.constants import DeliveryStatus


class Delivery(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """An outbound-delivery header (PLAN 7.3). ``delivery_number`` is claimed at creation (D-040).
    ``sales_order_id`` is a composite tenant FK to sales_orders; ``customer_id`` is a snapshot of
    the order's customer; ``warehouse_id`` is an OPAQUE inventory warehouse id (validated via
    inventory/queries — D-029). ``status`` runs the DeliveryStatus lifecycle (DRAFT → POSTED; DRAFT
    → CANCELLED). ``shipping_address`` (nullable) is a free-text ship-to snapshot; ``posted_at``
    records when the shipment committed. Audited (D-010)."""

    __tablename__ = "sales_deliveries"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("sales_orders", "sales_order_id"),
        # PERFORMANCE §1: the delivery list filters on (tenant, status) and an order's deliveries.
        sa.Index("ix_sales_deliveries_tenant_id_status", "tenant_id", "status"),
        sa.Index(
            "ix_sales_deliveries_tenant_id_sales_order_id",
            "tenant_id",
            "sales_order_id",
        ),
    )

    delivery_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=DeliveryStatus.DRAFT.value,
        server_default="DRAFT",
    )
    sales_order_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Customer snapshot from the order at create (reporting reads it without re-resolving the
    # order).
    customer_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Opaque inventory warehouse id (D-029) the shipment's stock issues FROM; each line's bin is in
    # it.
    warehouse_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    delivery_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    shipping_address: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class DeliveryLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One shipped item on a delivery (PLAN 7.3). ``sales_order_line_id`` is a composite tenant FK
    to sales_order_lines (the line being delivered against). ``item_id`` is an OPAQUE inventory item
    id snapshot from the order line; ``bin_id`` is an OPAQUE inventory bin id (where the stock is
    issued FROM — D-029, validated via inventory/queries). ``quantity`` is the shipped quantity on
    this line (≤ the order line's open-to-deliver). ``lot_code`` / ``serial_code`` (nullable) are
    passed to the stock move for lot/serial-tracked items. UNIQUE(tenant_id, delivery_id,
    line_number). NOT AuditMixin (header-line exclusion). No stock_move_id column — the
    delivery↔move link is docflow (D-041)."""

    __tablename__ = "sales_delivery_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "delivery_id", "line_number", name="uq_sales_delivery_lines_delivery_line"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("sales_deliveries", "delivery_id"),
        tenant_fk("sales_order_lines", "sales_order_line_id"),
    )

    delivery_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    sales_order_line_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    bin_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    quantity: Mapped[object] = mapped_column(QuantityType(), nullable=False)
    lot_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    serial_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)

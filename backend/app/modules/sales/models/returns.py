"""Sales returns / RMA documents (PLAN 7.4, D-046): ``SalesReturn`` + ``SalesReturnLine`` — the
reverse-O2C document (the inbound twin of a delivery, mirrored: a return is a delivery run
backwards).

A return records goods coming BACK from the customer against an order that was delivered AND
invoiced.
The header mixes in ``DocumentMixin`` and carries a gapless ``return_number`` (RMA-) claimed at
creation (D-040). It is built DRAFT (a returns clerk picks order lines + the receiving bin +
returned
quantities ≤ invoiced-not-yet-returned) and then POSTED: at POST it publishes TWO events — one the
inventory handler turns into a stock RECEIPT move (goods back into the bin, Dr Inventory / Cr COGS
via
the COGS-offset OVERRIDE — REVERSING the delivery's issue), one the finance handler turns into an AR
credit note (Dr revenue / Cr AR + reverse output tax — reversing the billing) — the order lines'
returned_quantity rises, all one transaction.

**The return cap (decided here, D-046):** a line's returned quantity is capped at the
INVOICED-not-yet-returned quantity (returned ≤ invoiced), NOT delivered. A return issues a credit
note, and a credit note must reduce a REAL receivable, so a customer cannot be credited for more
than
was invoiced. ``returned_quantity`` (raised by the post) tracks the cap on the order line.

``sales_order_id`` is a composite tenant FK to sales_orders (order-based, not billing-based — the
order line is the single anchor for delivered/invoiced/returned quantities). ``customer_id`` is a
SNAPSHOT of the order's customer; ``warehouse_id`` is an OPAQUE inventory warehouse id (where the
returned goods land); each line's ``bin_id`` is an opaque inventory bin id (where the stock is
received INTO). Per D-046 the return↔move + return↔credit-note linkages are DOCFLOW, never
cross-module FK columns. Money/quantity use ``MoneyType`` / ``QuantityType`` (D-015).
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
from app.modules.sales.constants import ReturnStatus


class SalesReturn(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A sales-return (RMA) header (PLAN 7.4). ``return_number`` (RMA-) is claimed at creation
    (D-040). ``sales_order_id`` is a composite tenant FK to sales_orders; ``customer_id`` is a
    snapshot of the order's customer; ``warehouse_id`` is an OPAQUE inventory warehouse id the
    returned goods land in (validated via inventory/queries — D-029). ``status`` runs the
    ReturnStatus
    lifecycle (DRAFT → POSTED; DRAFT → CANCELLED). ``reason`` (nullable) is a free-text RMA reason;
    ``total_amount`` is the maintained credit Σ; ``posted_at`` records when the return committed.
    Audited (D-010): a document that reverses stock + revenue + AR downstream."""

    __tablename__ = "sales_returns"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("sales_orders", "sales_order_id"),
        # PERFORMANCE §1: the return list filters on (tenant, status) and an order's returns.
        sa.Index("ix_sales_returns_tenant_id_status", "tenant_id", "status"),
        sa.Index(
            "ix_sales_returns_tenant_id_sales_order_id",
            "tenant_id",
            "sales_order_id",
        ),
    )

    return_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=ReturnStatus.DRAFT.value,
        server_default="DRAFT",
    )
    sales_order_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Opaque inventory warehouse id (D-029) the returned goods land in; each line's bin is in it.
    warehouse_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    return_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    total_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class SalesReturnLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One returned line on a return (PLAN 7.4). ``sales_order_line_id`` is a composite tenant FK to
    sales_order_lines (the line being returned against). ``item_id`` is an OPAQUE inventory item
    snapshot from the order line; ``bin_id`` is an OPAQUE inventory bin id (where the stock is
    received
    INTO — D-029, validated via inventory/queries). ``quantity`` is the returned qty (≤ the order
    line's invoiced-not-yet-returned). ``unit_price`` is snapshot from the order line (the credit
    price); ``line_amount`` = qty × unit_price; ``tax_code_id`` (nullable) drives the credit note's
    reversing output tax. ``lot_code`` / ``serial_code`` (nullable) tag the returned stock for
    tracked
    items. UNIQUE(tenant_id, return_id, line_number). NOT AuditMixin (header-line exclusion). No
    stock_move_id / credit_note_id column — those links are docflow (D-046)."""

    __tablename__ = "sales_return_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "return_id", "line_number", name="uq_sales_return_lines_return_line"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("sales_returns", "return_id"),
        tenant_fk("sales_order_lines", "sales_order_line_id"),
    )

    return_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    sales_order_line_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    bin_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    quantity: Mapped[object] = mapped_column(QuantityType(), nullable=False)
    unit_price: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    line_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    tax_code_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    lot_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    serial_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)

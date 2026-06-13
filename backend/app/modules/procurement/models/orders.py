"""Purchase orders (PLAN 6.2): the ``PurchaseOrder`` header + ``PurchaseOrderLine``.

A PO is the committing P2P document — the vendor commitment. The header mixes in ``DocumentMixin``
and carries a gapless ``po_number`` claimed at creation (D-040). It may be raised FROM an approved
requisition AND/OR a quoted RFQ (``source_requisition_id`` / ``source_rfq_id`` — nullable composite
tenant FKs + docflow edges). ``payment_terms_days`` is SNAPSHOT from the vendor at creation (so a
later vendor edit cannot rewrite an open PO's terms — the AP bill in 6.4 reads the snapshot).
``total_amount`` is the maintained sum of line nets. ``approved_by`` / ``approved_at`` record who
cleared the approval gate.

Each line carries an OPAQUE inventory ``item_id`` / ``uom_id`` (D-029), the negotiated
``unit_cost``,
the derived ``line_amount`` (qty × unit_cost), ``received_quantity`` (default 0 — updated by 6.3
goods receipts; the column lands now so the open-quantity query + 6.3 GR need no migration), and an
opaque finance ``tax_code_id`` (nullable — the bill in 6.4 uses it). Money/quantity use
``MoneyType`` / ``QuantityType`` (D-015). PERFORMANCE §1 indexes: (tenant, status) and
(tenant, vendor_id, status).
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
from app.modules.procurement.constants import PurchaseOrderStatus


class PurchaseOrder(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A purchase order header (PLAN 6.2). ``po_number`` is claimed at creation (D-040).
    ``vendor_id`` is a composite tenant FK to proc_vendors (validated ACTIVE at create). ``status``
    runs the PurchaseOrderStatus lifecycle; the SEND step evaluates the PURCHASE_ORDER approval
    threshold on ``total_amount`` (≥ threshold ⇒ PENDING_APPROVAL, below ⇒ auto APPROVED).
    ``payment_terms_days`` is snapshot from the vendor at create. ``source_requisition_id`` /
    ``source_rfq_id`` are nullable composite tenant FKs to the documents this PO was converted from.
    Audited (D-010)."""

    __tablename__ = "proc_purchase_orders"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("proc_vendors", "vendor_id"),
        tenant_fk("proc_requisitions", "source_requisition_id"),
        tenant_fk("proc_rfqs", "source_rfq_id"),
        # PERFORMANCE §1: the PO list filters on (tenant, status) and a vendor's POs by status.
        sa.Index("ix_proc_purchase_orders_tenant_id_status", "tenant_id", "status"),
        sa.Index(
            "ix_proc_purchase_orders_tenant_id_vendor_id_status",
            "tenant_id",
            "vendor_id",
            "status",
        ),
    )

    po_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=PurchaseOrderStatus.DRAFT.value,
        server_default="DRAFT",
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    order_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    expected_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    # Net-days terms snapshot from the vendor at create (the AP bill in 6.4 reads this snapshot so a
    # later vendor edit cannot rewrite an open PO's due-date math).
    payment_terms_days: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    total_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    # Approval audit: who cleared the gate and when (NULL until approved).
    approved_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    source_requisition_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    source_rfq_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


class PurchaseOrderLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One ordered item on a PO (PLAN 6.2). ``item_id`` / ``uom_id`` are OPAQUE inventory ids
    (D-029); ``tax_code_id`` is an opaque finance tax code (nullable — the bill in 6.4 uses it).
    ``unit_cost`` is the negotiated price; ``line_amount`` = quantity × unit_cost (maintained by the
    service). ``received_quantity`` (default 0) is raised by 6.3 goods receipts; the open quantity
    is ordered − received. UNIQUE(tenant_id, po_id, line_number). NOT AuditMixin (header-line
    exclusion)."""

    __tablename__ = "proc_purchase_order_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "po_id", "line_number", name="uq_proc_purchase_order_lines_po_line"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("proc_purchase_orders", "po_id"),
    )

    po_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    quantity: Mapped[object] = mapped_column(QuantityType(), nullable=False)
    uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    unit_cost: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    line_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    # Raised by 6.3 goods receipts; ordered − received is the still-open quantity (the 6.3/6.4 GR +
    # match read it). Default 0 so a fresh PO line is fully open.
    received_quantity: Mapped[object] = mapped_column(
        QuantityType(), nullable=False, default=0, server_default="0"
    )
    # Raised by 6.4 invoice matches (D-042); received − billed is the open-to-bill quantity. A match
    # line cannot exceed received − billed (the 3-way over-billing constraint: no billing beyond
    # goods receipt). Default 0 so a fresh / just-received line is fully open to bill.
    billed_quantity: Mapped[object] = mapped_column(
        QuantityType(), nullable=False, default=0, server_default="0"
    )
    tax_code_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)

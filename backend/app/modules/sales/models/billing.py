"""Sales billing documents (PLAN 7.4, D-046): ``SalesBilling`` + ``SalesBillingLine`` — the O2C
invoicing document, the inbound twin of the procurement invoice match (mirrored, sign-flipped to
AR).

A billing records the decision to invoice DELIVERED goods. The header mixes in ``DocumentMixin`` and
carries a gapless ``billing_number`` (BIL-) claimed at creation (D-040). It is built DRAFT (a
billing
clerk picks order lines + billed quantities ≤ delivered-not-invoiced) and then POSTED: at POST the
sales-billing event is published so FINANCE creates + posts the AR customer invoice (Dr AR control /
Cr sales-revenue per line + Cr output tax, D-046), the order lines' invoiced_quantity rises, and the
order advances INVOICED / CLOSED — all one transaction.

``sales_order_id`` is a composite tenant FK to sales_orders (a billing is always against an order in
v1). ``customer_id`` is a SNAPSHOT of the order's customer (the delivery customer-snapshot
precedent).
``payment_terms_days`` is a SNAPSHOT from the customer/order at create (so the AR invoice's due date
= billing_date + this many days cannot be rewritten by a later customer edit — the PO precedent).

Per D-046 the billing↔customer-invoice linkage is recorded via DOCFLOW (billing document →
'invoiced_by_invoice' → the finance customer-invoice document), NOT a cross-module FK column —
finance
owns the AR invoice, so a billing carries no ``customer_invoice_id``. Money/quantity use
``MoneyType`` / ``QuantityType`` (D-015, exact on both engines).
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
from app.modules.sales.constants import BillingStatus


class SalesBilling(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A sales-billing header (PLAN 7.4). ``billing_number`` (BIL-) is claimed at creation (D-040).
    ``sales_order_id`` is a composite tenant FK to sales_orders; ``customer_id`` snapshots the
    order's customer; ``payment_terms_days`` is a snapshot driving the AR invoice's due date.
    ``status`` runs DRAFT → POSTED / DRAFT → CANCELLED. ``total_amount`` is the maintained Σ
    line_amount. ``posted_at`` records when the billing committed. Audited (D-010): a document that
    recognizes revenue + AR downstream."""

    __tablename__ = "sales_billings"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("sales_orders", "sales_order_id"),
        # PERFORMANCE §1: the billing list filters on (tenant, status) and an order's billings.
        sa.Index("ix_sales_billings_tenant_id_status", "tenant_id", "status"),
        sa.Index(
            "ix_sales_billings_tenant_id_sales_order_id",
            "tenant_id",
            "sales_order_id",
        ),
    )

    billing_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=BillingStatus.DRAFT.value,
        server_default="DRAFT",
    )
    sales_order_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Customer snapshot from the order at create (the AR invoice's opaque partner_id = this id,
    # D-029).
    customer_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    billing_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    # Net-days terms snapshot (the AR invoice due date = billing_date + this many days).
    payment_terms_days: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    total_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class SalesBillingLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One billed line on a billing (PLAN 7.4). ``sales_order_line_id`` is a composite tenant FK to
    sales_order_lines (the line being billed). ``delivery_line_id`` (nullable composite tenant FK)
    names which shipment this bills (the source delivery line for the docflow chain; nullable so a
    future bill-without-a-named-line still works). ``item_id`` (OPAQUE), ``unit_price`` and the
    optional discount fields are SNAPSHOT from the order line; ``line_amount`` = qty × unit_price −
    discount. ``tax_code_id`` (nullable, opaque) drives the output tax. ``quantity`` is the billed
    qty (≤ delivered-not-invoiced). UNIQUE(tenant_id, billing_id, line_number). NOT AuditMixin."""

    __tablename__ = "sales_billing_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "billing_id", "line_number", name="uq_sales_billing_lines_billing_line"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("sales_billings", "billing_id"),
        tenant_fk("sales_order_lines", "sales_order_line_id"),
        tenant_fk("sales_delivery_lines", "delivery_line_id"),
    )

    billing_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    sales_order_line_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    delivery_line_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    quantity: Mapped[object] = mapped_column(QuantityType(), nullable=False)
    unit_price: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    discount_type: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    discount_value: Mapped[object | None] = mapped_column(MoneyType(), nullable=True)
    line_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    tax_code_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)

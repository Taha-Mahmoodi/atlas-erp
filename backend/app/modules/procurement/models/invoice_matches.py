"""Invoice matches (PLAN 6.4, D-042): the ``InvoiceMatch`` header + ``InvoiceMatchLine`` + the
per-tenant ``MatchTolerance`` config — the procure-to-pay closing step.

A 3-way match compares a vendor's invoice against the PO (price) and the goods receipt (quantity).
On POST it triggers the AP vendor bill (Dr GR/IR + PPV / Cr AP) that CLEARS the GR/IR account the
goods receipt credited at receipt — closing the procure-to-pay loop. The header mixes in
``DocumentMixin`` and carries a gapless ``match_number`` claimed at creation (D-040). The bill is
created in FINANCE via the event bus (procurement never imports finance/service); the match→bill
link lives in docflow only, so the match carries NO ``vendor_bill_id`` FK into finance's table.

``purchase_order_id`` is a composite tenant FK to proc_purchase_orders (a match is always against a
PO in v1). ``vendor_id`` is a SNAPSHOT of the PO's vendor (= the opaque finance ``partner_id``,
D-029). ``vendor_invoice_ref`` is the vendor's OWN invoice number (free text — the match document
number is Atlas-owned). ``total_amount`` is the vendor-invoiced total being matched. The GR/IR
account is snapshot for traceability of which clearing account the match's bill will debit.

Each line snapshots the PO line's ``po_unit_cost`` and computes the ``price_variance`` /
``quantity_variance`` against the vendor's invoiced ``unit_price`` / ``matched_quantity``;
``within_tolerance`` records whether the line passed the tolerance band. ``goods_receipt_line_id``
(nullable) records which receipt line this match line draws from, when supplied.
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
from app.modules.procurement.constants import MatchStatus


class MatchTolerance(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """The per-tenant 3-way-match tolerance config (PLAN 6.4, D-042). ``price_tolerance_percent`` is
    the band a line's invoiced unit price may deviate from the PO price before the line becomes an
    EXCEPTION; ``quantity_tolerance_percent`` is the band on the matched quantity. SINGLE active row
    per tenant in v1 (UNIQUE(tenant_id) — the ApprovalRule single-per-tenant precedent; per-vendor
    tolerance groups are the documented later). When a tenant has no row, the constants DEFAULTS
    apply (strict 0% — a price change must be deliberate). NOT DocumentMixin: config, not a posted
    document. Audited (D-010): tolerances are a financial control."""

    __tablename__ = "proc_match_tolerances"
    __table_args__ = (
        # The single-active-row-per-tenant guarantee. Named explicitly (not via the convention,
        # which keys on column_0 = tenant_id and would collide with tenant_unique()'s name).
        sa.UniqueConstraint("tenant_id", name="uq_proc_match_tolerances_tenant"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # Bare tokens: the D-022 ck convention wraps each as ck_<table>_<name>.
        sa.CheckConstraint("price_tolerance_percent >= 0", name="price_tolerance_non_negative"),
        sa.CheckConstraint(
            "quantity_tolerance_percent >= 0", name="quantity_tolerance_non_negative"
        ),
    )

    price_tolerance_percent: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    quantity_tolerance_percent: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )


class InvoiceMatch(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A 3-way invoice match header (PLAN 6.4, D-042). ``match_number`` is claimed at creation
    (D-040). ``purchase_order_id`` is a composite tenant FK to proc_purchase_orders; ``vendor_id``
    is a snapshot of the PO's vendor (the opaque finance partner_id, D-029). ``status`` runs the
    MatchStatus lifecycle (DRAFT → MATCHED/EXCEPTION → POSTED; DRAFT/EXCEPTION → CANCELLED).
    ``vendor_invoice_ref`` is the vendor's own invoice number; ``total_amount`` is the
    vendor-invoiced total. ``tax_code_id`` (nullable, opaque) drives the bill's input tax.
    ``gr_ir_account_id`` is the GR/IR clearing account snapshot (the bill debits it). ``posted_at``
    records
    when the match committed. NO vendor_bill_id FK — the match→bill link is docflow (D-042).
    Audited (D-010)."""

    __tablename__ = "proc_invoice_matches"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("proc_purchase_orders", "purchase_order_id"),
        # PERFORMANCE §1: the match list filters on (tenant, status) and a PO's matches.
        sa.Index("ix_proc_invoice_matches_tenant_id_status", "tenant_id", "status"),
        sa.Index(
            "ix_proc_invoice_matches_tenant_id_purchase_order_id",
            "tenant_id",
            "purchase_order_id",
        ),
    )

    match_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=MatchStatus.DRAFT.value,
        server_default="DRAFT",
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Vendor snapshot from the PO (= the opaque finance partner_id, D-029).
    vendor_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    vendor_invoice_ref: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    invoice_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    total_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    # Opaque finance tax code (D-029) driving the bill's input tax; nullable (a tax-free match).
    tax_code_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # GR/IR clearing account snapshot (the account the triggered bill debits to clear receipt).
    gr_ir_account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class InvoiceMatchLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One matched line on an invoice match (PLAN 6.4, D-042). ``purchase_order_line_id`` is a
    composite tenant FK to proc_purchase_order_lines (the line being billed against);
    ``goods_receipt_line_id`` (nullable composite tenant FK) records which receipt line it draws
    from. ``item_id`` is an OPAQUE inventory item id snapshot from the PO line. ``matched_quantity``
    is the quantity being invoiced (≤ received − already-billed, enforced by the service);
    ``unit_price`` is the vendor's invoiced unit price; ``po_unit_cost`` is the PO price snapshot.
    ``price_variance`` = (unit_price − po_unit_cost) × matched_quantity; ``quantity_variance`` is
    the matched-qty deviation; ``line_amount`` = matched_quantity × unit_price; ``within_tolerance``
    flags whether the line passed the tolerance band. UNIQUE(tenant_id, match_id, line_number). NOT
    AuditMixin (header-line exclusion)."""

    __tablename__ = "proc_invoice_match_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "match_id", "line_number", name="uq_proc_invoice_match_lines_match_line"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("proc_invoice_matches", "match_id"),
        tenant_fk("proc_purchase_order_lines", "purchase_order_line_id"),
        tenant_fk("proc_goods_receipt_lines", "goods_receipt_line_id"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    purchase_order_line_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    goods_receipt_line_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    matched_quantity: Mapped[object] = mapped_column(QuantityType(), nullable=False)
    unit_price: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    po_unit_cost: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    price_variance: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    quantity_variance: Mapped[object] = mapped_column(
        QuantityType(), nullable=False, default=0, server_default="0"
    )
    line_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    within_tolerance: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )

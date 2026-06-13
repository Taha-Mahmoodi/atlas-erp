"""Accounts Payable: vendor bills, payments and payment allocations (PLAN 4.5, D-029).

The AP sub-ledger is keyed by an OPAQUE ``partner_id`` (D-029): finance is the bottom of the
dependency order, so it never FK-references a vendor master (that lives in procurement, above
finance). Each AP document carries the opaque ``partner_id`` plus a denormalized ``partner_name``
for display; the owning module guarantees the id. Open items (the amount still owed on a bill)
live in ``open_amount`` on the bill, reduced as payments allocate against it.

Every AP document posts through the universal journal (D-017): a ``VendorBill`` registers in
core_documents at creation (DocumentMixin) and gets a ``journal_entry_id`` + system number at
posting; a ``VendorPayment`` is created and posted in one step, clearing the open items its
allocations name. Realized FX at clearing (D-019) is computed in the SERVICE, posted inside the
payment journal entry — no extra columns here.

Fifth file in the finance ``models/`` package (STRUCTURE §3); re-exported from ``models/__init__``.
Money columns use ``MoneyType`` (D-015, exact on both engines). All cross-row links are composite
tenant FKs (D-007 backstop) EXCEPT ``partner_id`` (opaque, no FK — D-029) and the dimension ids.
Enum-valued columns are plain ``sa.String`` storing the StrEnum value, as elsewhere in finance.
"""

import uuid
from datetime import date

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
from app.core.money import MoneyType
from app.modules.finance.constants import BillStatus, PaymentStatus


class VendorBill(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A vendor bill / supplier invoice (PLAN 4.5). Registered in core_documents at creation
    (DocumentMixin, doc_number NULL); the gapless system ``bill_number`` is claimed at POSTING
    (D-012). ``partner_id`` is the OPAQUE vendor id (D-029 — no FK); ``partner_name`` is the
    denormalized display name. ``bill_external_ref`` is the vendor's own document number (free
    text, not unique). At posting the service builds the AP journal entry (Dr expense/asset lines +
    Dr input tax, Cr AP control gross), sets ``journal_entry_id`` + ``open_amount`` = gross, and
    flips ``status`` to POSTED. ``open_amount`` (transaction currency) is the still-owed balance,
    reduced by payment allocations until PAID. Audited (D-010): a financial document."""

    __tablename__ = "fin_vendor_bills"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        # The AP control account this bill credits (composite tenant FK). Bills carry their own
        # AP control account so the sub-ledger needs no fixed default (D-029).
        tenant_fk("fin_accounts", "ap_account_id"),
        # The journal entry created at posting (composite tenant FK; NULL until posted).
        tenant_fk("fin_journal_entries", "journal_entry_id"),
        # Hot-list filter combination for GET /vendor-bills, aging, and payment runs
        # (PERFORMANCE §1, #25): tenant leads, then the dominant filters, then the sort key.
        sa.Index(
            "ix_fin_vendor_bills_list_filters",
            "tenant_id",
            "partner_id",
            "status",
            "bill_date",
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    partner_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # The vendor's own reference on the bill (free text, not the system number); nullable.
    bill_external_ref: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    # The gapless system number, claimed at posting (NULL until then; D-012).
    bill_number: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    bill_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    due_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=BillStatus.DRAFT.value, server_default="DRAFT"
    )
    ap_account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    gross_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    tax_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    net_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    # Still-owed balance in the bill's transaction currency. Equals gross at posting; reduced by
    # payment allocations until 0 (PAID). No stored total elsewhere — aging projects over this.
    open_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)


class VendorBillLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One expense/asset line on a vendor bill (PLAN 4.5). ``account_id`` is the GL account the net
    debits at posting; ``tax_code_id`` (nullable) drives the input-tax calculation, with the
    resulting ``tax_amount`` posted to the tax code's receivable account. ``cost_center_id`` and
    ``project_id`` are opaque CO/project dimensions (no FK — masters land in later phases, mirroring
    the journal line). NOT AuditMixin: lines are written once with their bill and the bill's audit
    row records the document-level change (same exclusion as journal lines)."""

    __tablename__ = "fin_vendor_bill_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "bill_id",
            "line_number",
            name="uq_fin_vendor_bill_lines_tenant_id_bill_id_line_number",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_vendor_bills", "bill_id"),
        tenant_fk("fin_accounts", "account_id"),
        tenant_fk("fin_tax_codes", "tax_code_id"),
    )

    bill_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    net_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    tax_code_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    tax_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


class VendorPayment(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A vendor payment (PLAN 4.5). Created and posted in one step: the service builds the payment
    journal entry (Dr AP control for the sum cleared, Cr bank for ``amount``, plus a realized-FX
    gain/loss line when the bill rate differs from the payment rate, D-019), then claims the gapless
    ``payment_number`` (D-012) and links the payment to the bills it clears. ``partner_id`` is the
    OPAQUE vendor id (D-029); ``bank_account_id`` is the bank/cash account credited. Audited
    (D-010). The bills cleared and by how much live in ``VendorPaymentAllocation`` rows."""

    __tablename__ = "fin_vendor_payments"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("fin_accounts", "bank_account_id"),
        tenant_fk("fin_journal_entries", "journal_entry_id"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    partner_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    payment_number: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    payment_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    bank_account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=PaymentStatus.POSTED.value, server_default="POSTED"
    )
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)


class VendorPaymentAllocation(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One (payment -> bill) clearing allocation (PLAN 4.5): how much of a payment cleared a given
    bill, in the transaction currency. UNIQUE(tenant_id, payment_id, vendor_bill_id) so a payment
    clears each bill at most once. NOT AuditMixin: an allocation is written once with its payment
    and the payment's audit row records the document-level change."""

    __tablename__ = "fin_vendor_payment_allocations"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "payment_id",
            "vendor_bill_id",
            # Short explicit name: PG caps identifiers at 63 chars and does NOT truncate explicit
            # names (the D-022 column-0 convention would otherwise collide with tenant_unique()).
            name="uq_fin_vendor_payment_allocations_payment_bill",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_vendor_payments", "payment_id"),
        tenant_fk("fin_vendor_bills", "vendor_bill_id"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    vendor_bill_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    allocated_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)

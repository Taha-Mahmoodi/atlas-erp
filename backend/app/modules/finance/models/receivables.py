"""Accounts Receivable: customer invoices, receipts, allocations and dunning (PLAN 4.6, D-029).

The AR sub-ledger mirrors AP (``payables.py``) with the sign flipped: a posted invoice debits the
AR control for the gross and credits revenue + output tax (vs AP's Dr expense / Cr AP); a receipt
credits AR control and debits the bank (vs AP's Dr AP / Cr bank). Like AP it is keyed by an OPAQUE
``partner_id`` (D-029): finance is the bottom of the dependency order, so it never FK-references a
customer master (that lives in sales, above finance). Each AR document carries the opaque
``partner_id`` plus a denormalized ``partner_name`` for display; the owning module guarantees it.

AR adds DUNNING: each open invoice tracks how many dunning notices have been sent
(``dunning_level``) and when (``last_dunned_date``). The dunning run (service/dunning.py) advances
those as the invoice ages past the day-thresholds; it posts no journal — it only updates state.

Every AR document posts through the universal journal (D-017): a ``CustomerInvoice`` registers in
core_documents at creation (DocumentMixin) and gets a ``journal_entry_id`` + system number at
posting; a ``CustomerReceipt`` is created and posted in one step, clearing the open items its
allocations name. Realized FX at clearing (D-019) is computed in the SERVICE, posted inside the
receipt journal entry — no extra columns here.

Sixth file in the finance ``models/`` package (STRUCTURE §3); re-exported from ``models/__init__``.
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
from app.modules.finance.constants import InvoiceStatus, ReceiptStatus


class CustomerInvoice(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A customer invoice (PLAN 4.6). Registered in core_documents at creation (DocumentMixin,
    doc_number NULL); the gapless system ``invoice_number`` is claimed at POSTING (D-012).
    ``partner_id`` is the OPAQUE customer id (D-029 — no FK); ``partner_name`` is the denormalized
    display name. ``external_ref`` is the tenant's own reference (free text, not unique). At posting
    the service builds the AR journal entry (Dr AR control gross, Cr each revenue line net, Cr
    output tax), sets ``journal_entry_id`` + ``open_amount`` = gross, flips ``status`` to POSTED.
    ``open_amount`` (transaction currency) is the still-owed balance, reduced by receipt allocations
    until PAID. ``dunning_level`` is how many dunning notices have been sent (0 = none); the dunning
    run raises it as the invoice ages and stamps ``last_dunned_date``. Audited (D-010)."""

    __tablename__ = "fin_customer_invoices"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        # The AR control account this invoice debits (composite tenant FK). Invoices carry their own
        # AR control account so the sub-ledger needs no fixed default (D-029).
        tenant_fk("fin_accounts", "ar_account_id"),
        # The journal entry created at posting (composite tenant FK; NULL until posted).
        tenant_fk("fin_journal_entries", "journal_entry_id"),
        # Hot-list filter combination for GET /customer-invoices, aging, and dunning
        # (PERFORMANCE §1, #25): tenant leads, then the dominant filters, then the sort key.
        sa.Index(
            "ix_fin_customer_invoices_list_filters",
            "tenant_id",
            "partner_id",
            "status",
            "invoice_date",
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    partner_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # The tenant's own reference on the invoice (free text, not the system number); nullable.
    external_ref: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    # The gapless system number, claimed at posting (NULL until then; D-012).
    invoice_number: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    invoice_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    due_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=InvoiceStatus.DRAFT.value, server_default="DRAFT"
    )
    ar_account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
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
    # Still-owed balance in the invoice's transaction currency. Equals gross at posting; reduced by
    # receipt allocations until 0 (PAID). No stored total elsewhere — aging projects over this.
    open_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    # How many dunning notices have been sent (0 = none); raised by the dunning run as the invoice
    # ages past the day-thresholds. ``last_dunned_date`` records the most recent advancing run.
    dunning_level: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    last_dunned_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)


class CustomerInvoiceLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One revenue line on a customer invoice (PLAN 4.6). ``account_id`` is the REVENUE account the
    net credits at posting; ``tax_code_id`` (nullable) drives the output-tax calculation, with the
    resulting ``tax_amount`` posted to the tax code's payable account. ``cost_center_id`` /
    ``profit_center_id`` / ``project_id`` are opaque CO/project dimensions (no FK — masters land in
    later phases, mirroring the journal line). NOT AuditMixin: lines are written once with their
    invoice and the invoice's audit row records the document-level change (same exclusion as
    journal lines)."""

    __tablename__ = "fin_customer_invoice_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "invoice_id",
            "line_number",
            name="uq_fin_customer_invoice_lines_invoice_line",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_customer_invoices", "invoice_id"),
        tenant_fk("fin_accounts", "account_id"),
        tenant_fk("fin_tax_codes", "tax_code_id"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    net_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    tax_code_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    tax_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    profit_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


class CustomerReceipt(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A customer receipt (PLAN 4.6). Created and posted in one step: the service builds the receipt
    journal entry (Cr AR control for the sum cleared, Dr bank for ``amount``, plus a realized-FX
    gain/loss line when the invoice rate differs from the receipt rate, D-019), then claims the
    gapless ``receipt_number`` (D-012) and links the receipt to the invoices it clears.
    ``partner_id`` is the OPAQUE customer id (D-029); ``bank_account_id`` is the bank/cash account
    debited. Audited (D-010). The invoices cleared and by how much live in
    ``CustomerReceiptAllocation`` rows."""

    __tablename__ = "fin_customer_receipts"
    __table_args__ = (
        # The floor under the ``unapplied_amount`` draw-down (D-084): a customer can never be owed
        # a negative deposit, whichever writer got there. Serializing two concurrent applications
        # is the with_for_update lock's job, not this one's — they are complementary, not
        # substitutes. A single-column comparison, exact on PG NUMERIC and SQLite micro-unit
        # INTEGER alike (D-003/D-015), the inv_stock_quants on-hand precedent (D-020/D-036).
        # The bare name, NOT a pre-prefixed one: NAMING_CONVENTION's "ck" template is
        # ck_%(table_name)s_%(constraint_name)s (core/models.py), so passing the full
        # ck_fin_customer_receipts_... here double-prefixes it to 72 chars — over PG's 63-char cap,
        # where it silently comes back machine-truncated with a hash suffix and no longer matches
        # the name the migration creates.
        sa.CheckConstraint("unapplied_amount >= 0", name="unapplied_non_negative"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("fin_accounts", "bank_account_id"),
        tenant_fk("fin_journal_entries", "journal_entry_id"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    partner_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    receipt_number: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    receipt_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    bank_account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    # The part of ``amount`` that cleared no invoice — an advance deposit, or the excess of an
    # over-payment (PLAN 20.4, D-084). Credited to the ``customer_advances`` control at posting and
    # reduced by ``apply_receipt`` as it is spent on invoices; 0 on a fully allocated receipt.
    # It is a BALANCE, not a total: allocations only ever subtract from it, never re-derive it.
    unapplied_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=ReceiptStatus.POSTED.value, server_default="POSTED"
    )
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)


class CustomerReceiptAllocation(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One (receipt -> invoice) clearing allocation (PLAN 4.6): how much of a receipt cleared a
    given invoice, in the transaction currency. UNIQUE(tenant_id, receipt_id, customer_invoice_id)
    so a receipt clears each invoice at most once (name abbreviated for Postgres' 63-char limit).
    NOT AuditMixin: an allocation is written once with its receipt and the receipt's audit row holds
    the document-level change."""

    __tablename__ = "fin_customer_receipt_allocations"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "receipt_id",
            "customer_invoice_id",
            # Short explicit name: PG caps identifiers at 63 chars and does NOT truncate explicit
            # names (the D-022 column-0 convention would otherwise collide with tenant_unique()).
            name="uq_fin_customer_receipt_allocations_receipt_invoice",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # Explicit short names: the D-022 convention's auto name for these two composite FKs
        # (fk_<table>_tenant_id_<target>) is 67 chars — over PG's 63-char identifier cap — so name
        # them explicitly (abbreviated) here, and the migration uses the SAME names.
        sa.ForeignKeyConstraint(
            ["tenant_id", "receipt_id"],
            ["fin_customer_receipts.tenant_id", "fin_customer_receipts.id"],
            name="fk_fin_cust_receipt_allocs_tenant_id_receipts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_invoice_id"],
            ["fin_customer_invoices.tenant_id", "fin_customer_invoices.id"],
            name="fk_fin_cust_receipt_allocs_tenant_id_invoices",
        ),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    customer_invoice_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    allocated_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)

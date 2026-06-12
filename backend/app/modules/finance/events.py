"""Domain events finance PUBLISHES (D-011). Declarative data only — no logic, no models — so
another module's ``handlers.py`` may import these typed classes (the STRUCTURE §5 events.py
allowance). Inventory and other modules subscribe in a later phase; the payload carries the
entry id plus amount/account summaries so a subscriber needs no finance read to react.

For v1 functional amounts equal transaction amounts (single functional currency); the event
carries the functional total since that is what downstream ledger consumers reconcile against.
"""

import uuid
from decimal import Decimal
from typing import ClassVar

from app.core.events import DomainEvent


class JournalEntryPosted(DomainEvent):
    """A draft journal entry was posted (D-017). Fired inside the posting transaction after the
    DRAFT->POSTED flush; a handler runs in the SAME transaction (D-011), so any cross-module
    effect it triggers commits or rolls back with the posting."""

    key: ClassVar[str] = "finance.journal.posted"

    entry_id: uuid.UUID
    entry_number: str
    document_type: str
    posting_date: str
    currency_code: str
    total_functional_amount: Decimal
    account_ids: tuple[uuid.UUID, ...]


class JournalEntryReversed(DomainEvent):
    """A posted entry was reversed by a new reversing entry (D-017). Carries both ids so a
    subscriber can mirror the correction (e.g. reverse a derived posting)."""

    key: ClassVar[str] = "finance.journal.reversed"

    entry_id: uuid.UUID
    reversal_entry_id: uuid.UUID
    reversal_entry_number: str
    document_type: str
    reversal_date: str


class VendorBillPosted(DomainEvent):
    """A vendor bill was posted to the journal (PLAN 4.5, AP). Fired inside the posting
    transaction; the payload carries the opaque ``partner_id`` (D-029) + amounts so procurement
    (later) can react without a finance read. ``open_amount`` equals ``gross_amount`` at posting."""

    key: ClassVar[str] = "finance.vendor_bill.posted"

    bill_id: uuid.UUID
    bill_number: str
    journal_entry_id: uuid.UUID
    partner_id: uuid.UUID
    currency_code: str
    gross_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal


class VendorPaymentPosted(DomainEvent):
    """A vendor payment was posted, clearing one or more open bills (PLAN 4.5, AP). Carries the
    opaque ``partner_id`` (D-029), the bank amount, and the ids of the bills it cleared so a
    subscriber can mirror the clearing. Realized FX (D-019) is already inside the payment entry."""

    key: ClassVar[str] = "finance.vendor_payment.posted"

    payment_id: uuid.UUID
    payment_number: str
    journal_entry_id: uuid.UUID
    partner_id: uuid.UUID
    currency_code: str
    amount: Decimal
    cleared_bill_ids: tuple[uuid.UUID, ...]


class CustomerInvoicePosted(DomainEvent):
    """A customer invoice was posted to the journal (PLAN 4.6, AR). Fired inside the posting
    transaction; the payload carries the opaque ``partner_id`` (D-029) + amounts so sales (later)
    can react without a finance read. ``open_amount`` equals ``gross_amount`` at posting."""

    key: ClassVar[str] = "finance.customer_invoice.posted"

    invoice_id: uuid.UUID
    invoice_number: str
    journal_entry_id: uuid.UUID
    partner_id: uuid.UUID
    currency_code: str
    gross_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal


class CustomerReceiptPosted(DomainEvent):
    """A customer receipt was posted, clearing one or more open invoices (PLAN 4.6, AR). Carries the
    opaque ``partner_id`` (D-029), the bank amount, and the ids of the invoices it cleared so a
    subscriber can mirror the clearing. Realized FX (D-019) is already inside the receipt entry."""

    key: ClassVar[str] = "finance.customer_receipt.posted"

    receipt_id: uuid.UUID
    receipt_number: str
    journal_entry_id: uuid.UUID
    partner_id: uuid.UUID
    currency_code: str
    amount: Decimal
    cleared_invoice_ids: tuple[uuid.UUID, ...]

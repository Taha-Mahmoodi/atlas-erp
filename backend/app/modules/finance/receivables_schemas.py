"""Accounts Receivable request/response schemas (PLAN 4.6, Pydantic v2, ApiModel base).

Split into a sibling file (not appended to ``schemas.py``) exactly as ``payables_schemas.py`` is:
``schemas.py`` is near the STRUCTURE §3 400-line cap and the AR shapes are a self-contained surface,
so co-locating them here keeps both files under the cap and reads cleanly (STRUCTURE §8.5). Money
fields are ``Decimal`` serialized as strings (D-015). ``partner_id`` is the OPAQUE customer id
(D-029) — accepted from the caller, never FK'd. Server-owned fields (ids, numbers, journal links,
status, dunning state, timestamps) are never accepted on Create.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.finance.constants import InvoiceStatus, ReceiptStatus

# --- Customer invoices --------------------------------------------------------


class CustomerInvoiceLineCreate(ApiModel):
    """One line on a draft customer invoice. ``net_amount`` is the pre-tax amount on ``account_id``
    (a REVENUE account); ``tax_code_id`` (optional) drives the output-tax calculation. Dimensions
    are opaque ids."""

    account_id: uuid.UUID
    description: str | None = None
    net_amount: Decimal
    tax_code_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    profit_center_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class CustomerInvoiceCreate(ApiModel):
    """Create a DRAFT customer invoice (PLAN 4.6). ``partner_id`` is the opaque customer id (D-029)
    and ``partner_name`` the denormalized display name. ``ar_account_id`` is the AR control account
    the invoice will debit at posting. ``external_ref`` is the tenant's own reference (free text).
    At least one line is required; the service computes tax + totals."""

    partner_id: uuid.UUID
    partner_name: str
    invoice_date: date
    due_date: date
    currency_code: str
    ar_account_id: uuid.UUID
    external_ref: str | None = None
    description: str | None = None
    lines: list[CustomerInvoiceLineCreate]


class CustomerInvoiceLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    account_id: uuid.UUID
    description: str | None
    net_amount: Decimal
    tax_code_id: uuid.UUID | None
    tax_amount: Decimal
    cost_center_id: uuid.UUID | None
    profit_center_id: uuid.UUID | None
    project_id: uuid.UUID | None


class CustomerInvoiceRead(ApiModel):
    """Invoice header without lines — the list-row shape."""

    id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    external_ref: str | None
    invoice_number: str | None
    invoice_date: date
    due_date: date
    currency_code: str
    status: InvoiceStatus
    ar_account_id: uuid.UUID
    journal_entry_id: uuid.UUID | None
    gross_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal
    open_amount: Decimal
    dunning_level: int
    last_dunned_date: date | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class CustomerInvoiceDetail(CustomerInvoiceRead):
    """Invoice header WITH its lines — the GET /{id} shape."""

    lines: list[CustomerInvoiceLineRead]


# --- Customer credit notes (PLAN 7.4, sales RMA returns) ----------------------


class CustomerCreditNoteCreate(ApiModel):
    """Create + post a customer credit note (PLAN 7.4) — the sign-flipped customer invoice. Same
    shape as ``CustomerInvoiceCreate`` (``partner_id`` opaque customer id D-029, an AR control
    account to credit, revenue lines + tax codes), but its posted journal REVERSES the AR invoice's:
    Dr revenue net / Dr output tax / Cr AR control gross — reducing what the customer owes. Built
    and
    posted in one step by the sales-return handler (finance had no credit-note path before 7.4)."""

    partner_id: uuid.UUID
    partner_name: str
    credit_note_date: date
    currency_code: str
    ar_account_id: uuid.UUID
    external_ref: str | None = None
    description: str | None = None
    lines: list[CustomerInvoiceLineCreate]


# --- Customer receipts --------------------------------------------------------


class ReceiptAllocationCreate(ApiModel):
    """One (invoice, amount) the receipt clears. ``amount`` is in the receipt's transaction currency
    and must not exceed the invoice's open amount (the service validates)."""

    invoice_id: uuid.UUID
    amount: Decimal


class CustomerReceiptCreate(ApiModel):
    """Create + post a customer receipt (PLAN 4.6). ``partner_id`` is the opaque customer id
    (D-029); all cleared invoices must be open, same partner, same currency. ``bank_account_id`` is
    the bank/cash account debited; ``amount`` is the cash received. Realized FX (D-019) computed and
    posted inside the receipt entry by the service."""

    partner_id: uuid.UUID
    partner_name: str
    receipt_date: date
    currency_code: str
    bank_account_id: uuid.UUID
    amount: Decimal
    description: str | None = None
    allocations: list[ReceiptAllocationCreate]


class ReceiptAllocationRead(ApiModel):
    id: uuid.UUID
    receipt_id: uuid.UUID
    customer_invoice_id: uuid.UUID
    allocated_amount: Decimal


class CustomerReceiptRead(ApiModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    receipt_number: str | None
    receipt_date: date
    currency_code: str
    bank_account_id: uuid.UUID
    amount: Decimal
    journal_entry_id: uuid.UUID | None
    status: ReceiptStatus
    description: str | None
    created_at: datetime
    updated_at: datetime


class CustomerReceiptDetail(CustomerReceiptRead):
    """Receipt header WITH its allocations — the create/GET response shape."""

    allocations: list[ReceiptAllocationRead]


# --- Dunning ------------------------------------------------------------------


class DunningRunRequest(ApiModel):
    """Run a dunning pass (PLAN 4.6). For each open overdue invoice (optionally narrowed to one
    ``partner_id``) the run computes the dunning level from days-overdue thresholds and, when it
    exceeds the invoice's current level, raises it + stamps ``as_of`` as the last-dunned date. Posts
    no journal — it updates dunning state only. Idempotent per day: a re-run the same day never
    advances a level already at/above its threshold."""

    as_of: date
    partner_id: uuid.UUID | None = None


class DunningNoticeRead(ApiModel):
    """One invoice the dunning run advanced (PLAN 4.6): the partner, the invoice, and the NEW level
    the run raised it to. The list of these is the dunning proposal / notice list a collections
    clerk acts on."""

    partner_id: uuid.UUID
    partner_name: str
    invoice_id: uuid.UUID
    invoice_number: str | None
    currency_code: str
    open_amount: Decimal
    due_date: date
    days_overdue: int
    previous_level: int
    new_level: int


class DunningRunResult(ApiModel):
    """The dunning run's outcome (PLAN 4.6): the invoices it advanced, as of ``as_of``. A wrapper
    (not a bare list) so the idempotency replay body serializes through ``model_dump`` like every
    other captured response (D-013)."""

    as_of: date
    notices: list[DunningNoticeRead]


# --- AR aging -----------------------------------------------------------------


class ArAgingBucketRead(ApiModel):
    """Open AR for one partner bucketed by (as_of - due_date) days (PLAN 4.6). ``current`` is not
    yet due (due on/after as_of); the rest are overdue bands. ``total`` is their sum."""

    partner_id: uuid.UUID
    partner_name: str
    currency_code: str
    current: Decimal
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_over_90: Decimal
    total: Decimal


class ArAgingReportRead(ApiModel):
    """The AR aging report (PLAN 4.6): per-partner buckets plus the rolled-up totals row. A pure
    projection over open invoices — no stored totals (D-021 spirit)."""

    as_of: date
    partners: list[ArAgingBucketRead]
    current: Decimal
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_over_90: Decimal
    total: Decimal

"""Accounts Payable request/response schemas (PLAN 4.5, Pydantic v2, ApiModel base).

Split into a sibling file (not appended to ``schemas.py``) the same way ``ap_router.py`` is a
sibling of ``router.py``: ``schemas.py`` is near the STRUCTURE §3 400-line cap, and the AP shapes
are a self-contained surface, so co-locating them here keeps both files under the cap and reads
cleanly (STRUCTURE §8.5 one-concept-per-file). Money fields are ``Decimal`` serialized as strings
(D-015). ``partner_id`` is the OPAQUE vendor id (D-029) — accepted from the caller, never FK'd.
Server-owned fields (ids, numbers, journal links, status, timestamps) are never accepted on Create.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.finance.constants import BillStatus, PaymentStatus

# --- Vendor bills -------------------------------------------------------------


class VendorBillLineCreate(ApiModel):
    """One line on a draft vendor bill. ``net_amount`` is the pre-tax amount on ``account_id``;
    ``tax_code_id`` (optional) drives the input-tax calculation. Dimensions are opaque ids."""

    account_id: uuid.UUID
    description: str | None = None
    net_amount: Decimal
    tax_code_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class VendorBillCreate(ApiModel):
    """Create a DRAFT vendor bill (PLAN 4.5). ``partner_id`` is the opaque vendor id (D-029) and
    ``partner_name`` the denormalized display name. ``ap_account_id`` is the AP control account the
    bill will credit at posting. ``bill_external_ref`` is the vendor's own document number (free
    text). At least one line is required; the service computes tax + totals."""

    partner_id: uuid.UUID
    partner_name: str
    bill_date: date
    due_date: date
    currency_code: str
    ap_account_id: uuid.UUID
    bill_external_ref: str | None = None
    description: str | None = None
    lines: list[VendorBillLineCreate]


class VendorBillLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    account_id: uuid.UUID
    description: str | None
    net_amount: Decimal
    tax_code_id: uuid.UUID | None
    tax_amount: Decimal
    cost_center_id: uuid.UUID | None
    project_id: uuid.UUID | None


class VendorBillRead(ApiModel):
    """Bill header without lines — the list-row shape."""

    id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    bill_external_ref: str | None
    bill_number: str | None
    bill_date: date
    due_date: date
    currency_code: str
    status: BillStatus
    ap_account_id: uuid.UUID
    journal_entry_id: uuid.UUID | None
    gross_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal
    open_amount: Decimal
    description: str | None
    created_at: datetime
    updated_at: datetime


class VendorBillDetail(VendorBillRead):
    """Bill header WITH its lines — the GET /{id} shape."""

    lines: list[VendorBillLineRead]


# --- Vendor payments ----------------------------------------------------------


class PaymentAllocationCreate(ApiModel):
    """One (bill, amount) the payment clears. ``amount`` is in the payment's transaction currency
    and must not exceed the bill's open amount (the service validates)."""

    bill_id: uuid.UUID
    amount: Decimal


class VendorPaymentCreate(ApiModel):
    """Create + post a vendor payment (PLAN 4.5). ``partner_id`` is the opaque vendor id (D-029);
    all cleared bills must be open, same partner, same currency. ``bank_account_id`` is the
    bank/cash account credited; ``amount`` is the cash paid. Realized FX (D-019) is computed and
    posted inside the payment entry by the service."""

    partner_id: uuid.UUID
    partner_name: str
    payment_date: date
    currency_code: str
    bank_account_id: uuid.UUID
    amount: Decimal
    description: str | None = None
    allocations: list[PaymentAllocationCreate]


class PaymentAllocationRead(ApiModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    vendor_bill_id: uuid.UUID
    allocated_amount: Decimal


class VendorPaymentRead(ApiModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    payment_number: str | None
    payment_date: date
    currency_code: str
    bank_account_id: uuid.UUID
    amount: Decimal
    journal_entry_id: uuid.UUID | None
    status: PaymentStatus
    description: str | None
    created_at: datetime
    updated_at: datetime


class VendorPaymentDetail(VendorPaymentRead):
    """Payment header WITH its allocations — the create/GET response shape."""

    allocations: list[PaymentAllocationRead]


# --- Payment runs -------------------------------------------------------------


class PaymentRunRequest(ApiModel):
    """Run a payment batch (PLAN 4.5). Selects POSTED bills with ``open_amount`` > 0 due on or
    before ``up_to_due_date`` (optionally narrowed to one ``partner_id``) and pays each partner's
    due bills in full from ``bank_account_id`` and ``payment_date`` (defaults to ``up_to_due_date``
    when omitted), one payment per partner."""

    up_to_due_date: date
    bank_account_id: uuid.UUID
    partner_id: uuid.UUID | None = None
    payment_date: date | None = None


# The former PaymentRunResult wrapper was retired with #26: POST /payment-runs now returns the
# core 202 JobSubmitted envelope, and the created payment ids live in the job's result (4P.5).


# --- AP aging -----------------------------------------------------------------


class AgingBucketRead(ApiModel):
    """Open AP for one partner bucketed by (as_of - due_date) days (PLAN 4.5). ``current`` is not
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


class AgingReportRead(ApiModel):
    """The AP aging report (PLAN 4.5): per-partner buckets plus the rolled-up totals row. A pure
    projection over open bills — no stored totals (D-021 spirit)."""

    as_of: date
    partners: list[AgingBucketRead]
    current: Decimal
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_over_90: Decimal
    total: Decimal

"""Sales-billing schemas (Pydantic v2, ApiModel base) for PLAN 7.4 — the O2C invoicing document.

A billing is created DRAFT against an order with its billed lines inline (which order line, optional
which delivery line, how much), then POSTED (which triggers the finance AR customer invoice). The
``item_id`` + ``unit_price`` + discount + ``tax_code_id`` are SNAPSHOT from the order line by the
service (the create payload names only the order line / qty) so the client cannot rewrite the priced
item. A convenience ``bill_all_delivered`` flag bills every delivered-not-yet-invoiced line in one
shot. Quantity/money are plain ``Decimal`` (D-015 via the column types). Re-exported from
``schemas/__init__``.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.sales.constants import BillingStatus


class BillingLineCreate(ApiModel):
    """One billed line on a DRAFT billing (PLAN 7.4). Names the ``sales_order_line_id`` being billed
    (the service snapshots its item + price + discount + tax code), an optional ``delivery_line_id``
    (which shipment this bills — for the docflow chain), and the ``quantity`` (> 0, capped at the
    order line's delivered-not-yet-invoiced quantity — over-billing is rejected 422)."""

    sales_order_line_id: uuid.UUID
    delivery_line_id: uuid.UUID | None = None
    quantity: Decimal


class BillingCreate(ApiModel):
    """Create a DRAFT billing against a sales order (PLAN 7.4). The order must be at least partially
    delivered. Every billed line must belong to the order and not over-bill its
    delivered-not-invoiced
    quantity. ``billing_date`` defaults to today. ``bill_all_delivered`` (when true) ignores
    ``lines``
    and bills EVERY order line's full delivered-not-yet-invoiced quantity (the convenience path);
    when
    false, ``lines`` drives the billing. The service snapshots the customer + payment terms from the
    order and claims the BIL number."""

    sales_order_id: uuid.UUID
    billing_date: date | None = None
    notes: str | None = None
    bill_all_delivered: bool = False
    lines: list[BillingLineCreate] = []


class BillingLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    sales_order_line_id: uuid.UUID
    delivery_line_id: uuid.UUID | None
    item_id: uuid.UUID
    quantity: Decimal
    unit_price: Decimal
    discount_type: str | None
    discount_value: Decimal | None
    line_amount: Decimal
    tax_code_id: uuid.UUID | None


class BillingRead(ApiModel):
    """Billing header without lines — the list-row shape."""

    id: uuid.UUID
    billing_number: str
    status: BillingStatus
    sales_order_id: uuid.UUID
    customer_id: uuid.UUID
    currency_code: str
    billing_date: date
    payment_terms_days: int
    total_amount: Decimal
    notes: str | None
    posted_at: datetime | None
    document_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class BillingDetail(BillingRead):
    """Billing header WITH its lines — the GET /{id} shape."""

    lines: list[BillingLineRead]


class BillingFilter(ApiModel):
    """List filters: by order, status and/or billing-date range."""

    sales_order_id: uuid.UUID | None = None
    status: BillingStatus | None = None
    date_from: date | None = None
    date_to: date | None = None

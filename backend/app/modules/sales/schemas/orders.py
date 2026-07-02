"""Sales quote → order schemas (Pydantic v2, ApiModel base) for PLAN 7.2.

The O2C slice of the sales ``schemas/`` package: quote + order create/update/read/filter (+ their
lines), the action payloads (send/accept/reject/convert/confirm/credit-release), and the ATP-check
response. Re-exported from ``schemas/__init__``.

Read schemas mirror the models field-for-field in snake_case; status/enum fields are typed with the
constants enums (ApiModel ``use_enum_values`` serializes them as their UPPER_SNAKE string). Money/
quantity are plain ``Decimal`` (D-015 via the column types; JSON-serialized as strings).
Create/Update carry only client-settable fields; ids, timestamps, tenant_id, the document number,
the maintained ``total_amount`` and the delivered/invoiced/credit_check fields are server-owned.
A line's ``unit_price`` is OPTIONAL on create — when omitted the service defaults it from the price
resolver (D-043); a supplied value overrides it.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.sales.constants import (
    CreditCheckStatus,
    DiscountType,
    QuoteStatus,
    SalesOrderStatus,
)

# --- Quote lines --------------------------------------------------------------


class QuoteLineCreate(ApiModel):
    """One quoted item. ``item_id`` / ``uom_id`` are opaque inventory ids (validated, D-029).
    ``unit_price`` is optional — omitted, the service defaults it from the price resolver (D-043);
    supplied, it overrides. ``discount_type`` + ``discount_value`` are an optional per-line discount
    (both omitted = no discount); the service computes the line amount."""

    item_id: uuid.UUID
    description: str | None = None
    quantity: Decimal = Field(gt=0)
    uom_id: uuid.UUID
    unit_price: Decimal | None = Field(default=None, ge=0)
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = Field(default=None, ge=0)


class QuoteLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    item_id: uuid.UUID
    description: str | None
    quantity: Decimal
    uom_id: uuid.UUID
    unit_price: Decimal
    discount_type: DiscountType | None
    discount_value: Decimal | None
    line_amount: Decimal


# --- Quotes -------------------------------------------------------------------


class QuoteCreate(ApiModel):
    """Create a DRAFT quote. ``customer_id`` must exist. ``currency_code`` defaults from the
    customer
    when omitted (validated to exist in finance). ``quote_date`` defaults to today; ``valid_until``
    (optional) is the offer expiry. At least one line is required."""

    customer_id: uuid.UUID
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    quote_date: date | None = None
    valid_until: date | None = None
    notes: str | None = None
    lines: list[QuoteLineCreate]


class QuoteUpdate(ApiModel):
    """Partial header update of a DRAFT quote; ``lines`` (when supplied) replace the lines wholesale
    (revalidated + repriced). Only a DRAFT quote is editable."""

    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    quote_date: date | None = None
    valid_until: date | None = None
    notes: str | None = None
    lines: list[QuoteLineCreate] | None = None


class QuoteRead(ApiModel):
    """Quote header without lines — the list-row shape."""

    id: uuid.UUID
    quote_number: str
    status: QuoteStatus
    customer_id: uuid.UUID
    currency_code: str
    quote_date: date
    valid_until: date | None
    total_amount: Decimal
    notes: str | None
    created_at: datetime
    updated_at: datetime


class QuoteDetail(QuoteRead):
    """Quote header + its lines — the detail / action-response shape."""

    lines: list[QuoteLineRead]


class QuoteFilter(ApiModel):
    """List filters for the quotes endpoint. None means "no constraint"; the router folds the set
    into the cursor's filter fingerprint so a cursor cannot cross filtered views."""

    status: QuoteStatus | None = None
    customer_id: uuid.UUID | None = None


# --- Order lines --------------------------------------------------------------


class SalesOrderLineCreate(ApiModel):
    """One ordered item. ``item_id`` / ``uom_id`` are opaque inventory ids (validated, D-029).
    ``unit_price`` is optional (resolver default / override, the quote-line rule). ``tax_code_id``
    (optional) is the opaque finance tax code the 7.4 invoice uses."""

    item_id: uuid.UUID
    description: str | None = None
    quantity: Decimal = Field(gt=0)
    uom_id: uuid.UUID
    unit_price: Decimal | None = Field(default=None, ge=0)
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = Field(default=None, ge=0)
    tax_code_id: uuid.UUID | None = None


class SalesOrderLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    item_id: uuid.UUID
    description: str | None
    ordered_quantity: Decimal
    uom_id: uuid.UUID
    unit_price: Decimal
    discount_type: DiscountType | None
    discount_value: Decimal | None
    line_amount: Decimal
    delivered_quantity: Decimal
    invoiced_quantity: Decimal
    returned_quantity: Decimal
    tax_code_id: uuid.UUID | None


# --- Orders -------------------------------------------------------------------


class SalesOrderCreate(ApiModel):
    """Create a DRAFT order from scratch. ``customer_id`` must be ACTIVE. ``currency_code`` defaults
    from the customer when omitted. ``order_date`` defaults to today; ``requested_date`` (optional)
    is the customer's requested delivery date. At least one line is required. ``payment_terms_days``
    is snapshot from the customer (not client-settable)."""

    customer_id: uuid.UUID
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    order_date: date | None = None
    requested_date: date | None = None
    notes: str | None = None
    lines: list[SalesOrderLineCreate]


class SalesOrderUpdate(ApiModel):
    """Partial header update of a DRAFT order; ``lines`` (when supplied) replace the lines wholesale
    (revalidated + repriced). Only a DRAFT order is editable (a CONFIRMED order is a firm
    commitment)."""

    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    order_date: date | None = None
    requested_date: date | None = None
    notes: str | None = None
    lines: list[SalesOrderLineCreate] | None = None


class SalesOrderRead(ApiModel):
    """Order header without lines — the list-row shape."""

    id: uuid.UUID
    order_number: str
    status: SalesOrderStatus
    customer_id: uuid.UUID
    currency_code: str
    order_date: date
    requested_date: date | None
    payment_terms_days: int
    total_amount: Decimal
    source_quote_id: uuid.UUID | None
    credit_check_status: CreditCheckStatus | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class SalesOrderDetail(SalesOrderRead):
    """Order header + its lines — the detail / action-response shape."""

    lines: list[SalesOrderLineRead]


class SalesOrderFilter(ApiModel):
    """List filters for the orders endpoint. None means "no constraint"."""

    status: SalesOrderStatus | None = None
    customer_id: uuid.UUID | None = None


# --- Conversion + action payloads ---------------------------------------------


class ConvertQuoteToOrder(ApiModel):
    """Convert an ACCEPTED quote to a DRAFT order (PLAN 7.2). The lines/prices/currency/customer
    come
    from the quote; only the order-specific dates are supplied here (both optional — order_date
    defaults to today)."""

    order_date: date | None = None
    requested_date: date | None = None
    notes: str | None = None


# Send / accept / reject / confirm / credit-release are parameterless transitions (the target id is
# the path id); they carry no body, so there is no payload schema — the routers POST an empty body.


# --- ATP check (the availability view 7.2's order UI reads) -------------------


class AtpLineRequest(ApiModel):
    """One line in an ATP check request: an item + the requested quantity."""

    item_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class AtpCheckRequest(ApiModel):
    """A POST ATP check over a set of lines (the order-entry availability preview). ``on_date``
    (optional) defaults to today — the date the availability is evaluated for."""

    on_date: date | None = None
    lines: list[AtpLineRequest]


class AtpLineResult(ApiModel):
    """The per-line ATP outcome (D-044): availability = on-hand − committed + on-order. ``atp_ok``
    is
    True when ``available >= requested``; ``shortfall`` is ``requested − available`` clamped at 0
    (0 when fully available). ``backordered`` mirrors ``not atp_ok`` — the flag confirm records on
    the
    order line. The on_hand / committed / on_order components are surfaced so the UI can explain the
    number."""

    item_id: uuid.UUID
    requested_quantity: Decimal
    on_hand: Decimal
    committed: Decimal
    on_order: Decimal
    available: Decimal
    atp_ok: bool
    backordered: bool
    shortfall: Decimal


class AtpCheckResponse(ApiModel):
    """The ATP check result over the requested lines (D-044). Informational: a shortfall flags a
    backorder, it does NOT block — the hard block is credit, evaluated only at confirm."""

    on_date: date
    lines: list[AtpLineResult]

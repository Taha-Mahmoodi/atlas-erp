"""Sales master + pricing schemas (Pydantic v2, ApiModel base) for PLAN 7.1.

The masters slice of the sales ``schemas/`` package (STRUCTURE §8.4: split into a package at the
400-line cap when PLAN 7.2's quote → order schemas landed — this file holds the customer master +
customer groups + price lists + the price-quote response; ``orders.py`` holds the O2C documents).
Re-exported from ``schemas/__init__`` so ``from app.modules.sales.schemas import CustomerCreate`` is
unchanged.

Read schemas mirror the models field-for-field in snake_case; status/enum fields are typed with the
constants enums (ApiModel's ``use_enum_values`` serializes them as their UPPER_SNAKE string,
matching
the column). Money/quantity are plain ``Decimal`` (D-015 via the column types; JSON-serialized as
strings). Create/Update carry only client-settable fields; ids, timestamps and tenant_id are
server-owned. ``customer_code`` / group ``code`` / price-list ``code`` are immutable after creation
(AR partner_id history and pricing references depend on them) so they are absent from the Update
schemas.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.sales.constants import (
    DEFAULT_CREDIT_LIMIT,
    DEFAULT_PAYMENT_TERMS_DAYS,
    DEFAULT_PRICE_LIST_PRIORITY,
    CustomerStatus,
    PriceListStatus,
)

# --- Customer groups ----------------------------------------------------------


class CustomerGroupCreate(ApiModel):
    """Create a customer group. ``code`` is user-supplied and unique per tenant; ``name`` is the
    display label. A group carries no pricing of its own — it is a grouping key."""

    code: str
    name: str


class CustomerGroupUpdate(ApiModel):
    """Partial update — ``code`` is immutable (customers + price lists reference the group) and so
    is deliberately absent; only ``name`` is editable."""

    name: str | None = None


class CustomerGroupRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    created_at: datetime
    updated_at: datetime


# --- Customers ----------------------------------------------------------------


class CustomerCreate(ApiModel):
    """Create a customer. ``customer_code`` is user-supplied and unique per tenant.
    ``default_currency_code`` must exist in finance's currency catalog (validated, D-029).
    ``payment_terms_days`` defaults to NET30 when omitted and must be >= 0. ``credit_limit``
    defaults
    to 0 = cash-only (D-043) and must be >= 0. ``customer_group_id`` is the optional pricing group
    (validated to exist). ``status`` defaults to ACTIVE."""

    customer_code: str
    name: str
    default_currency_code: str = Field(min_length=3, max_length=3)
    status: CustomerStatus = CustomerStatus.ACTIVE
    customer_group_id: uuid.UUID | None = None
    payment_terms_days: int = Field(default=DEFAULT_PAYMENT_TERMS_DAYS, ge=0)
    credit_limit: Decimal = Field(default=Decimal(DEFAULT_CREDIT_LIMIT), ge=0)
    tax_reference: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    notes: str | None = None


class CustomerUpdate(ApiModel):
    """Partial update — every field optional; ``customer_code`` is immutable (AR partner_id history
    /
    later orders reference the customer) and so is deliberately absent. A changed
    ``default_currency_code`` is re-validated against finance; a changed ``customer_group_id`` is
    re-validated to exist (or cleared to NULL); ``payment_terms_days`` / ``credit_limit`` must stay
    >= 0; ``status`` may move freely between ACTIVE/BLOCKED/INACTIVE."""

    name: str | None = None
    default_currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    status: CustomerStatus | None = None
    customer_group_id: uuid.UUID | None = None
    payment_terms_days: int | None = Field(default=None, ge=0)
    credit_limit: Decimal | None = Field(default=None, ge=0)
    tax_reference: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    notes: str | None = None


class CustomerRead(ApiModel):
    id: uuid.UUID
    customer_code: str
    name: str
    status: CustomerStatus
    customer_group_id: uuid.UUID | None
    default_currency_code: str
    payment_terms_days: int
    credit_limit: Decimal
    tax_reference: str | None
    email: str | None
    phone: str | None
    address: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CustomerFilter(ApiModel):
    """List filters for the customers endpoint. None means "no constraint"; the router folds the set
    into the cursor's filter fingerprint so a cursor cannot cross filtered views."""

    status: CustomerStatus | None = None


# --- Price lists --------------------------------------------------------------


class PriceListCreate(ApiModel):
    """Create a price list (condition header). ``code`` is user-supplied and unique per tenant.
    ``currency_code`` must exist in finance. ``customer_group_id`` (optional, validated) targets a
    group, or is NULL for a general list. ``valid_from`` is required; ``valid_to`` (optional) must
    be
    >= valid_from. ``status`` defaults to ACTIVE; ``priority`` defaults to 0 (>= 0)."""

    code: str
    name: str
    currency_code: str = Field(min_length=3, max_length=3)
    customer_group_id: uuid.UUID | None = None
    valid_from: date
    valid_to: date | None = None
    status: PriceListStatus = PriceListStatus.ACTIVE
    priority: int = Field(default=DEFAULT_PRICE_LIST_PRIORITY, ge=0)


class PriceListUpdate(ApiModel):
    """Partial update — ``code`` is immutable (deliberately absent). ``currency_code`` /
    ``customer_group_id`` are re-validated when changed; the resulting ``[valid_from, valid_to]``
    window must stay coherent (valid_to >= valid_from); ``priority`` must stay >= 0; ``status`` may
    move freely between ACTIVE/INACTIVE."""

    name: str | None = None
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    customer_group_id: uuid.UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: PriceListStatus | None = None
    priority: int | None = Field(default=None, ge=0)


class PriceListRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    currency_code: str
    customer_group_id: uuid.UUID | None
    valid_from: date
    valid_to: date | None
    status: PriceListStatus
    priority: int
    created_at: datetime
    updated_at: datetime


class PriceListFilter(ApiModel):
    """List filters for the price-lists endpoint. None means "no constraint"."""

    status: PriceListStatus | None = None


# --- Price-list items (nested under a price list) -----------------------------


class PriceListItemCreate(ApiModel):
    """Add a base price for an item to a price list. ``item_id`` is an opaque inventory item id,
    validated to exist via inventory/queries (D-029). ``unit_price`` is the base price (>= 0) in the
    list's currency. ``min_quantity`` (default 0, >= 0) is the optional quantity floor. The
    ``price_list_id`` comes from the path, not the body."""

    item_id: uuid.UUID
    unit_price: Decimal = Field(ge=0)
    min_quantity: Decimal = Field(default=Decimal(0), ge=0)


class PriceListItemRead(ApiModel):
    id: uuid.UUID
    price_list_id: uuid.UUID
    item_id: uuid.UUID
    unit_price: Decimal
    min_quantity: Decimal
    created_at: datetime
    updated_at: datetime


# --- Price quote (the resolved price) -----------------------------------------


class PriceQuoteRead(ApiModel):
    """The resolved base price for an item + customer + date + quantity (PLAN 7.1) — the output of
    the condition resolver (D-043). ``matched`` is True when an ACTIVE price list yielded a price;
    then ``unit_price`` + the winning list's id/code/currency are populated. When ``matched`` is
    False (no applicable list) the price fields are NULL — 7.2's order entry then requires a manual
    price or override. No discount is applied here (the price list gives the base price only;
    discounts are a per-order-line concern in 7.2)."""

    matched: bool
    item_id: uuid.UUID
    customer_id: uuid.UUID
    quote_date: date
    quantity: Decimal
    currency_code: str | None = None
    unit_price: Decimal | None = None
    price_list_id: uuid.UUID | None = None
    price_list_code: str | None = None

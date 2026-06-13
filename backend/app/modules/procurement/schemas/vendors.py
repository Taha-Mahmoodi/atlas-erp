"""Vendor-master request/response schemas (Pydantic v2, ApiModel base) for PLAN 6.1.

First file in the procurement ``schemas/`` package (STRUCTURE §3: split at the 400-line cap when
PLAN 6.2's requisition/RFQ/PO/approval-rule schemas landed). Re-exported from ``schemas/__init__``
so
``from app.modules.procurement.schemas import VendorCreate`` keeps working from one surface.

Read schemas mirror the models field-for-field in snake_case; ``status`` is typed with the
``VendorStatus`` constant (ApiModel's ``use_enum_values`` serializes it as its UPPER_SNAKE string,
matching the column). The vendor master carries no money/quantity fields — everything here is a
scalar (codes, names, an int net-days, contact strings) — so no Decimal-as-string handling is
needed (D-015 applies only where money/qty appears, which is the P2P documents in 6.2+).

Create/Update carry only client-settable fields; ids, timestamps and tenant_id are server-owned.
``payment_terms_days`` is OPTIONAL on create (defaulted to NET30 by the service when omitted);
``vendor_code`` is immutable after creation (AP partner_id history and later POs reference the
vendor) so it is absent from VendorUpdate.
"""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.procurement.constants import DEFAULT_PAYMENT_TERMS_DAYS, VendorStatus

# --- Vendors ------------------------------------------------------------------


class VendorCreate(ApiModel):
    """Create a vendor. ``vendor_code`` is user-supplied and unique per tenant.
    ``default_currency_code`` must exist in finance's currency catalog (validated, D-029).
    ``payment_terms_days`` defaults to NET30 when omitted and must be >= 0. ``status`` defaults
    to ACTIVE."""

    vendor_code: str
    name: str
    default_currency_code: str = Field(min_length=3, max_length=3)
    status: VendorStatus = VendorStatus.ACTIVE
    payment_terms_days: int = Field(default=DEFAULT_PAYMENT_TERMS_DAYS, ge=0)
    tax_reference: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    notes: str | None = None


class VendorUpdate(ApiModel):
    """Partial update — every field optional; ``vendor_code`` is immutable (AP partner_id history /
    later POs reference the vendor) and so is deliberately absent. A changed
    ``default_currency_code`` is re-validated against finance; a changed ``payment_terms_days`` must
    stay >= 0; ``status`` may move freely between ACTIVE/BLOCKED/INACTIVE."""

    name: str | None = None
    default_currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    status: VendorStatus | None = None
    payment_terms_days: int | None = Field(default=None, ge=0)
    tax_reference: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    notes: str | None = None


class VendorRead(ApiModel):
    id: uuid.UUID
    vendor_code: str
    name: str
    status: VendorStatus
    default_currency_code: str
    payment_terms_days: int
    tax_reference: str | None
    email: str | None
    phone: str | None
    address: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class VendorFilter(ApiModel):
    """List filters for the vendors endpoint. None means "no constraint"; the router folds the set
    into the cursor's filter fingerprint so a cursor cannot cross filtered views."""

    status: VendorStatus | None = None


# --- Approved items (nested under a vendor) -----------------------------------


class VendorApprovedItemCreate(ApiModel):
    """Approve an inventory item for a vendor (info-record-lite). ``item_id`` is an opaque inventory
    item id, validated to exist via inventory/queries (D-029). ``vendor_item_code`` is the vendor's
    own SKU (optional). The ``vendor_id`` comes from the path, not the body."""

    item_id: uuid.UUID
    vendor_item_code: str | None = None
    is_active: bool = True


class VendorApprovedItemRead(ApiModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    item_id: uuid.UUID
    vendor_item_code: str | None
    is_active: bool
    created_at: datetime

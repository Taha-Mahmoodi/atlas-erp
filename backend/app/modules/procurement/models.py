"""Procurement vendor master (PLAN 6.1): the ``Vendor`` entity and the v1 "approved items"
info-record-lite (``VendorApprovedItem``).

ONE file (STRUCTURE §8.4: split into a models/ package only at the 400-line cap, the inventory
precedent); two tables fit well under it.

Design decisions baked in here:

- **The vendor's id IS finance AP's opaque ``partner_id`` (D-029).** Finance owns no vendor table;
  every AP bill/payment carries an opaque ``partner_id`` (no FK) + a denormalized ``partner_name``.
  That id is exactly this ``Vendor.id``. Procurement is ABOVE finance in the dependency order, so
  finance can never FK to this table; the link is by opaque id only, resolved through
  ``procurement/queries.get_vendor_for_partner``.

- **``payment_terms_days`` is a plain net-days integer on the vendor**, not a terms master — it
  drives AP due dates (bill_date + days), the simplest model that matches how AP already computes
  them (constants.py documents the deferral of richer term schedules). A DB CHECK keeps it >= 0.

- **``VendorApprovedItem.item_id`` is an OPAQUE inventory item id (D-029)** — a plain ``sa.Uuid``
  column, NOT a ``tenant_fk`` to ``inv_items``: procurement may READ inventory via
  ``inventory/queries.item_exists`` (validated in the service) but never cross-module FK-references
  it. Contrast the vendor link on the same table, which IS a composite ``tenant_fk`` to
  ``proc_vendors`` (an intra-module parent). This is the info-record-lite: the vendor↔item link
  with the vendor's own SKU, but NO price / lead-time / valid-from-to (deferred per parity).

Both tables follow the D-007 composite-tenant-FK backstop: ``tenant_unique()`` on every table a
child references, ``tenant_fk()`` composites for every INTRA-module cross-row link. Enum-valued
columns are plain ``sa.String`` storing the StrEnum's UPPER_SNAKE value (the core/finance/inventory
convention, no ``sa.Enum``); the service maps to/from the constants classes.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.modules.procurement.constants import DEFAULT_PAYMENT_TERMS_DAYS, VendorStatus


class Vendor(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A vendor / supplier master record (parity: supplier master — FULL in v1).

    ``vendor_code`` is user-supplied and unique per tenant (no auto-numbering — the account-code /
    item-code precedent). ``status`` gates new POs in 6.2 (BLOCKED/INACTIVE vendors cannot receive
    them). ``default_currency_code`` defaults onto a vendor's bills/POs and is validated to exist in
    finance's currency catalog (D-029, via ``finance/queries.currency_exists``).
    ``payment_terms_days`` is the net-days value AP adds to a bill date for the due date (CHECK >=
    0). Contact fields are kept modest (email/phone + a single address line). The row's ``id`` IS
    the opaque ``partner_id`` finance AP stores (D-029). Audited (D-010): master data driving where
    money is owed."""

    __tablename__ = "proc_vendors"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "vendor_code", name="uq_proc_vendors_tenant_id_vendor_code"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        sa.CheckConstraint(
            "payment_terms_days >= 0", name="ck_proc_vendors_payment_terms_days_non_negative"
        ),
        # The vendor list filters on (tenant_id, status) and sorts by vendor_code (PERFORMANCE §1):
        # composite so the filtered + paginated reference list is index-served.
        sa.Index("ix_proc_vendors_tenant_id_status", "tenant_id", "status"),
    )

    vendor_code: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=VendorStatus.ACTIVE.value,
        server_default="ACTIVE",
    )
    default_currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=DEFAULT_PAYMENT_TERMS_DAYS,
        server_default=str(DEFAULT_PAYMENT_TERMS_DAYS),
    )
    # The vendor's tax/VAT registration reference (free text, optional).
    tax_reference: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    email: Mapped[str | None] = mapped_column(sa.String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class VendorApprovedItem(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """An approved (vendor, item) link — the v1 info-record-lite (parity: purchasing info records,
    PARTIAL).

    Records that a vendor is an approved source for an inventory item, optionally with the vendor's
    own SKU (``vendor_item_code``). ``vendor_id`` is a composite ``tenant_fk`` to ``proc_vendors``
    (an intra-module parent). ``item_id`` is an OPAQUE inventory item id (D-029): a plain
    ``sa.Uuid``, NOT an FK — the service validates it exists via ``inventory/queries.item_exists``.
    ``UNIQUE(tenant_id, vendor_id, item_id)`` so a vendor approves an item at most once.
    Deliberately NO price / lead-time / valid-from-to: those time-dependent conditions are deferred
    per the parity doc and would extend this table later.

    NOT AuditMixin: an approved-item link is low-churn config that rides the vendor's audit story
    (it has no independent lifecycle), keeping the audit log lean — the same reasoning inventory's
    ``UomConversion`` applies to the per-item conversion rows."""

    __tablename__ = "proc_vendor_approved_items"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "vendor_id",
            "item_id",
            name="uq_proc_vendor_approved_items_tenant_id_vendor_id_item_id",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("proc_vendors", "vendor_id"),
        # FK index for "this vendor's approved items" — the nested list endpoint's read path.
        sa.Index(
            "ix_proc_vendor_approved_items_tenant_id_vendor_id", "tenant_id", "vendor_id"
        ),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Opaque inventory item id (D-029): no cross-module FK; validated via inventory/queries.
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    vendor_item_code: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )

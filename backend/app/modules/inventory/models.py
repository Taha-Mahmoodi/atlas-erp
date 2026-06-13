"""Inventory master data (PLAN 5.1): item categories, UoMs, per-item UoM conversions, the item
master, and the lot/serial instance tables.

Single ``models.py`` (STRUCTURE §3: split into a models/ package only at the 400-line cap, the
finance precedent). Six tables, all under that for 5.1.

Design decisions baked in here:

- **Costing wiring on the category (D-020 + D-029).** ``ItemCategory`` carries the default
  costing method AND the three GL accounts COGS/valuation posting will need —
  ``inventory_account_id``, ``cogs_account_id``, ``price_difference_account_id`` — as OPAQUE
  ``sa.Uuid`` columns, NOT cross-module FKs (D-029): finance owns those accounts; the inventory
  service validates each id exists via ``finance/queries.py`` when set, and the journal-line
  precedent already stores finance dimension ids without an FK on a cross-module table. They are
  NULLABLE on the category (a SERVICE-only category needs none); a STOCKED item's category must
  carry them before that item can post moves — validated when moves land (5.2+), not in 5.1.

- **costing_method on the item (D-020).** Defaulted from the category at create but STORED on the
  item, because the item is the costing unit and D-020 lets it change only while no stock exists.

- **UoM convention (the chosen one of the two the task offered): per-item BASE + ALTERNATES.**
  Each item has ONE ``base_uom_id``; quantities are stored/costed in the base UoM. An
  ``UomConversion`` row expresses an ALTERNATE UoM for that item as ``factor_to_base`` —
  multiplying a quantity in the alternate UoM by the factor yields the base-UoM quantity (an
  item whose base is EA and has BOX with factor 12 means 1 BOX = 12 EA). ``UNIQUE(tenant_id,
  item_id, alt_uom_id)`` — one factor per (item, alternate). This is the standard ERP shape
  (S/4HANA's alternative-UoM table): simpler than a full from/to graph, and base<->alt and
  alt<->alt conversions all derive from the single per-alternate factor (service.convert_quantity).

- **Lot / SerialNumber are MASTER tables only for 5.1.** They are defined so the schema is
  receipt-ready, but instances are CREATED during receipts (5.2+); 5.1 ships no CRUD for them.

All tables follow the D-007 composite-tenant-FK backstop: ``tenant_unique()`` on every table
referenced by a child, ``tenant_fk()`` composites for every cross-row link so a child can never
point at another tenant's parent. Enum-valued columns are plain ``sa.String`` storing the
StrEnum's UPPER_SNAKE value (the core/finance convention, no ``sa.Enum``); the service maps
to/from the constants classes.
"""

import uuid
from datetime import datetime
from decimal import Decimal

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
from app.core.money import QuantityType
from app.modules.inventory.constants import CostingMethod, LotStatus, TrackingMode


class ItemCategory(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A grouping of items sharing a default costing method and GL-account wiring (D-020/D-029).

    ``default_costing_method`` is copied onto each item at create (the item then owns its method).
    The three account ids are OPAQUE finance GL-account uuids (D-029): NULLABLE here (a category of
    SERVICE items needs none), validated-present-in-finance only when supplied, and required on a
    STOCKED item's category before that item can post stock moves (enforced in 5.2+). Audited
    (D-010): category configuration drives where COGS lands."""

    __tablename__ = "inv_item_categories"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_inv_item_categories_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    default_costing_method: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=CostingMethod.MOVING_AVERAGE.value,
        server_default="MOVING_AVERAGE",
    )
    # Opaque finance GL-account ids (D-029): no cross-module FK; the service validates each via
    # finance/queries when set. Dr COGS / Cr inventory at goods issue; price_difference absorbs
    # moving-average zero-quantity rounding flushes (D-020).
    inventory_account_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    cogs_account_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    price_difference_account_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


class Uom(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A unit-of-measure definition (e.g. EA, KG, BOX). Just the unit's identity — base-ness is
    NOT here: which UoM is base is decided PER ITEM (``Item.base_uom_id``), and alternate-UoM
    factors live on ``UomConversion``. Audited (D-010): master data."""

    __tablename__ = "inv_uoms"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_inv_uoms_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
    )

    code: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)


class Item(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """The item master (parity: material/product master with item types + multi-UoM).

    ``item_code`` is user-supplied and unique per tenant (no auto-numbering — the account-code
    precedent). ``item_type`` decides stock participation; only STOCKED items may carry a
    non-NONE ``tracking_mode`` and meaningful costing (the service enforces it). ``costing_method``
    is defaulted from the category at create but stored here (D-020). ``base_uom_id`` is the unit
    every quantity for this item is stored/costed in; alternate UoMs hang off ``UomConversion``.
    ``reorder_point``/``reorder_quantity`` belong to the item master now though reorder PLANNING
    lands later. Audited (D-010): master data."""

    __tablename__ = "inv_items"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "item_code", name="uq_inv_items_tenant_id_item_code"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("inv_item_categories", "category_id"),
        tenant_fk("inv_uoms", "base_uom_id"),
        # The list filters on (tenant_id, item_type, category_id, is_active) — composite so the
        # filtered + paginated list is index-served (PERFORMANCE §1).
        sa.Index(
            "ix_inv_items_tenant_id_item_type_category_id_is_active",
            "tenant_id",
            "item_type",
            "category_id",
            "is_active",
        ),
        # FK index for the per-category item lookups (PERFORMANCE §1).
        sa.Index("ix_inv_items_tenant_id_category_id", "tenant_id", "category_id"),
    )

    item_code: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    item_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    base_uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    costing_method: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    tracking_mode: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, default=TrackingMode.NONE.value, server_default="NONE"
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    # Reorder-point planning is a later PLAN phase, but the fields belong to the item master now.
    reorder_point: Mapped[Decimal | None] = mapped_column(QuantityType(), nullable=True)
    reorder_quantity: Mapped[Decimal | None] = mapped_column(QuantityType(), nullable=True)


class UomConversion(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """A per-item ALTERNATE unit of measure and its factor to the item's base UoM (PLAN 5.1).

    Convention (chosen): ``factor_to_base`` multiplies an alternate-UoM quantity to yield the
    base-UoM quantity (base EA, alt BOX, factor 12 ⇒ 1 BOX = 12 EA). One row per (item, alternate)
    — ``UNIQUE(tenant_id, item_id, alt_uom_id)``. NOT AuditMixin: conversions are low-churn config
    that ride the item's audit story (they have no independent lifecycle), keeping the audit log
    lean — the same reasoning core applies to RefreshSession. The DB CHECK guarantees the factor is
    positive on both engines (a zero/negative factor would make conversion undefined)."""

    __tablename__ = "inv_uom_conversions"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "item_id",
            "alt_uom_id",
            name="uq_inv_uom_conversions_tenant_id_item_id_alt_uom_id",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("inv_items", "item_id"),
        tenant_fk("inv_uoms", "alt_uom_id"),
        sa.CheckConstraint("factor_to_base > 0", name="ck_inv_uom_conversions_factor_positive"),
        # FK index for "this item's conversions" — the nested list endpoint's read path.
        sa.Index("ix_inv_uom_conversions_tenant_id_item_id", "tenant_id", "item_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    alt_uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    factor_to_base: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)


class Lot(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A lot/batch instance for a LOT-tracked item (parity: batch management). MASTER table for
    5.1: defined so receipts can populate it (5.2+); no CRUD ships now. ``lot_code`` is unique per
    (tenant, item). ``received_at`` is set when a receipt creates the lot. Audited (D-010): batch
    identity is traceability-relevant."""

    __tablename__ = "inv_lots"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "item_id", "lot_code", name="uq_inv_lots_tenant_id_item_id_lot_code"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("inv_items", "item_id"),
        sa.Index("ix_inv_lots_tenant_id_item_id", "tenant_id", "item_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    lot_code: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(12), nullable=False, default=LotStatus.AVAILABLE.value, server_default="AVAILABLE"
    )
    received_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class SerialNumber(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A serial-number instance for a SERIAL-tracked item (parity: serial management). MASTER
    table for 5.1: defined so receipts can populate it (5.2+); no CRUD ships now. ``serial_code``
    is unique per (tenant, item). Audited (D-010): unit identity is traceability-relevant."""

    __tablename__ = "inv_serials"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "item_id",
            "serial_code",
            name="uq_inv_serials_tenant_id_item_id_serial_code",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("inv_items", "item_id"),
        sa.Index("ix_inv_serials_tenant_id_item_id", "tenant_id", "item_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    serial_code: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(12), nullable=False, default="IN_STOCK", server_default="IN_STOCK"
    )
    received_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

"""Sales condition-style pricing (PLAN 7.1): the ``PriceList`` condition header and its
``PriceListItem`` per-item base prices.

Second file in the sales ``models/`` package; re-exported from ``models/__init__``.

This is the condition-style price model the s4hana-parity Sales section scopes to v1 — price lists
by currency / customer group / date range with a base unit price per item — NOT the generalized
access-sequence / pricing-procedure engine (no quantity scales beyond a single optional
``min_quantity`` floor, no freight/tax condition types, no pricing procedure). The deterministic
best-match resolver lives in ``service/price_resolution.py`` (exposed by ``queries.resolve_price``).

Design decisions baked in here:

- **A ``PriceList`` is a CONDITION header**: a currency, an OPTIONAL ``customer_group_id`` (NULL =
  general, applies to every customer regardless of group; set = targets that group), a
  ``[valid_from, valid_to]`` date window (``valid_to`` NULL = open-ended), a ``status``, and a
  ``priority`` integer. When several ACTIVE lists match the same item/customer/date/currency/qty,
  the resolver picks by priority (highest), then specificity (group-targeted over general), then
  latest ``valid_from`` (D-043 resolution order, documented on ``resolve_price``).

- **``customer_group_id`` is an intra-module composite ``tenant_fk``** (nullable) to
  ``sales_customer_groups`` — the same group rows a customer belongs to, so a list and a customer
  match on identical ids.

- **``PriceListItem`` carries ONE base unit price per (list, item)** — ``UNIQUE(tenant,
  price_list_id, item_id)``. ``min_quantity`` defaults to 0 and is the only scale knob in v1 (a list
  applies when ordered qty >= min_quantity); genuine multi-tier quantity scales (several prices per
  item, each with its own break) are a documented later. ``item_id`` is an OPAQUE inventory item id
  (D-029) — a plain ``sa.Uuid``, NOT an FK to ``inv_items``: the service validates it exists via
  ``inventory/queries.item_exists``.

Money columns use ``MoneyType``; quantity uses ``QuantityType`` (D-015, exact on both engines).
Cross-row links are composite tenant FKs (D-007 backstop) EXCEPT ``item_id`` (opaque, no FK —
D-029). Enum-valued columns are plain ``sa.String`` storing the StrEnum value.
"""

import uuid
from datetime import date

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
from app.core.money import MoneyType, QuantityType
from app.modules.sales.constants import DEFAULT_PRICE_LIST_PRIORITY, PriceListStatus


class PriceList(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A condition-style price list (parity: pricing PARTIAL — by currency/group/date).

    ``code`` is user-supplied and unique per tenant; ``name`` is the display label.
    ``currency_code`` is the currency the list prices in (a list matches only orders in that
    currency, validated to exist in finance). ``customer_group_id`` (nullable composite tenant FK)
    targets a group, or is NULL for a GENERAL list applying to all customers. ``[valid_from,
    valid_to]`` is the inclusive date window (``valid_to`` NULL = open-ended). ``status`` is
    ACTIVE/INACTIVE (only ACTIVE lists are priced from). ``priority`` is the highest-wins tie-break
    when several lists match (D-043). Audited (D-010): pricing config is consequential.
    ``tenant_unique`` so its items composite-FK to it."""

    __tablename__ = "sales_price_lists"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "code", name="uq_sales_price_lists_tenant_id_code"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # The optional targeted group (intra-module parent): a composite tenant FK so a list can
        # never target another tenant's group. NULL = a general list (applies to all customers).
        tenant_fk("sales_customer_groups", "customer_group_id"),
        sa.CheckConstraint(
            "priority >= 0", name="ck_sales_price_lists_priority_non_negative"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_sales_price_lists_valid_window",
        ),
        # The resolver filters ACTIVE lists by (currency, group, date) and orders the small
        # candidate set by priority/valid_from (PERFORMANCE §6): this composite serves the fetch.
        sa.Index(
            "ix_sales_price_lists_resolver",
            "tenant_id",
            "currency_code",
            "customer_group_id",
            "valid_from",
        ),
    )

    code: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    # NULL = a general list (applies to every customer); set = targets that customer group.
    customer_group_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    valid_from: Mapped[date] = mapped_column(sa.Date, nullable=False)
    # NULL = open-ended (no expiry).
    valid_to: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=PriceListStatus.ACTIVE.value,
        server_default="ACTIVE",
    )
    priority: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=DEFAULT_PRICE_LIST_PRIORITY,
        server_default=str(DEFAULT_PRICE_LIST_PRIORITY),
    )


class PriceListItem(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """A single base unit price for an item on a price list (PLAN 7.1).

    ``price_list_id`` is a composite ``tenant_fk`` to ``sales_price_lists`` (an intra-module).
    ``item_id`` is an OPAQUE inventory item id (D-029): a plain ``sa.Uuid``, NOT an FK — the service
    validates it exists via ``inventory/queries.item_exists``. ``unit_price`` is the base price in
    the list's currency. ``min_quantity`` (default 0) is the optional quantity floor: the line
    applies only when the ordered quantity is >= it (v1's single scale knob — multi-tier scales are
    a documented later). ``UNIQUE(tenant, price_list_id, item_id)`` so an item appears at most once
    per list.

    NOT AuditMixin: a price-list item rides the list's audit story (no independent lifecycle),
    keeping the audit log lean — the same reasoning the procurement ``VendorApprovedItem`` and
    inventory ``UomConversion`` rows apply."""

    __tablename__ = "sales_price_list_items"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "price_list_id",
            "item_id",
            name="uq_sales_price_list_items_tenant_id_price_list_id_item_id",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("sales_price_lists", "price_list_id"),
        sa.CheckConstraint(
            "min_quantity >= 0", name="ck_sales_price_list_items_min_quantity_non_negative"
        ),
        # FK index for "this list's items" — the nested list endpoint's read path AND the resolver's
        # per-candidate-list item lookup.
        sa.Index(
            "ix_sales_price_list_items_tenant_id_price_list_id",
            "tenant_id",
            "price_list_id",
        ),
        # The resolver finds a price by (item, list) across the candidate lists: index item_id under
        # the tenant so that lookup is served.
        sa.Index(
            "ix_sales_price_list_items_tenant_id_item_id", "tenant_id", "item_id"
        ),
    )

    price_list_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Opaque inventory item id (D-029): no cross-module FK; validated via inventory/queries.
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    unit_price: Mapped[object] = mapped_column(MoneyType, nullable=False)
    min_quantity: Mapped[object] = mapped_column(
        QuantityType, nullable=False, default=0, server_default="0"
    )

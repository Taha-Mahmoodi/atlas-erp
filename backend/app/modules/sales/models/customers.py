"""Sales customer master (PLAN 7.1): the ``CustomerGroup`` grouping master and the ``Customer``
entity — near-symmetric with the procurement vendor master.

First file in the sales ``models/`` package (STRUCTURE §3: a models/ package from the start because
customers + pricing together exceed the 400-line cap, the finance/inventory/procurement precedent).
Re-exported from ``models/__init__`` so ``from app.modules.sales.models import Customer`` works from
one surface.

Design decisions baked in here:

- **The customer's id IS finance AR's opaque ``partner_id`` (D-029).** Finance owns no customer
  table; every AR invoice/receipt carries an opaque ``partner_id`` (no FK) + a denormalized
  ``partner_name``. That id is exactly this ``Customer.id``. Sales is ABOVE finance in the
  dependency order, so finance can never FK to this table; the link is by opaque id only, resolved
  through ``sales/queries.get_customer_for_partner`` — the exact mirror of the vendor↔partner_id
  link.

- **``credit_limit`` is a non-null ``MoneyType`` (D-043).** It is the maximum outstanding AR the
  customer may carry: 0 (the default) = cash-only (no open credit), a positive value = the ceiling.
  No NULL/unlimited sentinel (constants.py documents why). A DB CHECK keeps it >= 0; 7.2's order
  confirmation reads it for the static credit-limit block.

- **``payment_terms_days`` is a plain net-days integer** (30 = NET30) driving AR due dates
  (invoice_date + days), the vendor precedent; a DB CHECK keeps it >= 0.

- **``customer_group_id`` is an intra-module composite ``tenant_fk``** to ``sales_customer_groups``
  (nullable — a customer need not belong to a group). Contrast finance/inventory ids, which when
  referenced cross-module are opaque; the group is sales-owned so it is a real composite FK.

Both tables follow the D-007 composite-tenant-FK backstop: ``tenant_unique()`` on every table a
child references, ``tenant_fk()`` composites for every INTRA-module cross-row link. Enum-valued
columns are plain ``sa.String`` storing the StrEnum's UPPER_SNAKE value (the core/finance/inventory/
procurement convention, no ``sa.Enum``); the service maps to/from the constants classes.
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
from app.core.money import MoneyType
from app.modules.sales.constants import (
    DEFAULT_CREDIT_LIMIT,
    DEFAULT_PAYMENT_TERMS_DAYS,
    CustomerStatus,
)


class CustomerGroup(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A customer group — a lean grouping master pricing keys on (PLAN 7.1).

    ``code`` is user-supplied and unique per tenant; ``name`` is the display label. The group
    carries NO pricing of its own: it is purely a key a ``Customer`` belongs to and a ``PriceList``
    can target (constants.py documents the master-table-over-free-string choice). Audited (D-010): a
    grouping that steers which prices a customer sees is master data worth tracking.
    ``tenant_unique`` so customers + price lists can composite-FK to it."""

    __tablename__ = "sales_customer_groups"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "code", name="uq_sales_customer_groups_tenant_id_code"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
    )

    code: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)


class Customer(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A customer master record (parity: customer master — PARTIAL core sales data in v1, not the
    multi-role business-partner model).

    ``customer_code`` is user-supplied and unique per tenant (no auto-numbering — the vendor-code /
    item-code precedent). ``status`` gates new orders in 7.2 (BLOCKED/INACTIVE customers cannot
    receive them). ``default_currency_code`` defaults onto a customer's quotes/orders/invoices and
    is validated to exist in finance's currency catalog (D-029, via finance/queries).
    ``payment_terms_days`` is the net-days value AR adds to an invoice date for the due date (CHECK
    >= 0). ``credit_limit`` is the static credit ceiling (D-043: non-null MoneyType, 0 = cash-only,
    CHECK >= 0) 7.2 checks at order confirmation. ``customer_group_id`` (nullable composite tenant
    FK) is the optional pricing group. Contact fields are kept modest (email/phone + a single
    address line). The row's ``id`` IS the opaque ``partner_id`` finance AR stores (D-029). Audited
    (D-010): master data driving where money is owed."""

    __tablename__ = "sales_customers"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "customer_code", name="uq_sales_customers_tenant_id_customer_code"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # The optional pricing group (intra-module parent): a composite tenant FK so a customer can
        # never reference another tenant's group. Nullable — group membership is optional.
        tenant_fk("sales_customer_groups", "customer_group_id"),
        sa.CheckConstraint(
            "payment_terms_days >= 0",
            name="ck_sales_customers_payment_terms_days_non_negative",
        ),
        sa.CheckConstraint(
            "credit_limit >= 0", name="ck_sales_customers_credit_limit_non_negative"
        ),
        # The customer list filters on (tenant_id, status) and sorts by customer_code (PERFORMANCE
        # §1): composite so the filtered + paginated reference list is index-served.
        sa.Index("ix_sales_customers_tenant_id_status", "tenant_id", "status"),
    )

    customer_code: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=CustomerStatus.ACTIVE.value,
        server_default="ACTIVE",
    )
    # The optional pricing group (nullable composite tenant FK to sales_customer_groups).
    customer_group_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    default_currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=DEFAULT_PAYMENT_TERMS_DAYS,
        server_default=str(DEFAULT_PAYMENT_TERMS_DAYS),
    )
    # The static credit ceiling = max outstanding AR (D-043). Non-null; 0 = cash-only.
    credit_limit: Mapped[object] = mapped_column(
        MoneyType,
        nullable=False,
        default=DEFAULT_CREDIT_LIMIT,
        server_default=str(DEFAULT_CREDIT_LIMIT),
    )
    # The customer's tax/VAT registration reference (free text, optional).
    tax_reference: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    email: Mapped[str | None] = mapped_column(sa.String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)

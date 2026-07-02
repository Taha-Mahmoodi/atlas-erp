"""Sales quote → order documents (PLAN 7.2): ``Quote`` + ``QuoteLine`` and ``SalesOrder`` +
``SalesOrderLine`` — the O2C spine, mirrored on the procurement requisition/PO shape.

A quote is the pre-sales document (a price offer); an order is the committing O2C document (a
customer commitment ≈ a purchase order, mirrored). Each header mixes in ``DocumentMixin``
(registered in core_documents) and carries a gapless number claimed AT CREATION (D-012/D-040 — a
quote/order is referenceable the moment it exists, the procurement-document precedent, NOT finance's
number-at-post branch). ``total_amount`` is the maintained sum of line nets.

Order specifics:

- ``customer_id`` is a composite tenant FK to ``sales_customers`` (intra-module, so a real FK — the
  customer master is sales-owned). ``payment_terms_days`` is SNAPSHOT from the customer at creation
  (so a later customer edit cannot rewrite an open order's terms — the 7.4 invoice reads the
  snapshot, the PO precedent).
- ``source_quote_id`` (nullable composite tenant FK) links an order back to the ACCEPTED quote it
  was converted from (+ the docflow edge).
- ``credit_check_status`` (nullable) records the confirm-time credit result
(PASSED/BLOCKED/RELEASED,
  D-044).

Line specifics carry an OPAQUE inventory ``item_id`` / ``uom_id`` (D-029, plain ``sa.Uuid``,
validated via inventory/queries, never a cross-module FK), the resolved/overridable ``unit_price``,
an optional per-line discount (type + value), the derived ``line_amount`` (qty × unit_price −
discount), ``delivered_quantity`` (raised by 7.3), ``invoiced_quantity`` (raised by 7.4), and an
opaque finance ``tax_code_id`` (nullable — the 7.4 invoice uses it). Money/quantity use
``MoneyType`` / ``QuantityType`` (D-015, exact on both engines).

Enum-valued columns are plain ``sa.String`` storing the StrEnum's UPPER_SNAKE value; the service
maps to/from the constants classes. Every table follows the D-007 composite-tenant-FK backstop
(``tenant_unique()`` + ``tenant_fk()`` composites + ``document_fk()`` on the headers).
"""

import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.docflow import DocumentMixin, document_fk
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
from app.modules.sales.constants import QuoteStatus, SalesOrderStatus


class Quote(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A sales quotation header (PLAN 7.2). ``quote_number`` is claimed at creation (D-012/D-040).
    ``customer_id`` is a composite tenant FK to sales_customers (validated to exist at create).
    ``status`` runs the QuoteStatus lifecycle (DRAFT → SENT → ACCEPTED/REJECTED, EXPIRED on lapse,
    CONVERTED when an order is raised, CANCELLED). ``valid_until`` (nullable) is the offer expiry —
    a quote past it is EXPIRED (a lazy service check). ``total_amount`` is the maintained Σ
    line_amount. Audited (D-010): a price offer worth tracking."""

    __tablename__ = "sales_quotes"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("sales_customers", "customer_id"),
        # PERFORMANCE §1: the quote list filters on (tenant, status) and a customer's quotes by
        # status; composite so the filtered + paginated list is index-served.
        sa.Index("ix_sales_quotes_tenant_id_status", "tenant_id", "status"),
        sa.Index(
            "ix_sales_quotes_tenant_id_customer_id_status",
            "tenant_id",
            "customer_id",
            "status",
        ),
    )

    quote_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=QuoteStatus.DRAFT.value,
        server_default="DRAFT",
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    quote_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    total_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class QuoteLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One quoted item on a quote (PLAN 7.2). ``item_id`` / ``uom_id`` are OPAQUE inventory ids
    (D-029). ``unit_price`` is defaulted from the price resolver at line add and is overridable;
    the optional per-line discount (``discount_type`` PERCENT/AMOUNT + ``discount_value``) is
    applied so ``line_amount`` = qty × unit_price − discount (maintained by the service).
    UNIQUE(tenant_id, quote_id, line_number). NOT AuditMixin (header-line exclusion)."""

    __tablename__ = "sales_quote_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "quote_id", "line_number", name="uq_sales_quote_lines_quote_line"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("sales_quotes", "quote_id"),
    )

    quote_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    quantity: Mapped[object] = mapped_column(QuantityType(), nullable=False)
    uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    unit_price: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    # Optional per-line discount: PERCENT (a percentage off) or AMOUNT (an absolute per-unit amount
    # off), both nullable (no discount → both NULL). discount_value is a MoneyType (an amount, or a
    # percentage stored exact); the service interprets it by discount_type.
    discount_type: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    discount_value: Mapped[object | None] = mapped_column(MoneyType(), nullable=True)
    line_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)


class SalesOrder(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A sales order header (PLAN 7.2) — the committing O2C document. ``order_number`` is claimed at
    creation (D-012/D-040). ``customer_id`` is a composite tenant FK to sales_customers (validated
    ACTIVE at create). ``status`` runs the SalesOrderStatus lifecycle; CONFIRMED is the 7.2 gate
    (ATP + credit). ``payment_terms_days`` is snapshot from the customer at create.
    ``requested_date``
    (nullable) is the customer's requested delivery date. ``source_quote_id`` (nullable composite
    tenant FK) links the ACCEPTED quote it converted from. ``credit_check_status`` (nullable)
    records
    the confirm-time credit result (D-044). Audited (D-010): a commitment that will move money +
    stock downstream."""

    __tablename__ = "sales_orders"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("sales_customers", "customer_id"),
        tenant_fk("sales_quotes", "source_quote_id"),
        # PERFORMANCE §1: the order list filters on (tenant, status) and a customer's orders by
        # status; the (tenant, customer_id, status) index also serves the committed-quantity +
        # credit-exposure scans over a customer's confirmed orders (D-044, set-based, no N+1).
        sa.Index("ix_sales_orders_tenant_id_status", "tenant_id", "status"),
        sa.Index(
            "ix_sales_orders_tenant_id_customer_id_status",
            "tenant_id",
            "customer_id",
            "status",
        ),
    )

    order_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=SalesOrderStatus.DRAFT.value,
        server_default="DRAFT",
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    order_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    requested_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    # Net-days terms snapshot from the customer at create (the 7.4 invoice reads this snapshot so a
    # later customer edit cannot rewrite an open order's due-date math — the PO precedent).
    payment_terms_days: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    total_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    source_quote_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # The confirm-time credit result (PASSED/BLOCKED/RELEASED, D-044); NULL until confirm is
    # attempted. RELEASED is set by the privileged credit-release action.
    credit_check_status: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class SalesOrderLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One ordered item on a sales order (PLAN 7.2). ``item_id`` / ``uom_id`` are OPAQUE inventory
    ids (D-029); ``tax_code_id`` is an opaque finance tax code (nullable — the 7.4 invoice uses it).
    ``unit_price`` + the optional per-line discount drive ``line_amount`` (qty × unit_price −
    discount, maintained by the service). ``ordered_quantity`` is the committed quantity;
    ``delivered_quantity`` (default 0) is raised by 7.3 deliveries and the open-to-deliver +
    committed-quantity reads compute ordered − delivered; ``invoiced_quantity`` (default 0) is
    raised
    by 7.4. UNIQUE(tenant_id, order_id, line_number). NOT AuditMixin (header-line exclusion)."""

    __tablename__ = "sales_order_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "order_id", "line_number", name="uq_sales_order_lines_order_line"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("sales_orders", "order_id"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    ordered_quantity: Mapped[object] = mapped_column(QuantityType(), nullable=False)
    uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    unit_price: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    discount_type: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    discount_value: Mapped[object | None] = mapped_column(MoneyType(), nullable=True)
    line_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    # Raised by 7.3 outbound deliveries; ordered − delivered is the still-open-to-deliver quantity
    # AND the committed quantity an ATP scan counts on a CONFIRMED/PARTIALLY_DELIVERED order
    # (D-044).
    # Default 0 so a fresh / just-confirmed line is fully open + fully committed.
    delivered_quantity: Mapped[object] = mapped_column(
        QuantityType(), nullable=False, default=0, server_default="0"
    )
    # Raised by 7.4 billing; delivered − invoiced is the open-to-invoice quantity. Default 0.
    invoiced_quantity: Mapped[object] = mapped_column(
        QuantityType(), nullable=False, default=0, server_default="0"
    )
    # Raised by 7.4 returns (RMA); invoiced − returned is the open-to-return quantity (the return
    # cap
    # is INVOICED, not delivered — a credit note must reduce a real invoice, D-046). Default 0.
    returned_quantity: Mapped[object] = mapped_column(
        QuantityType(), nullable=False, default=0, server_default="0"
    )
    tax_code_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)

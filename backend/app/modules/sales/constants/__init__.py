"""Sales constants (STRUCTURE §3): the customer-master + pricing enums, the pricing-engine defaults,
and the permission keys, registered into the core RBAC catalog at import (D-009).

Split into a constants/ PACKAGE at the 400-line cap when PLAN 7.4's billing + return status enums
landed (STRUCTURE §8.4, the finance constants/ precedent). Everything is re-exported here so every
existing ``from app.modules.sales.constants import X`` import keeps working from one surface:

- ``enums``: the status/type StrEnum classes + the pricing-engine numeric defaults.
- ``permissions``: the sales permission keys, registered into the RBAC catalog at import (D-009).
- ``documents``: doc types, number sequences, docflow link types and domain-event keys
(D-012/D-040).

**Customer codes are USER-SUPPLIED and unique per tenant** (the ``UNIQUE(tenant_id, customer_code)``
on sales_customers) — mirroring the procurement ``vendor_code`` and inventory ``item_code``: a
customer MASTER carries no gapless document number (a code, not a number). The SALES DOCUMENTS in
7.2+ (quotes, orders, deliveries, invoices) DO claim gapless numbers — a posted document in the
D-012 sense — but the master does not.

**Credit-limit semantics (decided here, D-043).** ``Customer.credit_limit`` is a non-null
``MoneyType`` defaulting to 0 and meaning the maximum outstanding AR (open invoices) the customer
may carry. It is interpreted as:

- ``0`` (the default) → CASH-ONLY: the customer is allowed no open credit at all, so 7.2's order
  confirmation blocks if confirming would leave ANY positive outstanding AR. New customers are
  cash-only until a limit is set explicitly.
- a positive value → the credit ceiling: 7.2 blocks confirmation when outstanding AR + the new
  order would exceed it.

There is deliberately NO "unlimited" sentinel in v1 (a NULL credit_limit is NOT used): "unlimited"
is expressed by setting a very large explicit limit, keeping the column non-null and the 7.2 check a
single unconditional comparison with no NULL branch. This is the static credit-limit block the
s4hana-parity Sales section scopes to v1 (no exposure aggregation across open orders/deliveries, no
finance-owned exposure ledger — documented there as a later).

**Customer group (decided here).** A customer optionally belongs to ONE ``CustomerGroup`` — a lean
``sales_customer_groups`` (tenant, code, name) MASTER table, NOT a free-string column. A master
table is chosen because pricing keys on the group: a ``PriceList`` targets a group by id (a
composite tenant FK), so both the customer and the price list reference the same group rows, the
group's name is editable in one place, and a typo'd free-string group can never silently exclude a
customer from its price list. The group carries NO pricing of its own — it is purely a grouping key.
"""

from app.modules.sales.constants.documents import (
    BILLING_DOC_TYPE,
    BILLING_INVOICED_BY_INVOICE_LINK,
    BILLING_NUMBER_PADDING,
    BILLING_NUMBER_PREFIX,
    BILLING_POSTED_EVENT_KEY,
    BILLING_SEQUENCE_NAME,
    DELIVERY_DOC_TYPE,
    DELIVERY_INVOICED_BY_BILLING_LINK,
    DELIVERY_MOVED_BY_STOCK_MOVE_LINK,
    DELIVERY_NUMBER_PADDING,
    DELIVERY_NUMBER_PREFIX,
    DELIVERY_SEQUENCE_NAME,
    DELIVERY_SHIPPED_EVENT_KEY,
    ORDER_BILLED_BY_BILLING_LINK,
    ORDER_DELIVERED_BY_DELIVERY_LINK,
    ORDER_RETURNED_BY_RETURN_LINK,
    QUOTE_CONVERTED_TO_ORDER_LINK,
    QUOTE_DOC_TYPE,
    QUOTE_NUMBER_PADDING,
    QUOTE_NUMBER_PREFIX,
    QUOTE_SEQUENCE_NAME,
    RETURN_CREDITED_BY_CREDIT_NOTE_LINK,
    RETURN_CREDITED_EVENT_KEY,
    RETURN_DOC_TYPE,
    RETURN_NUMBER_PADDING,
    RETURN_NUMBER_PREFIX,
    RETURN_RECEIVED_BY_STOCK_MOVE_LINK,
    RETURN_RECEIVED_EVENT_KEY,
    RETURN_SEQUENCE_NAME,
    SALES_ORDER_DOC_TYPE,
    SALES_ORDER_NUMBER_PADDING,
    SALES_ORDER_NUMBER_PREFIX,
    SALES_ORDER_SEQUENCE_NAME,
)
from app.modules.sales.constants.enums import (
    DEFAULT_CREDIT_LIMIT,
    DEFAULT_PAYMENT_TERMS_DAYS,
    DEFAULT_PRICE_LIST_PRIORITY,
    BillingStatus,
    CreditCheckStatus,
    CustomerStatus,
    DeliveryStatus,
    DiscountType,
    PriceListStatus,
    QuoteStatus,
    ReturnStatus,
    SalesOrderStatus,
)
from app.modules.sales.constants.permissions import (
    SALES_BILLING_MANAGE,
    SALES_BILLING_POST,
    SALES_BILLING_READ,
    SALES_CUSTOMER_MANAGE,
    SALES_CUSTOMER_READ,
    SALES_DELIVERY_MANAGE,
    SALES_DELIVERY_POST,
    SALES_DELIVERY_READ,
    SALES_ORDER_CONFIRM,
    SALES_ORDER_CREDIT_RELEASE,
    SALES_ORDER_MANAGE,
    SALES_ORDER_READ,
    SALES_PRICELIST_MANAGE,
    SALES_PRICELIST_READ,
    SALES_QUOTE_MANAGE,
    SALES_QUOTE_READ,
    SALES_RETURN_MANAGE,
    SALES_RETURN_POST,
    SALES_RETURN_READ,
)

__all__ = [
    "BILLING_DOC_TYPE",
    "BILLING_INVOICED_BY_INVOICE_LINK",
    "BILLING_NUMBER_PADDING",
    "BILLING_NUMBER_PREFIX",
    "BILLING_POSTED_EVENT_KEY",
    "BILLING_SEQUENCE_NAME",
    "BillingStatus",
    "CreditCheckStatus",
    "CustomerStatus",
    "DEFAULT_CREDIT_LIMIT",
    "DEFAULT_PAYMENT_TERMS_DAYS",
    "DEFAULT_PRICE_LIST_PRIORITY",
    "DELIVERY_DOC_TYPE",
    "DELIVERY_INVOICED_BY_BILLING_LINK",
    "DELIVERY_MOVED_BY_STOCK_MOVE_LINK",
    "DELIVERY_NUMBER_PADDING",
    "DELIVERY_NUMBER_PREFIX",
    "DELIVERY_SEQUENCE_NAME",
    "DELIVERY_SHIPPED_EVENT_KEY",
    "DeliveryStatus",
    "DiscountType",
    "ORDER_BILLED_BY_BILLING_LINK",
    "ORDER_DELIVERED_BY_DELIVERY_LINK",
    "ORDER_RETURNED_BY_RETURN_LINK",
    "PriceListStatus",
    "QUOTE_CONVERTED_TO_ORDER_LINK",
    "QUOTE_DOC_TYPE",
    "QUOTE_NUMBER_PADDING",
    "QUOTE_NUMBER_PREFIX",
    "QUOTE_SEQUENCE_NAME",
    "QuoteStatus",
    "RETURN_CREDITED_BY_CREDIT_NOTE_LINK",
    "RETURN_CREDITED_EVENT_KEY",
    "RETURN_DOC_TYPE",
    "RETURN_NUMBER_PADDING",
    "RETURN_NUMBER_PREFIX",
    "RETURN_RECEIVED_BY_STOCK_MOVE_LINK",
    "RETURN_RECEIVED_EVENT_KEY",
    "RETURN_SEQUENCE_NAME",
    "ReturnStatus",
    "SALES_BILLING_MANAGE",
    "SALES_BILLING_POST",
    "SALES_BILLING_READ",
    "SALES_CUSTOMER_MANAGE",
    "SALES_CUSTOMER_READ",
    "SALES_DELIVERY_MANAGE",
    "SALES_DELIVERY_POST",
    "SALES_DELIVERY_READ",
    "SALES_ORDER_CONFIRM",
    "SALES_ORDER_CREDIT_RELEASE",
    "SALES_ORDER_DOC_TYPE",
    "SALES_ORDER_MANAGE",
    "SALES_ORDER_NUMBER_PADDING",
    "SALES_ORDER_NUMBER_PREFIX",
    "SALES_ORDER_READ",
    "SALES_ORDER_SEQUENCE_NAME",
    "SALES_PRICELIST_MANAGE",
    "SALES_PRICELIST_READ",
    "SALES_QUOTE_MANAGE",
    "SALES_QUOTE_READ",
    "SALES_RETURN_MANAGE",
    "SALES_RETURN_POST",
    "SALES_RETURN_READ",
    "SalesOrderStatus",
]

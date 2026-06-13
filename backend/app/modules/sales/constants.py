"""Sales constants (STRUCTURE §3): the customer-master + pricing enums, the pricing-engine defaults,
and the permission keys, registered into the core RBAC catalog at import (D-009).

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap, the
finance precedent); PLAN 7.1's customer master + condition-style pricing sit under that. The
order/delivery/invoice document chain (7.2–7.4) will add its own status enums, document types and
number sequences here as it lands.

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

from enum import StrEnum

from app.core.rbac import register_permissions


class CustomerStatus(StrEnum):
    """A customer's lifecycle / usability state (parity: customer master block levels).

    - ACTIVE: usable — new quotes/orders may name this customer (the only state 7.2+ accepts).
    - BLOCKED: temporarily barred — kept for history and existing open documents, but the O2C chain
      (7.2) refuses to confirm a NEW order against it (a soft block, distinct from the credit-limit
      block; the customer can be unblocked back to ACTIVE).
    - INACTIVE: retired — no new business, retained for reporting and existing AR history.

    Transitions are unrestricted between the three (ACTIVE↔BLOCKED↔INACTIVE all allowed): a block is
    reversible and a retired customer can be reactivated. The only rule the service enforces is that
    the target is a valid CustomerStatus; no terminal state, because customer history must stay
    referenceable and a mistaken retire/block must be undoable (the append-only ledger lives in
    finance AR, not here) — the procurement VendorStatus precedent."""

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    INACTIVE = "INACTIVE"


class PriceListStatus(StrEnum):
    """A price list's usability state. Only ACTIVE lists are considered by the price resolver; an
    INACTIVE list is retained (history, a seasonal list parked between campaigns) but never priced
    from. Transitions are unrestricted between the two (a list can be re-activated)."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class DiscountType(StrEnum):
    """How a per-order-LINE discount is expressed (PLAN 7.2 applies it; defined here so the wire
    contract is stable from the start, the MatchStatus-declared-early precedent).

    - PERCENT: a percentage off the resolved base price (e.g. 10 = 10% off).
    - AMOUNT: an absolute amount off per unit in the line's currency.

    The PRICE LIST itself carries no discount — it yields the base unit price only (the condition
    base). Discounts are an order-line concern (7.2), so the resolver in 7.1 returns the base price
    untouched; this enum is the vocabulary those lines will use."""

    PERCENT = "PERCENT"
    AMOUNT = "AMOUNT"


# The default net-days a customer is created with when the payload omits it (NET30 — the common
# commercial default; AR's due-date math is invoice_date + this many days). Stored on the customer
# with a CHECK >= 0; mirrors the procurement vendor payment-terms model.
DEFAULT_PAYMENT_TERMS_DAYS = 30

# A customer's credit_limit defaults to 0 = CASH-ONLY (D-043, documented in the module docstring):
# no open credit allowed. Stored on the customer as a non-null MoneyType with a CHECK >= 0.
DEFAULT_CREDIT_LIMIT = 0

# A new price list's default priority. When several ACTIVE lists match the same item/customer/date/
# currency/quantity, the resolver picks the HIGHEST priority first (D-043 resolution order); equal
# priorities fall through to specificity (group-targeted beats general) then latest valid_from. A
# higher integer = higher priority. The default 0 means "no explicit priority"; a tenant raises a
# list's priority to make it win ties. Stored with a CHECK >= 0.
DEFAULT_PRICE_LIST_PRIORITY = 0


# --- Permissions (D-009): one key per guarded endpoint action -----------------
# Customer master (PLAN 7.1): read the customer master (+ customer groups) vs create/edit it.
# Customer-group management rides CUSTOMER_MANAGE (the inventory item/uom-conversion precedent:
# closely-related master config shares the parent entity's manage key — a group is a customer
# grouping, managed by whoever manages customers).
SALES_CUSTOMER_READ = "sales.customer.read"
SALES_CUSTOMER_MANAGE = "sales.customer.manage"
# Price lists (PLAN 7.1): read the price lists (+ their items, + a resolved price quote) vs
# create/edit them (and their items). Pricing is a distinct authority from the customer master.
SALES_PRICELIST_READ = "sales.pricelist.read"
SALES_PRICELIST_MANAGE = "sales.pricelist.manage"

register_permissions(
    SALES_CUSTOMER_READ,
    SALES_CUSTOMER_MANAGE,
    SALES_PRICELIST_READ,
    SALES_PRICELIST_MANAGE,
    descriptions={
        SALES_CUSTOMER_READ: "Read customers and customer groups",
        SALES_CUSTOMER_MANAGE: "Create and edit customers and customer groups",
        SALES_PRICELIST_READ: "Read price lists, their items and resolved price quotes",
        SALES_PRICELIST_MANAGE: "Create and edit price lists and their items",
    },
)

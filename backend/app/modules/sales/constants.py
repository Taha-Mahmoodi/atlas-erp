"""Sales constants (STRUCTURE §3): the customer-master + pricing enums, the pricing-engine defaults,
and the permission keys, registered into the core RBAC catalog at import (D-009).

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap, the
finance precedent); PLAN 7.1's customer master + condition-style pricing and PLAN 7.2's quote →
order document chain sit under that. The delivery/invoice document chain (7.3–7.4) will add its own
status enums, document types and number sequences here as it lands.

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


class QuoteStatus(StrEnum):
    """Lifecycle of a sales quotation — the pre-sales document (PLAN 7.2).

    All transitions are set IN 7.2 (a quote is a wholly-sales document; no later phase touches it):

    - DRAFT: created, editable; lines can change. The QUO number is claimed AT CREATION (D-012/D-040
      claim-at-creation — a quote is referenceable the moment it exists, the procurement-document
      precedent, not finance's number-at-post).
    - SENT: issued to the customer (DRAFT→SENT). Lines are frozen.
    - ACCEPTED: the customer accepted (SENT→ACCEPTED) — the only state convertible to an order.
    - REJECTED: the customer declined (SENT→REJECTED); terminal.
    - EXPIRED: ``valid_until`` has passed without acceptance — a lazy state the service sets on
      access/sweep (DRAFT/SENT → EXPIRED); terminal-ish (a fresh quote is raised instead).
    - CONVERTED: an order was raised from an ACCEPTED quote (the order's ``source_quote_id`` is
    set);
      terminal — a converted quote is not re-converted or edited.
    - CANCELLED: abandoned before conversion (from DRAFT/SENT/ACCEPTED); terminal."""

    DRAFT = "DRAFT"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONVERTED = "CONVERTED"
    CANCELLED = "CANCELLED"


class SalesOrderStatus(StrEnum):
    """Lifecycle of a sales order — the committing O2C document (PLAN 7.2). CONFIRMED is the key
    gate this phase implements; the later O2C phases drive the fulfilment/billing states.

    States SET in 7.2:

    - DRAFT: created (from scratch or from an ACCEPTED quote), editable; the SO number is claimed AT
      CREATION (D-012/D-040). The customer is validated ACTIVE at create.
    - CONFIRMED: the confirm gate passed (ATP evaluated + credit within limit). A CONFIRMED order is
      a firm commitment whose undelivered quantity COMMITS stock against ATP for subsequent orders
      (D-044). This is the state 7.3 deliveries pick from.
    - CREDIT_BLOCKED: confirmation was attempted but the credit exposure (open AR + open confirmed
      orders + this order) exceeded the customer's credit_limit — the HARD block (D-044). A user
      with
      ``sales.order.credit_release`` releases it (credit_check_status RELEASED) and re-confirms.
    - CANCELLED: abandoned before any delivery/invoice; terminal (a delivered/invoiced order is
      corrected downstream, never cancelled).

    States driven by LATER phases (declared now as the full lifecycle, transitions land later):

    - PARTIALLY_DELIVERED / DELIVERED: set by 7.3 outbound deliveries as ``delivered_quantity``
    rises
      on the lines (DELIVERED when every line is fully delivered).
    - INVOICED: set by 7.4 billing once the order is fully invoiced.
    - CLOSED: fully delivered + invoiced (or short-closed); terminal."""

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CREDIT_BLOCKED = "CREDIT_BLOCKED"
    PARTIALLY_DELIVERED = "PARTIALLY_DELIVERED"
    DELIVERED = "DELIVERED"
    INVOICED = "INVOICED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class CreditCheckStatus(StrEnum):
    """The result of an order's confirm-time credit check (PLAN 7.2, D-044), stored on the order so
    the UI + audit can see why a confirmation blocked and that it was released.

    - PASSED: exposure (open AR + open confirmed orders + this order) was within the credit limit;
      the order confirmed normally.
    - BLOCKED: exposure exceeded the limit at confirmation — the order is CREDIT_BLOCKED and not
      confirmed (the HARD block per parity).
    - RELEASED: a user with ``sales.order.credit_release`` overrode the block; the order may then
      confirm (the release is recorded, the audit trail carries who/when via the audit row)."""

    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    RELEASED = "RELEASED"


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

# Quotes (PLAN 7.2): read the quote register vs create/edit/send/accept/reject/convert. A quote
# carries no committing gate (sending/accepting a quote moves no money or stock), so MANAGE covers
# every quote action — the RFQ-manage precedent (sourcing is not a committing action).
SALES_QUOTE_READ = "sales.quote.read"
SALES_QUOTE_MANAGE = "sales.quote.manage"
# Sales orders (PLAN 7.2): read vs create/edit/convert/cancel vs the privileged CONFIRM action vs
# the privileged CREDIT_RELEASE action.
#   - CONFIRM is its own key (the journal.post / po.approve precedent): confirming runs the ATP
#     evaluation + the credit-limit gate, a distinct authority from drafting an order.
#   - CREDIT_RELEASE is its own key (an approval-like override): releasing a CREDIT_BLOCKED order
#     past the limit is a manager's call, recorded in the audit trail. A clerk who can confirm
#     cannot silently override a credit block.
SALES_ORDER_READ = "sales.order.read"
SALES_ORDER_MANAGE = "sales.order.manage"
SALES_ORDER_CONFIRM = "sales.order.confirm"
SALES_ORDER_CREDIT_RELEASE = "sales.order.credit_release"

register_permissions(
    SALES_CUSTOMER_READ,
    SALES_CUSTOMER_MANAGE,
    SALES_PRICELIST_READ,
    SALES_PRICELIST_MANAGE,
    SALES_QUOTE_READ,
    SALES_QUOTE_MANAGE,
    SALES_ORDER_READ,
    SALES_ORDER_MANAGE,
    SALES_ORDER_CONFIRM,
    SALES_ORDER_CREDIT_RELEASE,
    descriptions={
        SALES_CUSTOMER_READ: "Read customers and customer groups",
        SALES_CUSTOMER_MANAGE: "Create and edit customers and customer groups",
        SALES_PRICELIST_READ: "Read price lists, their items and resolved price quotes",
        SALES_PRICELIST_MANAGE: "Create and edit price lists and their items",
        SALES_QUOTE_READ: "Read sales quotations",
        SALES_QUOTE_MANAGE: "Create, edit, send, accept, reject and convert sales quotations",
        SALES_ORDER_READ: "Read sales orders",
        SALES_ORDER_MANAGE: "Create, edit, convert and cancel sales orders",
        SALES_ORDER_CONFIRM: "Confirm sales orders (run the ATP and credit-limit checks)",
        SALES_ORDER_CREDIT_RELEASE: "Release a credit-blocked sales order past the credit limit",
    },
)


# --- Document types + number sequences (D-012/D-040) --------------------------
# The two O2C documents register in core_documents and claim a gapless number AT CREATION (D-040:
# claim-at-creation so a quote/order is referenceable the moment it exists — the
# procurement-document
# precedent, not finance's number-at-post branch). Sequences year-reset (QUO-2026-00001 /
# SO-2026-00001). Gaplessness still holds because creation is the committing transaction.
QUOTE_DOC_TYPE = "sales.quote"
QUOTE_SEQUENCE_NAME = "sales.quote"
QUOTE_NUMBER_PREFIX = "QUO"
QUOTE_NUMBER_PADDING = 5

SALES_ORDER_DOC_TYPE = "sales.order"
SALES_ORDER_SEQUENCE_NAME = "sales.order"
SALES_ORDER_NUMBER_PREFIX = "SO"
SALES_ORDER_NUMBER_PADDING = 5

# docflow link type joining the chain (D-012 vocabulary). The edge is predecessor → successor, so
# the
# link_type names the edge from the predecessor's point of view: an ACCEPTED quote is "converted_to"
# the order raised from it (the order carries source_quote_id; the quote→order edge is the chain the
# DocFlowViewer renders). The reverse ("quoted_by") is the successor's view, kept here for the docs.
QUOTE_CONVERTED_TO_ORDER_LINK = "converted_to"

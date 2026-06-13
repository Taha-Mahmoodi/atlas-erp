"""Sales status/type enums + pricing-engine numeric defaults (STRUCTURE §8.4).

Split out of the single ``constants.py`` at the 400-line cap when PLAN 7.4's billing + return
status enums landed (the finance constants/ precedent). The credit-limit + customer-group rationale
that lived in the old module docstring is recorded in ``constants/__init__`` and DECISIONS.md
(D-043). Every enum stores its UPPER_SNAKE value; the columns are plain ``sa.String``.
"""

from enum import StrEnum


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


class DeliveryStatus(StrEnum):
    """Lifecycle of an outbound delivery — the O2C fulfilment document (PLAN 7.3), the outbound twin
    of the procurement goods receipt (the GoodsReceiptStatus precedent, mirrored).

    - DRAFT: created, editable; a shipping clerk picks order lines + source bins + quantities. The
      DN number is claimed AT CREATION (D-012/D-040 claim-at-creation — a delivery is referenceable
      the moment it exists, the goods-receipt precedent). No stock has moved yet.
    - POSTED: the delivery shipped (DRAFT → POSTED). At POST it ISSUES stock (one inventory ISSUE
      move per line, via the event bus) — each move's costing posts Dr COGS / Cr Inventory — raises
      the order lines' delivered_quantity, and advances the order (PARTIALLY_DELIVERED / DELIVERED).
      All ONE transaction (D-011/D-020). TERMINAL: a POSTED delivery has moved stock + posted COGS,
      so it is corrected by a return / RMA (7.4), never cancelled or re-posted — the goods-receipt
      terminal-POSTED precedent.
    - CANCELLED: a DRAFT delivery abandoned before posting (DRAFT → CANCELLED); moves nothing."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class BillingStatus(StrEnum):
    """Lifecycle of a sales billing document — the O2C invoicing document (PLAN 7.4).

    A billing is the sales-side document that triggers the FINANCE AR customer invoice (it claims
    its
    OWN BIL- number; the AR invoice claims its own INV- number, D-046). Mirrors DeliveryStatus.

    - DRAFT: created, editable; a billing clerk picks order lines + the billed quantities (≤ the
      delivered-not-yet-invoiced quantity). The BIL number is claimed AT CREATION (D-040). No
      journal
      yet.
    - POSTED: the billing posted (DRAFT → POSTED). At POST it PUBLISHES the billing event so finance
      creates + posts the AR customer invoice (Dr AR control / Cr sales-revenue + Cr output tax),
      raises the order lines' invoiced_quantity, and advances the order (INVOICED / CLOSED). All ONE
      transaction (D-011). TERMINAL: a POSTED billing has recognized revenue + AR, so it is
      corrected
      by a return / credit note (7.4), never cancelled or re-posted — the delivery terminal-POSTED
      precedent.
    - CANCELLED: a DRAFT billing abandoned before posting (DRAFT → CANCELLED); posts nothing."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class ReturnStatus(StrEnum):
    """Lifecycle of a sales return / RMA — the reverse-O2C document (PLAN 7.4).

    A return brings goods back AND issues a credit note: at POST it publishes one event the
    inventory
    handler turns into a stock RECEIPT move (goods back in, Dr Inventory / Cr COGS — reversing the
    delivery's issue) and one the finance handler turns into an AR credit note (Dr revenue / Cr AR —
    reversing the billing's revenue). Mirrors DeliveryStatus / BillingStatus.

    - DRAFT: created, editable; a returns clerk picks order lines + the receiving bin + returned
      quantities (≤ the invoiced-not-yet-returned quantity). The RMA number is claimed AT CREATION
      (D-040). Nothing has moved or been credited yet.
    - POSTED: the return posted (DRAFT → POSTED). At POST it receives stock (reversing COGS) AND
    posts
      a credit note (reversing revenue + AR), raises the order lines' returned_quantity, and links
      docflow. All ONE transaction (D-011). TERMINAL: a POSTED return has moved stock + posted a
      credit note, so it is never cancelled or re-posted.
    - CANCELLED: a DRAFT return abandoned before posting (DRAFT → CANCELLED); moves/credits
    nothing."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
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

"""Domain events sales PUBLISHES (D-011/D-041). Declarative data only — no logic, no models — so
inventory's ``handlers.py`` may import these typed classes (the STRUCTURE §5 events.py allowance:
an event carries no behaviour, so a subscriber in another module imports it without any logic).

``DeliveryShipped`` is the SANCTIONED cross-module mechanism for the delivery → stock-issue effect
(D-045), the OUTBOUND TWIN of procurement's ``GoodsReceiptPosted`` (D-041, mirrored). Sales OWNS the
delivery document and its sales order; it MUST NOT call inventory's service directly (STRUCTURE §5
forbids importing another module's service). So the delivery POST publishes this event carrying
everything inventory needs to create the stock ISSUE moves — one ``DeliveryMove`` per delivery line
(item, the SOURCE bin to issue from, quantity, lot/serial) plus the move_date and the delivery's
core_documents id for docflow linkage. Inventory's ``handlers.py`` subscribes, creates each move via
its OWN service with ``move_type=ISSUE``, and links delivery document → 'moved_by' → move document.
The handler shares the session, so the moves + their COGS/inventory journals land in the SAME
transaction as the delivery post — all-or-nothing (D-011/D-020): a closed period or any handler
failure (e.g. insufficient stock) rolls the WHOLE delivery post back.

The KEY DIFFERENCE from ``GoodsReceiptPosted`` (D-045): the event carries NO GL accounts. A receipt
overrode its valuation offset to the GR/IR clearing account (a three-way-match leg), so that event
carried ``gr_ir_account_id``. An ISSUE move's DEFAULT valuation offset IS the item category's COGS
account (resolved inside the costing engine from the item's category), so a delivery needs no offset
override — COGS *is* the issue offset — and the event carries no account at all.

Sales updates its OWN tables (the order-line delivered_quantity, the order status, the delivery
status/posted_at) in that same transaction AFTER publishing; it does NOT need the move ids back —
the delivery↔move link is the durable docflow edge the handler writes, not a cross-module FK column
(D-041/D-045).
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.events import DomainEvent
from app.modules.sales.constants import (
    BILLING_POSTED_EVENT_KEY,
    DELIVERY_SHIPPED_EVENT_KEY,
    RETURN_CREDITED_EVENT_KEY,
    RETURN_RECEIVED_EVENT_KEY,
)


class DeliveryMove(BaseModel):
    """One delivery line's worth of stock to issue (D-045), the payload inventory's handler turns
    into a stock ISSUE move. Plain frozen data: the opaque item + SOURCE bin ids (D-029), the
    quantity issued in the item's base UoM, and optional lot/serial IDS (the lot/serial the stock
    leaves on for tracked items). The ids are RESOLVED by sales at create time from the line's
    lot/serial codes — an ISSUE references an EXISTING lot/serial by id (unlike a receipt, it
    creates none). No unit cost — the costing engine COMPUTES the COGS of the stock that left (FIFO
    layers / moving-average), unlike a receipt which enters at a supplied cost."""

    model_config = ConfigDict(frozen=True)

    item_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    lot_id: uuid.UUID | None = None
    serial_id: uuid.UUID | None = None


class DeliveryShipped(DomainEvent):
    """A delivery was posted / shipped (D-045). Inventory's ``handlers.py`` subscribes and creates
    one stock ISSUE move per ``move`` in the SAME transaction, each offsetting to the item-category
    COGS account by DEFAULT (Dr COGS / Cr Inventory — no offset override, unlike the GR/IR receipt),
    and links the delivery document to each move document ('moved_by').

    - ``delivery_id`` + ``delivery_number`` + ``document_id`` — the delivery document
      (``document_id`` is the core_documents id the handler links the move documents to).
    - ``warehouse_id`` — the inventory warehouse the shipment's stock issues from (each move's bin
      is in it); carried for context / future per-warehouse routing.
    - ``move_date`` — the delivery date the stock moves post on (ISO date string); a date in a
      CLOSED period makes each move's COGS journal trip the period trigger, rolling the delivery
      back.
    - ``moves`` — the per-line issues (see ``DeliveryMove``)."""

    key: ClassVar[str] = DELIVERY_SHIPPED_EVENT_KEY

    delivery_id: uuid.UUID
    delivery_number: str
    document_id: uuid.UUID
    warehouse_id: uuid.UUID
    move_date: str
    moves: tuple[DeliveryMove, ...]


# --- Billing → finance AR customer invoice (PLAN 7.4, D-046) ------------------
# The MIRROR of procurement's InvoiceMatched (match → AP bill), sign-flipped to billing → AR
# invoice.
# Sales OWNS the billing document; it MUST NOT call finance's service (STRUCTURE §5). So the billing
# POST publishes BillingInvoiced carrying everything finance needs to create + post the AR customer
# invoice. The event carries the resolved AR control + sales-revenue accounts (sales reads them from
# finance/queries BEFORE publishing, the procurement-match precedent), so finance's handler is a
# thin
# builder. Each ``BillingInvoiceLine`` becomes a revenue invoice line (net + tax code).


class BillingInvoiceLine(BaseModel):
    """One billing line's worth of AR invoice posting (D-046), the payload finance's handler turns
    into a customer-invoice line. Plain frozen data: the line's net (Cr revenue), the opaque finance
    tax code (drives output tax), and the opaque item (the invoice line's dimension, D-017). The
    revenue account is NOT per-line in v1 — it is the single sales-revenue default on the event
    header (mirroring how PPV is one per-tenant account)."""

    model_config = ConfigDict(frozen=True)

    item_id: uuid.UUID
    net_amount: Decimal
    tax_code_id: uuid.UUID | None = None


class BillingInvoiced(DomainEvent):
    """A sales billing was posted (D-046). Finance's ``handlers.py`` subscribes and creates + POSTS
    the AR customer invoice in the SAME transaction: Dr AR control / Cr sales-revenue per line + Cr
    output tax, with the opaque ``partner_id`` (= customer id, D-029) on the AR line. The MIRROR of
    the AP-bill handler. Finance handles its OWN invoice posting; sales only PUBLISHES (STRUCTURE
    §5).

    - ``billing_id`` + ``billing_number`` + ``document_id`` — the billing document (``document_id``
      is the core_documents id finance links the AR-invoice document to, 'invoiced_by_invoice').
    - ``partner_id`` + ``partner_name`` — the customer (the opaque finance partner_id, D-029) +
    name.
    - ``billing_date`` + ``due_date`` — the AR invoice's date + due date (sales computes due =
      billing_date + payment terms, read from the order snapshot).
    - ``currency_code`` — the AR invoice's transaction currency (the order/billing currency).
    - ``ar_account_id`` — the AR control account the invoice debits (resolved from finance/queries
    by
      sales before publishing).
    - ``revenue_account_id`` — the sales-revenue account each line credits (resolved likewise).
    - ``lines`` — the per-billing-line revenue postings (see ``BillingInvoiceLine``)."""

    key: ClassVar[str] = BILLING_POSTED_EVENT_KEY

    billing_id: uuid.UUID
    billing_number: str
    document_id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    billing_date: date
    due_date: date
    currency_code: str
    ar_account_id: uuid.UUID
    revenue_account_id: uuid.UUID
    lines: tuple[BillingInvoiceLine, ...]


# --- Return → inventory RECEIPT (reversing COGS) (PLAN 7.4, D-046) ------------
# The OUTBOUND-twin reversed: a delivery ISSUED stock (Dr COGS / Cr Inventory); a return RECEIVES it
# back (Dr Inventory / Cr COGS). Inventory's ``handlers.py`` subscribes to ReturnReceived and
# creates
# one RECEIPT move per line with ``valuation_offset_account_id`` = the item-category COGS account
# (the OVERRIDE, mirroring 6.3's GR/IR override) so the costing posts Dr Inventory / Cr COGS —
# reversing the original issue's COGS. The goods re-enter at the supplied ``unit_cost`` (the item's
# current book cost, resolved by sales before publishing). Sales never imports inventory/service.


class ReturnMove(BaseModel):
    """One return line's worth of stock to RECEIVE back (D-046), the payload inventory's handler
    turns into a stock RECEIPT move. Plain frozen data: the opaque item + DESTINATION bin ids
    (D-029),
    the returned quantity, the unit cost the goods re-enter at (the item's current book cost so the
    value reconciles), and optional lot/serial CODES (a RECEIPT may create the lot/serial master on
    the fly for tracked items, the goods-receipt precedent — unlike an issue which references one by
    id)."""

    model_config = ConfigDict(frozen=True)

    item_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    unit_cost: Decimal
    lot_code: str | None = None
    serial_code: str | None = None


class ReturnReceived(DomainEvent):
    """A sales return was posted — receive the goods back (D-046). Inventory's ``handlers.py``
    subscribes and creates one stock RECEIPT move per ``move`` in the SAME transaction, each
    offsetting to the event's ``cogs_account_id`` (the OVERRIDE) so the costing posts Dr Inventory /
    Cr COGS — REVERSING the delivery's issue. Links the return document to each move document
    ('received_by').

    - ``return_id`` + ``return_number`` + ``document_id`` — the return document (``document_id`` is
      the core_documents id the handler links the move documents to).
    - ``warehouse_id`` — the inventory warehouse the returned stock lands in (each move's bin is in
      it).
    - ``move_date`` — the return date the moves post on (ISO date string); a date in a CLOSED period
      makes each move's valuation journal trip the period trigger, rolling the whole return back.
    - ``cogs_account_id`` — the item-category COGS account the moves credit (the valuation-offset
      OVERRIDE; resolved by sales from inventory/queries before publishing).
    - ``moves`` — the per-line receipts (see ``ReturnMove``)."""

    key: ClassVar[str] = RETURN_RECEIVED_EVENT_KEY

    return_id: uuid.UUID
    return_number: str
    document_id: uuid.UUID
    warehouse_id: uuid.UUID
    move_date: str
    cogs_account_id: uuid.UUID
    moves: tuple[ReturnMove, ...]


# --- Return → finance AR credit note (reversing revenue) (PLAN 7.4, D-046) ----
# The second leg of a return post: finance's ``handlers.py`` subscribes to ReturnCredited and
# creates
# + posts the AR credit note (Dr revenue / Cr AR + reverse output tax) — reversing the billing's
# revenue + AR. Reuses the BillingInvoiceLine payload shape (same revenue/tax data, opposite journal
# direction). Two separate events (received + credited) so each module subscribes to exactly the leg
# it owns; both drain in the SAME atomic return-post transaction.


class ReturnCredited(DomainEvent):
    """A sales return was posted — credit the customer (D-046). Finance's ``handlers.py`` subscribes
    and creates + posts the AR credit note in the SAME transaction: Dr sales-revenue per line + Dr
    output tax / Cr AR control gross, partner-keyed by the opaque customer id (D-029). Links the
    return document to the credit-note document ('credited_by').

    The header mirrors ``BillingInvoiced`` (partner, dates, currency, AR control + revenue
    accounts);
    ``lines`` reuse ``BillingInvoiceLine`` (the credit note's magnitude math is the invoice's, only
    the journal direction flips — handled in finance's credit-note service)."""

    key: ClassVar[str] = RETURN_CREDITED_EVENT_KEY

    return_id: uuid.UUID
    return_number: str
    document_id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    credit_note_date: date
    currency_code: str
    ar_account_id: uuid.UUID
    revenue_account_id: uuid.UUID
    lines: tuple[BillingInvoiceLine, ...]


__all__ = [
    "BillingInvoiceLine",
    "BillingInvoiced",
    "DeliveryMove",
    "DeliveryShipped",
    "ReturnCredited",
    "ReturnMove",
    "ReturnReceived",
]

"""Domain events manufacturing PUBLISHES (D-011/D-048). Declarative data only — no logic, no
models — so inventory's ``handlers.py`` may import these typed classes (the STRUCTURE §5 events.py
allowance: an event carries no behaviour, so a subscriber in another module imports it without any
logic).

These are the SANCTIONED cross-module mechanism for the production-order → stock-move effects
(D-048), mirroring procurement's ``GoodsReceiptPosted`` (6.3, the WIP-offset twin of the GR/IR
override) and sales' ``DeliveryShipped``/``ReturnReceived`` (7.3/7.4). Manufacturing OWNS the
production-order document; it MUST NOT call inventory's service directly (STRUCTURE §5). So:

- ``ComponentsIssued`` (component ISSUE moves → Dr WIP / Cr Inventory): one ``ComponentIssueMove``
  per issued component line carries the item, the SOURCE bin, the quantity, optional lot/serial, and
  the ``wip_account_id`` — the valuation-offset OVERRIDE every move passes so the costing engine
  routes the ISSUE to WIP instead of COGS. The cost of the stock that left is COMPUTED by the
  costing engine (moving-average / FIFO), so no unit cost is on the event.
- ``OrderFinished`` (finished RECEIPT move → Dr Inventory / Cr WIP): one ``FinishedReceiptMove``
  (the parent item entering stock) carries the item, the DESTINATION bin, the finished quantity, the
  ``unit_cost`` = accumulated WIP / finished quantity (the goods enter at the WIP-accumulated cost),
  optional lot/serial CODES (a RECEIPT may create the master on the fly), and the ``wip_account_id``
  override so the costing posts Dr Inventory / Cr WIP.

Inventory's ``handlers.py`` subscribes, creates each move via its OWN service with the WIP offset,
and links the production-order document → 'issued_to'/'finished_to' → move document. The handler
shares the session, so the moves + their WIP journals land in the SAME transaction as the
issue/finish — all-or-nothing (D-011/D-020): a closed period or insufficient stock rolls the WHOLE
issue/finish back.

Manufacturing updates its OWN tables (the component ``issued_quantity``, the order
``accumulated_wip_cost``, ``finished_quantity``, status) in that same transaction; the order↔move
link is the durable docflow edge the handler writes, not a cross-module FK (D-048).
"""

import uuid
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.events import DomainEvent
from app.modules.manufacturing.constants import (
    COMPONENTS_ISSUED_EVENT_KEY,
    ORDER_FINISHED_EVENT_KEY,
    PLANNED_BUY_CONVERTED_EVENT_KEY,
)


class ComponentIssueMove(BaseModel):
    """One component line's worth of stock to ISSUE to WIP (D-048), the payload inventory's handler
    turns into a stock ISSUE move offset to WIP. Plain frozen data: the opaque component item +
    SOURCE bin ids (D-029), the quantity issued in the item's base UoM, and optional lot/serial IDS
    (the existing lot/serial the stock leaves on — an ISSUE references an existing instance by id,
    it creates none). No unit cost: the costing engine COMPUTES the cost of the stock that left."""

    model_config = ConfigDict(frozen=True)

    item_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    lot_id: uuid.UUID | None = None
    serial_id: uuid.UUID | None = None


class ComponentsIssued(DomainEvent):
    """Production-order components were issued to WIP (D-048). Inventory's ``handlers.py``
    subscribes and creates one stock ISSUE move per ``move`` in the SAME transaction, each
    offsetting to ``wip_account_id`` (Dr WIP / Cr Inventory — the valuation-offset OVERRIDE, the 6.3
    GR/IR-override pattern applied to an ISSUE), and links the order document to each move document
    ('issued_to').

    - ``production_order_id`` + ``order_number`` + ``document_id`` — the order document
      (``document_id`` is the core_documents id the handler links the move documents to).
    - ``warehouse_id`` — the warehouse the components issue FROM (each move's bin is in it).
    - ``move_date`` — the date the stock moves post on (ISO date string); a date in a CLOSED period
      makes each move's WIP journal trip the period trigger, rolling the whole issue back.
    - ``wip_account_id`` — the tenant's WIP clearing account (resolved by manufacturing from
      finance/queries before publishing); the valuation-offset OVERRIDE every move carries.
    - ``moves`` — the per-component issues (see ``ComponentIssueMove``)."""

    key: ClassVar[str] = COMPONENTS_ISSUED_EVENT_KEY

    production_order_id: uuid.UUID
    order_number: str
    document_id: uuid.UUID
    warehouse_id: uuid.UUID
    move_date: str
    wip_account_id: uuid.UUID
    moves: tuple[ComponentIssueMove, ...]


class FinishedReceiptMove(BaseModel):
    """The parent item's worth of stock to RECEIVE into finished goods (D-048), the payload
    inventory's handler turns into a stock RECEIPT move offset to WIP. Plain frozen data: the opaque
    parent item + DESTINATION bin ids (D-029), the finished quantity, the unit cost the goods enter
    at (= accumulated WIP / finished quantity, so the value entering inventory reconciles to WIP),
    and optional lot/serial CODES (a RECEIPT may create the lot/serial master on the fly for tracked
    items — unlike an issue which references one by id)."""

    model_config = ConfigDict(frozen=True)

    item_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    unit_cost: Decimal
    lot_code: str | None = None
    serial_code: str | None = None


class OrderFinished(DomainEvent):
    """A production order was finished to stock (D-048). Inventory's ``handlers.py`` subscribes and
    creates the finished-goods RECEIPT move in the SAME transaction, offsetting to
    ``wip_account_id`` (Dr Inventory / Cr WIP — the valuation-offset OVERRIDE), and links the order
    document to the move document ('finished_to'). The goods enter at the move's ``unit_cost``, so
    inventory value rises by the value credited out of WIP.

    On the FINAL finish, ``variance_amount`` carries any residual WIP the finished receipt did NOT
    absorb (over/under-absorption — when the finished value differs from accumulated WIP). FINANCE's
    handler posts the variance entry (Dr/Cr WIP / Cr/Dr the variance account) so WIP nets to ZERO,
    the way finance posts the costing journal off StockValued — manufacturing never imports
    finance/service (STRUCTURE §5). ``variance_amount`` is SIGNED: positive = WIP carries a leftover
    DEBIT (cost overran → Dr variance / Cr WIP); negative = leftover CREDIT (under → Dr WIP / Cr
    variance); zero = no entry (the common case where the receipt drained WIP exactly).

    - ``production_order_id`` + ``order_number`` + ``document_id`` — the order document.
    - ``warehouse_id`` — the warehouse the finished goods land in (the move's bin is in it).
    - ``move_date`` — the date the move + variance post on (ISO date string); a CLOSED period rolls
      it back.
    - ``wip_account_id`` — the tenant's WIP clearing account (the valuation-offset OVERRIDE + the
      account the variance entry clears).
    - ``variance_account_id`` — the production-variance account the residual flushes to (None when
      ``variance_amount`` is 0 — nothing to post).
    - ``variance_amount`` — the signed residual WIP to flush (0 = none).
    - ``currency_code`` — the variance entry's currency.
    - ``item_id`` — the parent item, the variance lines' dimension (D-017).
    - ``move`` — the finished-goods receipt (see ``FinishedReceiptMove``)."""

    key: ClassVar[str] = ORDER_FINISHED_EVENT_KEY

    production_order_id: uuid.UUID
    order_number: str
    document_id: uuid.UUID
    warehouse_id: uuid.UUID
    move_date: str
    wip_account_id: uuid.UUID
    variance_account_id: uuid.UUID | None
    variance_amount: Decimal
    currency_code: str
    item_id: uuid.UUID
    move: FinishedReceiptMove


class PlannedBuyConverted(DomainEvent):
    """A planned BUY order was converted to a procurement requisition (PLAN 8.3, D-049). The
    §5-clean cross-module mechanism for the planned-BUY → requisition conversion: manufacturing OWNS
    the planned order but MUST NOT call procurement's service (STRUCTURE §5), so the convert flow
    PUBLISHES this and procurement's ``handlers.create_requisition_for_planned_buy`` creates the
    DRAFT requisition in the SAME transaction and links the run document → 'planned_to' →
    requisition
    document (the docflow edge is the durable converted link, the billing→invoice precedent — the
    planned order itself is not a document, the MRP run is).

    - ``run_document_id`` — the MRP run's core_documents id, the docflow predecessor the requisition
      links to (so the plan → requisition flow is renderable).
    - ``item_id`` — the opaque inventory item to buy (D-029); ``uom_id`` its base UoM (resolved by
      manufacturing from inventory/queries before publishing); ``quantity`` the net requirement.
    - ``currency_code`` — the requisition line currency (the tenant functional currency, the reorder
      scan's default); ``description`` the proposal note (why this buy).
    """

    key: ClassVar[str] = PLANNED_BUY_CONVERTED_EVENT_KEY

    run_document_id: uuid.UUID
    item_id: uuid.UUID
    uom_id: uuid.UUID
    quantity: Decimal
    currency_code: str
    description: str


__all__ = [
    "ComponentIssueMove",
    "ComponentsIssued",
    "FinishedReceiptMove",
    "OrderFinished",
    "PlannedBuyConverted",
]

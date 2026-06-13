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
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.events import DomainEvent
from app.modules.sales.constants import DELIVERY_SHIPPED_EVENT_KEY


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


__all__ = ["DeliveryMove", "DeliveryShipped"]

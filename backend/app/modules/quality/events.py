"""Domain events quality PUBLISHES (D-011/D-050). Declarative data only — no logic, no models — so
inventory's ``handlers.py`` may import this typed class (the STRUCTURE §5 events.py allowance: an
event carries no behaviour, so a subscriber in another module imports it without any logic).

``InspectionDispositioned`` is the SANCTIONED cross-module mechanism for a REJECT usage decision's
stock effect (D-050). Quality OWNS the inspection lot; it MUST NOT call inventory's service directly
(STRUCTURE §5). So a reject PUBLISHES this event carrying everything inventory needs to move the
rejected stock, and inventory's ``handlers.py`` subscribes and creates the move via its OWN service:

- **SCRAP** → an ADJUSTMENT-out (``from_bin`` set, no ``to_bin``): the costing engine offsets an
  ADJUSTMENT-down to the price-difference / inventory-adjustment account (the write-off), so the
  move
  posts Dr inventory-adjustment / Cr Inventory at the stock's book value — total on-hand drops.
- **BLOCK** → a TRANSFER from ``from_bin`` to ``to_bin`` (the tenant's blocked/QI bin):
value-neutral
  (a within-warehouse transfer publishes no costing journal) — total on-hand unchanged, the stock
  leaves the usable bin. ``to_bin`` is carried only for BLOCK (None for SCRAP).

The handler shares the session, so the move + its (SCRAP) journal land in the SAME transaction as
the
decision — all-or-nothing (D-011/D-020): a closed period (the SCRAP write-off journal) or
insufficient
stock rolls the WHOLE decision back. The lot↔move link is the durable docflow edge the handler
writes
(inspection lot → 'dispositioned_by' → move), not a cross-module FK. An ACCEPT publishes NOTHING —
the accepted stock is already received and usable, so it needs no move.
"""

import uuid
from decimal import Decimal
from typing import ClassVar

from app.core.events import DomainEvent
from app.modules.quality.constants import INSPECTION_DISPOSITIONED_EVENT_KEY


class InspectionDispositioned(DomainEvent):
    """An inspection lot was REJECTED with a stock disposition (D-050). Inventory's ``handlers.py``
    subscribes and creates the disposition move in the SAME transaction, then links the inspection
    lot document → 'dispositioned_by' → move document.

    - ``lot_id`` + ``lot_number`` + ``document_id`` — the inspection-lot document (``document_id``
    is
      the core_documents id the handler links the move document to).
    - ``disposition`` — SCRAP (an ADJUSTMENT-out write-off) or BLOCK (a TRANSFER to the blocked
    bin).
    - ``item_id`` — the OPAQUE inventory item being dispositioned (D-029).
    - ``rejected_quantity`` — how much to move (the lot's rejected portion).
    - ``from_bin_id`` — the receiving bin the rejected stock currently sits in (the move's source).
    - ``to_bin_id`` — the blocked/QI bin for a BLOCK transfer; None for a SCRAP (one-sided
      adjustment).
    - ``inventory_lot_id`` / ``serial_id`` — the EXISTING tracked instance the stock leaves on (an
      outbound move references one by id, it creates none); None for untracked items.
    - ``move_date`` — the date the disposition move posts on (ISO date string); a date in a CLOSED
      period makes a SCRAP move's write-off journal trip the period trigger, rolling the whole
      decision back.
    """

    key: ClassVar[str] = INSPECTION_DISPOSITIONED_EVENT_KEY

    lot_id: uuid.UUID
    lot_number: str
    document_id: uuid.UUID
    disposition: str
    item_id: uuid.UUID
    rejected_quantity: Decimal
    from_bin_id: uuid.UUID
    to_bin_id: uuid.UUID | None
    inventory_lot_id: uuid.UUID | None
    serial_id: uuid.UUID | None
    move_date: str


__all__ = ["InspectionDispositioned"]

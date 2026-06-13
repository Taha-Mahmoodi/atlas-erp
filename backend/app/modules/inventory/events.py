"""Domain events inventory PUBLISHES (D-011/D-020). Declarative data only — no logic, no models —
so finance's ``handlers.py`` may import these typed classes (the STRUCTURE §5 events.py allowance,
explicitly covering finance importing "upward" from inventory because events carry no behaviour).

``StockValued`` is fired inside ``create_move`` AFTER the move + quant + valuation/layer updates,
carrying the computed value delta and the THREE GL account ids resolved from the item's category at
publish time (D-029 opaque ids). ``finance/handlers.py`` subscribes and posts the COGS/inventory
journal in the SAME transaction (D-011/D-020), so the move and its journal commit or roll back as
one
— a stock move can never exist without its journal entry, or vice versa.

ONE event for every value-changing move; the handler branches on ``move_type`` for the per-type
postings (RECEIPT / ISSUE / ADJUSTMENT up/down). A value-neutral within-warehouse TRANSFER does NOT
publish (no value change → no journal). All amounts are full-precision Decimals; the handler
quantizes
the posted COGS to the currency's decimals (D-015).
"""

import uuid
from decimal import Decimal
from typing import ClassVar

from app.core.events import DomainEvent
from app.modules.inventory.constants import STOCK_VALUED_EVENT_KEY


class StockValued(DomainEvent):
    """A stock move changed valuation (D-020). Payload:

    - ``move_id`` + ``move_date`` + ``move_number`` — the driving move (the journal posts with
      ``move_date``; a date in a CLOSED period makes the journal's period trigger fire inside the
      same transaction, rolling the whole move back — you cannot move stock into a closed period).
    - ``move_type`` — RECEIPT / ISSUE / ADJUSTMENT (the handler branches on it; TRANSFER within one
      warehouse never publishes). ``is_inbound`` disambiguates an ADJUSTMENT's direction (increase
      vs decrease) since both carry move_type ADJUSTMENT.
    - ``item_id`` + ``warehouse_id`` + ``quantity`` — the dimensions copied onto the COGS journal
      line (item dimension) and the value context.
    - ``total_cost`` — the value Δ the move moved (positive): RECEIPT entry value, ISSUE/decrease
      computed COGS, increase value. ``residual_to_price_difference`` is the moving-average
      zero-quantity flush amount (signed, usually 0) the handler posts to price-difference WITHIN
      the issue's entry so value and quantity never disagree (D-020).
    - ``document_id`` — the move's core_documents id (the docflow source ref the handler links the
      journal entry to, link_type 'posts').
    - ``inventory_account_id`` + ``offset_account_id`` — the two legs of the main posting: inventory
      is always one side; the OFFSET is chosen by the costing engine per move type (ISSUE -> COGS;
      RECEIPT / ADJUSTMENT -> price-difference; a reversal -> the OPPOSITE of the original move's
      offset, so reversing an issue credits COGS and reversing a receipt debits price-difference).
      ``is_inbound`` picks the Dr/Cr direction: inbound = Dr inventory / Cr offset.
    - ``price_difference_account_id`` — where the moving-average zero-quantity residual flush lands
      (always price-difference), separate from the main offset."""

    key: ClassVar[str] = STOCK_VALUED_EVENT_KEY

    move_id: uuid.UUID
    move_number: str
    move_type: str
    is_inbound: bool
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: Decimal
    total_cost: Decimal
    residual_to_price_difference: Decimal
    move_date: str
    document_id: uuid.UUID
    inventory_account_id: uuid.UUID
    offset_account_id: uuid.UUID
    price_difference_account_id: uuid.UUID


__all__ = ["StockValued"]

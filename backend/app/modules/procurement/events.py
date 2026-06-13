"""Domain events procurement PUBLISHES (D-011/D-041). Declarative data only — no logic, no models —
so inventory's ``handlers.py`` may import these typed classes (the STRUCTURE §5 events.py allowance:
an event carries no behaviour, so a subscriber in another module imports it without any logic).

``GoodsReceiptPosted`` is the SANCTIONED cross-module mechanism for the goods-receipt → stock-move
effect (D-041). Procurement OWNS the GR document and its PO; it MUST NOT call inventory's service
directly (STRUCTURE §5 forbids importing another module's service). So the GR POST publishes this
event carrying everything inventory needs to create the stock RECEIPT moves — one
``GoodsReceiptMove`` per GR line (item, target bin, quantity, the snapshot unit cost, lot/serial,
the GR/IR
clearing offset account, the inspection flag) plus the move_date and the GR's core_documents id for
docflow linkage. Inventory's ``handlers.py`` subscribes, creates each move via its OWN service with
``valuation_offset_account_id`` = the GR/IR account (so the costing event credits GR/IR), and links
GR document → 'moved_by' → move document. The handler shares the session, so the moves + their
inventory-debit/GR-IR journals land in the SAME transaction as the GR post — all-or-nothing
(D-011/D-020): a closed period or any handler failure rolls the WHOLE GR post back.

Procurement updates its OWN tables (the PO received_quantity, the GR status/posted_at) in that same
transaction AFTER publishing; it does NOT need the move ids back — the GR↔move link is the durable
docflow edge the handler writes, not a cross-module FK column (D-041).
"""

import uuid
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.events import DomainEvent
from app.modules.procurement.constants import GOODS_RECEIPT_POSTED_EVENT_KEY


class GoodsReceiptMove(BaseModel):
    """One GR line's worth of stock to receive (D-041), the payload inventory's handler turns into a
    stock RECEIPT move. Plain frozen data: the opaque item + target bin ids (D-029), the received
    quantity in the item's base UoM, the snapshot unit cost the stock enters at, optional lot/serial
    codes (created on the receipt for tracked items), and the v1 ``requires_inspection`` flag
    (passed through for traceability — Phase 9 adds the disposition; v1 does not block use)."""

    model_config = ConfigDict(frozen=True)

    item_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    unit_cost: Decimal
    lot_code: str | None = None
    serial_code: str | None = None
    requires_inspection: bool = False


class GoodsReceiptPosted(DomainEvent):
    """A goods receipt was posted (D-041). Inventory's ``handlers.py`` subscribes and creates one
    stock RECEIPT move per ``move`` in the SAME transaction, offsetting each to ``gr_ir_account_id``
    (Dr Inventory / Cr GR-IR), and links the GR document to each move document ('moved_by').

    - ``goods_receipt_id`` + ``gr_number`` + ``document_id`` — the GR document (``document_id`` is
      the core_documents id the handler links the move documents to).
    - ``warehouse_id`` — the inventory warehouse the receipt's stock lands in (each move's bin is in
      it); carried for context / future per-warehouse routing.
    - ``move_date`` — the receipt date the stock moves post on (ISO date string); a date in a CLOSED
      period makes each move's valuation journal trip the period trigger, rolling the whole GR back.
    - ``gr_ir_account_id`` — the tenant's GR/IR clearing account (resolved by procurement from
      finance/queries before publishing); the valuation-offset OVERRIDE every move carries.
    - ``moves`` — the per-line receipts (see ``GoodsReceiptMove``)."""

    key: ClassVar[str] = GOODS_RECEIPT_POSTED_EVENT_KEY

    goods_receipt_id: uuid.UUID
    gr_number: str
    document_id: uuid.UUID
    warehouse_id: uuid.UUID
    move_date: str
    gr_ir_account_id: uuid.UUID
    moves: tuple[GoodsReceiptMove, ...]


__all__ = ["GoodsReceiptMove", "GoodsReceiptPosted"]

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
from datetime import date
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.events import DomainEvent
from app.modules.procurement.constants import (
    GOODS_RECEIPT_POSTED_EVENT_KEY,
    INVOICE_MATCHED_EVENT_KEY,
)


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


class InvoiceMatchBillLine(BaseModel):
    """One match line's worth of bill posting (D-042), the payload finance's handler turns into a
    vendor-bill line. Plain frozen data carrying the GL-account routing the matched bill needs:

    - ``gr_ir_amount`` — the GR/IR clearing portion at PO COST (matched_quantity × po_unit_cost).
      This is what the goods receipt CREDITED GR/IR at receipt; the bill DEBITS exactly this so
      GR/IR clears to zero (the accounting subtlety of the 3-way match).
    - ``price_variance`` — (unit_price − po_unit_cost) × matched_quantity. The difference between
      the vendor's invoiced price and the PO price, routed to the purchase-price-variance account so
      GR/IR still clears at PO cost. Positive = the vendor charged MORE than PO (Dr PPV, an extra
      cost); negative = LESS (Cr PPV, a saving).
    - ``net_amount`` — the line's invoiced net (gr_ir_amount + price_variance = matched_quantity ×
      unit_price), the basis the input tax is computed on for this line.
    - ``item_id`` — the opaque inventory item, carried as the bill line's dimension (D-017)."""

    model_config = ConfigDict(frozen=True)

    item_id: uuid.UUID
    gr_ir_amount: Decimal
    price_variance: Decimal
    net_amount: Decimal


class InvoiceMatched(DomainEvent):
    """A 3-way invoice match was posted (D-042). Finance's ``handlers.py`` subscribes and creates +
    POSTS the AP vendor bill in the SAME transaction: Dr GR/IR (the received-goods portion at PO
    cost) + Dr/Cr purchase-price-variance (the in-tolerance price difference) + Dr input tax / Cr AP
    control at the vendor-invoiced total, with the opaque ``partner_id`` on the AP line (D-029). The
    bill clears the GR/IR account the goods receipt credited at receipt — closing the procure-to-pay
    loop. Finance handles its OWN bill posting; procurement only PUBLISHES the event (it must not
    import finance/service — STRUCTURE §5).

    - ``match_id`` + ``match_number`` + ``document_id`` — the match document (``document_id`` is the
      core_documents id finance links the bill document to, via the 'billed_by' edge).
    - ``partner_id`` + ``partner_name`` — the vendor (the opaque finance partner_id, D-029) + name.
    - ``vendor_invoice_ref`` — the vendor's own invoice number, stored as the bill's external ref.
    - ``invoice_date`` + ``due_date`` — the bill's date + due date (procurement computes the due
      date = invoice_date + the vendor's payment terms, read from procurement's own master).
    - ``currency_code`` — the bill's transaction currency (the PO/match currency).
    - ``gr_ir_account_id`` — the GR/IR clearing account the bill debits (resolved from finance by
      procurement before publishing).
    - ``ppv_account_id`` — the purchase-price-variance account any price difference routes to.
    - ``ap_account_id`` — the AP control account the bill credits at the invoiced total.
    - ``tax_code_id`` — the opaque finance tax code (nullable) driving the input tax.
    - ``lines`` — the per-match-line bill postings (see ``InvoiceMatchBillLine``)."""

    key: ClassVar[str] = INVOICE_MATCHED_EVENT_KEY

    match_id: uuid.UUID
    match_number: str
    document_id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    vendor_invoice_ref: str | None
    invoice_date: date
    due_date: date
    currency_code: str
    gr_ir_account_id: uuid.UUID
    ppv_account_id: uuid.UUID
    ap_account_id: uuid.UUID
    tax_code_id: uuid.UUID | None
    lines: tuple[InvoiceMatchBillLine, ...]


__all__ = [
    "GoodsReceiptMove",
    "GoodsReceiptPosted",
    "InvoiceMatchBillLine",
    "InvoiceMatched",
]

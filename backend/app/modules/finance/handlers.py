"""Finance domain-event handlers (D-011) — cross-module subscribers (PLAN 5.3 / 6.4).

``post_stock_valuation_journal`` (PLAN 5.3, D-020) subscribes to ``inventory.stock.valued`` and
posts the COGS/inventory valuation journal in the SAME transaction as the stock move (D-011
run_in_uow drains before commit; D-020 same-transaction COGS). Because the handler shares the
session and any handler exception rolls the WHOLE transaction back, a stock move can never commit
without its journal entry, or vice versa — the load-bearing atomicity invariant. The journal posts
with the move's ``move_date``: a date in a CLOSED period makes the journal's period trigger fire
inside this same transaction, which rolls the whole move back (you cannot move stock into a closed
accounting period — correct by construction).

``create_bill_for_match`` (PLAN 6.4, D-042) subscribes to ``procurement.invoice_match.matched`` and
creates + posts the AP vendor bill (Dr GR/IR at PO cost + Dr/Cr purchase-price-variance for the
in-tolerance price difference + Dr input tax / Cr AP control at the vendor-invoiced total) in the
SAME transaction as the match post. Procurement PUBLISHES the event; finance handles its OWN bill
posting (procurement must not import finance/service — STRUCTURE §5). The bill DEBITS GR/IR at
exactly the cost the goods receipt CREDITED it at receipt, so the GR/IR clearing account nets to
zero — the procure-to-pay loop closes. A closed invoice period trips the bill's journal period
trigger here and rolls the whole match post back.

``post_production_variance`` (PLAN 8.2, D-048) subscribes to the manufacturing OrderFinished event
and posts the residual WIP-variance entry on the final finish so the WIP clearing account nets to
ZERO (the MAV zero-quantity-flush analogue for WIP) — manufacturing PUBLISHES, finance posts its own
entry (STRUCTURE §5), the costing-handler precedent.

Postings per move type (the GL effect — D-020): the costing engine pre-selects the OFFSET and the
event carries it, so the stock-valuation handler is a thin Dr/Cr switch (RECEIPT/ADJUSTMENT-up: Dr
inventory / Cr offset; ISSUE: Dr offset / Cr inventory at the computed cost; the MAV zero-quantity
residual flushes to price-difference within the issue's entry; a reversal posts the exact reverse;
a value-neutral TRANSFER publishes no event). The detail lives in docs/modules/inventory.md.

Journals are built through the finance posting service (``create_draft_entry`` + ``post_entry``),
NEVER raw inserts, so every invariant fires. The move's document is linked to the entry's document
('posts' edge). Registration: ``app.main.register_event_handlers`` subscribes the handlers at the
factory (the D-011 seam), so the test harness re-registers after its per-test reset (D-025).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.money import quantize_for_currency
from app.modules.finance import queries as finance_queries
from app.modules.finance.constants import DocumentType
from app.modules.finance.payables_schemas import VendorBillCreate, VendorBillLineCreate
from app.modules.finance.receivables_schemas import (
    CustomerCreditNoteCreate,
    CustomerInvoiceCreate,
    CustomerInvoiceLineCreate,
)
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service.credit_notes import create_and_post_customer_credit_note
from app.modules.finance.service.customer_invoices import (
    create_customer_invoice,
    post_customer_invoice,
)
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.finance.service.vendor_bills import create_vendor_bill, post_vendor_bill
from app.modules.inventory.constants import DEFAULT_COSTING_CURRENCY, STOCK_MOVE_POSTS_LINK
from app.modules.inventory.events import StockValued
from app.modules.manufacturing.constants import PRODUCTION_ORDER_FINISHED_TO_MOVE_LINK
from app.modules.manufacturing.events import OrderFinished
from app.modules.procurement.constants import INVOICE_MATCH_BILLED_BY_BILL_LINK
from app.modules.procurement.events import InvoiceMatched
from app.modules.sales.constants import (
    BILLING_INVOICED_BY_INVOICE_LINK,
    RETURN_CREDITED_BY_CREDIT_NOTE_LINK,
)
from app.modules.sales.events import BillingInvoiced, ReturnCredited

# A signed posting (account_id, amount): positive => debit, negative => credit; the line builder
# drops zeros and splits into one-sided debit/credit lines.
_SignedPosting = tuple[uuid.UUID, Decimal]


async def post_stock_valuation_journal(session: AsyncSession, event: StockValued) -> None:
    """Post the COGS/inventory journal for a valued stock move (D-020), in the move's transaction.

    Registered via ``app.main.register_event_handlers`` (the deterministic D-011 registration seam),
    not an import-time ``@on`` decorator, so the test harness can re-register it after its per-test
    ``clear_subscriptions`` reset (D-025) without relying on a module re-import.

    Builds the signed postings for the move type, turns them into balanced one-sided journal lines,
    posts a COGS-typed entry dated the move date (the period trigger fires here — a closed period
    rolls the whole move back), and links move.document -> entry.document ('posts')."""
    currency_code = (
        await finance_queries.functional_currency_or_none(session, event.tenant_id)
        or DEFAULT_COSTING_CURRENCY
    )
    # total_cost is already quantized for ISSUE (per-layer / MAV quantize) but a RECEIPT's
    # qty × unit_cost can carry sub-currency digits — quantize the posted amount at the boundary
    # (D-015); the residual flush is already an exact MoneyType difference.
    amount = quantize_for_currency(Decimal(event.total_cost), currency_code)
    residual = Decimal(event.residual_to_price_difference)

    postings = _postings_for(event, amount, residual)
    lines = _lines_from_postings(postings, event.item_id)
    if len(lines) < 2:
        # A zero-value move (e.g. a free receipt) produces no balanced entry — nothing to post. The
        # quant/valuation still updated; there is simply no GL effect. (Not reachable on priced
        # moves.)
        return

    entry = await create_draft_entry(
        session,
        event.tenant_id,
        JournalEntryCreate(
            posting_date=date.fromisoformat(event.move_date),
            currency_code=currency_code,
            description=f"Stock {event.move_type.lower()} {event.move_number}",
            document_type=DocumentType.COGS,
            lines=lines,
        ),
    )
    await post_entry(session, event.tenant_id, entry.id)
    # Link the move's document to the journal entry's document so the docflow chain shows the COGS
    # posting (D-012 'posts' edge — the finance posting convention).
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=entry.document_id,
        link_type=STOCK_MOVE_POSTS_LINK,
    )


def _postings_for(
    event: StockValued, amount: Decimal, residual: Decimal
) -> list[_SignedPosting]:
    """The signed GL postings (positive = debit, negative = credit) for the move (D-020).

    The costing engine already chose ``offset_account_id`` per move type (ISSUE -> COGS; RECEIPT /
    ADJUSTMENT -> price-difference; a reversal -> the opposite of the original's offset), so the
    handler stays a thin Dr/Cr direction switch:
    - inbound: Dr inventory / Cr offset (stock entered or an issue was reversed).
    - outbound: Dr offset / Cr inventory (stock left or a receipt was reversed). The inventory leg
      additionally carries the moving-average zero-quantity residual, flushed to price-difference,
      so value and quantity reconcile to zero (D-020). ``residual`` is 0 unless the issue drove
      on-hand to exactly zero."""
    if event.is_inbound:
        return [
            (event.inventory_account_id, amount),
            (event.offset_account_id, -amount),
        ]
    return [
        (event.offset_account_id, amount),
        (event.inventory_account_id, -(amount + residual)),
        (event.price_difference_account_id, residual),
    ]


def _lines_from_postings(
    postings: list[_SignedPosting], item_id: uuid.UUID
) -> list[JournalLineCreate]:
    """Collapse signed postings per account, drop zeros, and emit one-sided journal lines (D-017):
    a positive net is a debit, a negative net a credit. The item dimension rides every line so the
    COGS entry is attributable to the item (D-017 dimensions)."""
    net: dict[uuid.UUID, Decimal] = {}
    for account_id, signed in postings:
        net[account_id] = net.get(account_id, Decimal(0)) + signed
    lines: list[JournalLineCreate] = []
    for account_id, value in net.items():
        if value == 0:
            continue
        if value > 0:
            lines.append(
                JournalLineCreate(
                    account_id=account_id,
                    transaction_debit_amount=value,
                    item_id=item_id,
                )
            )
        else:
            lines.append(
                JournalLineCreate(
                    account_id=account_id,
                    transaction_credit_amount=-value,
                    item_id=item_id,
                )
            )
    return lines


async def create_bill_for_match(session: AsyncSession, event: InvoiceMatched) -> None:
    """Create + post the AP vendor bill for a posted 3-way match (PLAN 6.4, D-042), in the match's
    transaction.

    Builds a draft vendor bill whose lines DEBIT GR/IR at PO cost and route the in-tolerance price
    difference to the purchase-price-variance account, with the header tax code driving input tax,
    then posts it through the finance AP service (``create_vendor_bill`` + ``post_vendor_bill``) so
    every AP/journal invariant fires exactly as for a hand-entered bill. The AP control is credited
    at the vendor-invoiced gross, partner-keyed by the opaque vendor id (D-029); the bill's due date
    is invoice_date + the vendor's terms (procurement computed it). The GR/IR debit equals the GR/IR
    credit at receipt, so GR/IR nets to zero — the procure-to-pay loop closes. Linking the match
    document to the bill document ('billed_by') completes the PO → GR → match → bill docflow chain.

    Registered via ``app.main.register_event_handlers`` (the deterministic D-011 seam), so the test
    harness re-registers it after its per-test ``clear_subscriptions`` reset (D-025)."""
    lines: list[VendorBillLineCreate] = []
    for line in event.lines:
        # The GR/IR clearing portion at PO cost (taxable): Dr GR/IR, clearing the receipt credit.
        lines.append(
            VendorBillLineCreate(
                account_id=event.gr_ir_account_id,
                description="GR/IR clearing",
                net_amount=line.gr_ir_amount,
                tax_code_id=event.tax_code_id,
            )
        )
        # The price variance (taxable, same code so input tax matches the full invoice): Dr/Cr PPV.
        # Dropped when zero so a clean match posts no PPV line.
        if line.price_variance != 0:
            lines.append(
                VendorBillLineCreate(
                    account_id=event.ppv_account_id,
                    description="Purchase price variance",
                    net_amount=line.price_variance,
                    tax_code_id=event.tax_code_id,
                )
            )

    bill = await create_vendor_bill(
        session,
        event.tenant_id,
        VendorBillCreate(
            partner_id=event.partner_id,
            partner_name=event.partner_name,
            bill_date=event.invoice_date,
            due_date=event.due_date,
            currency_code=event.currency_code,
            ap_account_id=event.ap_account_id,
            bill_external_ref=event.vendor_invoice_ref,
            description=f"3-way match {event.match_number}",
            lines=lines,
        ),
    )
    await post_vendor_bill(session, event.tenant_id, bill.id, posting_date=event.invoice_date)
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=bill.document_id,
        link_type=INVOICE_MATCH_BILLED_BY_BILL_LINK,
    )


async def create_invoice_for_billing(session: AsyncSession, event: BillingInvoiced) -> None:
    """Create + post the AR customer invoice for a posted sales billing (PLAN 7.4, D-046), in the
    billing's transaction — the MIRROR of ``create_bill_for_match`` (match → AP bill), sign-flipped.

    Builds a draft customer invoice whose lines CREDIT the sales-revenue account at each net (the
    header tax code drives output tax), then posts it through the finance AR service
    (``create_customer_invoice`` + ``post_customer_invoice``) so every AR/journal invariant fires
    exactly as for a hand-entered invoice: Dr AR control gross / Cr revenue net / Cr output tax,
    partner-keyed by the opaque customer id (D-029), due = billing_date + the terms sales computed.
    Linking the billing document to the invoice document ('invoiced_by_invoice') completes the
    order → delivery → billing → invoice docflow chain. A closed billing period trips the invoice's
    journal trigger here and rolls the whole billing post back.

    Registered via ``app.main.register_event_handlers`` (the deterministic D-011 seam), so the test
    harness re-registers it after its per-test ``clear_subscriptions`` reset (D-025)."""
    lines = [
        CustomerInvoiceLineCreate(
            account_id=event.revenue_account_id,
            description="Sales revenue",
            net_amount=line.net_amount,
            tax_code_id=line.tax_code_id,
        )
        for line in event.lines
    ]
    invoice = await create_customer_invoice(
        session,
        event.tenant_id,
        CustomerInvoiceCreate(
            partner_id=event.partner_id,
            partner_name=event.partner_name,
            invoice_date=event.billing_date,
            due_date=event.due_date,
            currency_code=event.currency_code,
            ar_account_id=event.ar_account_id,
            external_ref=event.billing_number,
            description=f"Sales billing {event.billing_number}",
            lines=lines,
        ),
    )
    await post_customer_invoice(
        session, event.tenant_id, invoice.id, posting_date=event.billing_date
    )
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=invoice.document_id,
        link_type=BILLING_INVOICED_BY_INVOICE_LINK,
    )


async def create_credit_note_for_return(session: AsyncSession, event: ReturnCredited) -> None:
    """Create + post the AR credit note for a posted sales return (PLAN 7.4, D-046), in the return's
    transaction. Builds a credit note (the sign-flipped customer invoice) whose lines DEBIT
    sales-revenue at each net (reversing revenue) and whose AR control is CREDITED at the gross
    (reversing AR), the header tax code reversing output tax — posted via
    ``create_and_post_customer_credit_note`` so every journal invariant fires. Links the return
    document → 'credited_by' → credit-note document. A closed return period trips the journal
    trigger here and rolls the whole return post back. Registered via the D-011 seam."""
    lines = [
        CustomerInvoiceLineCreate(
            account_id=event.revenue_account_id,
            description="Sales revenue reversal",
            net_amount=line.net_amount,
            tax_code_id=line.tax_code_id,
        )
        for line in event.lines
    ]
    note = await create_and_post_customer_credit_note(
        session,
        event.tenant_id,
        CustomerCreditNoteCreate(
            partner_id=event.partner_id,
            partner_name=event.partner_name,
            credit_note_date=event.credit_note_date,
            currency_code=event.currency_code,
            ar_account_id=event.ar_account_id,
            external_ref=event.return_number,
            description=f"Sales return {event.return_number}",
            lines=lines,
        ),
        posting_date=event.credit_note_date,
    )
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=note.document_id,
        link_type=RETURN_CREDITED_BY_CREDIT_NOTE_LINK,
    )


async def post_production_variance(session: AsyncSession, event: OrderFinished) -> None:
    """Post the WIP-variance entry for a finished production order (PLAN 8.2, D-048), in the
    finish's transaction — the MAV zero-quantity-flush analogue for WIP. The finished RECEIPT move
    credited WIP by the value entering stock; this posts the RESIDUAL WIP the receipt did NOT absorb
    so WIP nets to EXACTLY zero. ``variance_amount`` is SIGNED: positive = leftover DEBIT (cost
    overran → Dr variance / Cr WIP); negative = leftover CREDIT (under → Dr WIP / Cr variance); 0
    posts nothing. Manufacturing PUBLISHES; finance posts its OWN entry (STRUCTURE §5), as off
    StockValued. A closed period trips the trigger here and rolls the whole finish back. Registered
    via ``app.main.register_event_handlers`` (the D-011 seam)."""
    amount = Decimal(event.variance_amount)
    if amount == 0 or event.variance_account_id is None:
        return
    currency_code = event.currency_code or DEFAULT_COSTING_CURRENCY
    magnitude = quantize_for_currency(abs(amount), currency_code)
    if magnitude == 0:
        return
    if amount > 0:
        # Leftover DEBIT → Dr variance / Cr WIP (cost overran); leftover CREDIT → the reverse.
        postings: list[_SignedPosting] = [
            (event.variance_account_id, magnitude),
            (event.wip_account_id, -magnitude),
        ]
    else:
        postings = [
            (event.wip_account_id, magnitude),
            (event.variance_account_id, -magnitude),
        ]
    lines = _lines_from_postings(postings, event.item_id)
    entry = await create_draft_entry(
        session,
        event.tenant_id,
        JournalEntryCreate(
            posting_date=date.fromisoformat(event.move_date),
            currency_code=currency_code,
            description=f"WIP variance {event.order_number}",
            document_type=DocumentType.COGS,
            lines=lines,
        ),
    )
    await post_entry(session, event.tenant_id, entry.id)
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=entry.document_id,
        link_type=PRODUCTION_ORDER_FINISHED_TO_MOVE_LINK,
    )


__all__ = [
    "create_bill_for_match",
    "create_credit_note_for_return",
    "create_invoice_for_billing",
    "post_production_variance",
    "post_stock_valuation_journal",
]

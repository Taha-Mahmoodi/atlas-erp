"""Inventory stock-valuation → COGS/inventory journal handler (PLAN 5.3, D-020).

``post_stock_valuation_journal`` subscribes to ``inventory.stock.valued`` and posts the
COGS/inventory valuation journal in the SAME transaction as the stock move (D-011 run_in_uow drains
before commit; D-020 same-transaction COGS). Because the handler shares the session and any handler
exception rolls the WHOLE transaction back, a stock move can never commit without its journal entry,
or vice versa — the load-bearing atomicity invariant. The journal posts with the move's
``move_date``: a date in a CLOSED period makes the journal's period trigger fire inside this same
transaction, which rolls the whole move back (you cannot move stock into a closed accounting
period — correct by construction).

Postings per move type (the GL effect — D-020): the costing engine pre-selects the OFFSET and the
event carries it, so the handler stays a thin Dr/Cr switch (RECEIPT/ADJUSTMENT-up: Dr inventory / Cr
offset; ISSUE: Dr offset / Cr inventory at the computed cost; the MAV zero-quantity residual flushes
to price-difference within the issue's entry; a reversal posts the exact reverse; a value-neutral
TRANSFER publishes no event). The detail lives in docs/modules/inventory.md.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.money import quantize_for_currency
from app.modules.finance import queries as finance_queries
from app.modules.finance.constants import DocumentType
from app.modules.finance.handlers._shared import _lines_from_postings, _SignedPosting
from app.modules.finance.schemas import JournalEntryCreate
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.inventory.constants import DEFAULT_COSTING_CURRENCY, STOCK_MOVE_POSTS_LINK
from app.modules.inventory.events import StockValued


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

"""Finance domain-event handlers (D-011) — the FIRST real cross-module handler (PLAN 5.3, D-020).

Subscribes to ``inventory.stock.valued`` and posts the COGS/inventory valuation journal in the SAME
transaction as the stock move (D-011 run_in_uow drains before commit; D-020 same-transaction COGS).
Because the handler shares the session and any handler exception rolls the WHOLE transaction back, a
stock move can never commit without its journal entry, or vice versa — the load-bearing atomicity
invariant. The journal posts with the move's ``move_date``: a date in a CLOSED period makes the
journal's period trigger fire inside this same transaction, which rolls the whole move back (you
cannot move stock into a closed accounting period — correct by construction).

Postings per move type (the GL effect of each — D-020). The costing engine pre-selects the OFFSET
account per type and the event carries it, so the handler is a thin Dr/Cr direction switch:
- RECEIPT / ADJUSTMENT-up: Dr inventory / Cr price-difference. A STANDALONE receipt (opening
  balance, manual stock-in) has no procurement GR clearing yet, so its offset is price-difference /
  inventory-adjustment account; procurement's goods-receipt path (6.x) will OVERRIDE this with its
  own GR/IR offset. ADJUSTMENT-up is the same shape (a stock increase with no document behind it).
- ISSUE: Dr COGS / Cr inventory at the computed cost (goods left for sale/production).
- ADJUSTMENT-down: Dr price-difference / Cr inventory (an inventory write-off, no document).
- The moving-average zero-quantity FLUSH posts its residual to price-difference WITHIN the issue's
  entry so value and quantity never disagree (D-020).
- A reversal posts the EXACT reverse of the original move's entry (reversing an issue credits COGS;
  reversing a receipt debits price-difference) — the costing engine sets the reversal's offset.
- TRANSFER within one inventory account: value-neutral → the inventory engine publishes NO event, so
  the handler never runs for it (documented; no journal).

The journal is built through the finance posting service (``create_draft_entry`` + ``post_entry``),
NEVER raw inserts, so every journal invariant (balance, one-side CHECK, period, immutability,
numbering, audit, docflow) fires exactly as for any posting. The move's document is linked to the
journal entry's document ('posts' edge) so the docflow viewer shows move -> COGS entry.

Registration: ``app.main.register_event_handlers`` subscribes ``post_stock_valuation_journal`` to
the
event key at the app factory (the deterministic D-011 registration seam), so the test harness can
re-register after its per-test ``clear_subscriptions`` reset (D-025) without a module re-import.
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
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.inventory.constants import DEFAULT_COSTING_CURRENCY, STOCK_MOVE_POSTS_LINK
from app.modules.inventory.events import StockValued

# A signed posting: (account_id, amount). Positive amount => debit, negative => credit. The line
# builder drops zeros and splits into the journal's one-sided debit/credit lines.
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


__all__ = ["post_stock_valuation_journal"]

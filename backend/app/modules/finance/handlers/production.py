"""Manufacturing production-finish → WIP-variance journal handler (PLAN 8.2, D-048).

``post_production_variance`` subscribes to the manufacturing ``OrderFinished`` event and posts the
residual WIP-variance entry on the final finish so the WIP clearing account nets to ZERO (the MAV
zero-quantity-flush analogue for WIP) — manufacturing PUBLISHES, finance posts its own entry
(STRUCTURE §5), the costing-handler precedent.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.money import quantize_for_currency
from app.modules.finance.constants import DocumentType
from app.modules.finance.handlers._shared import _lines_from_postings, _SignedPosting
from app.modules.finance.schemas import JournalEntryCreate
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.inventory.constants import DEFAULT_COSTING_CURRENCY
from app.modules.manufacturing.constants import PRODUCTION_ORDER_FINISHED_TO_MOVE_LINK
from app.modules.manufacturing.events import OrderFinished


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

"""Shared building blocks for the finance event handlers (D-011), split out so each handler concern
file stays under the 400-line cap (STRUCTURE §8.4; the models/ + service/ package precedent).

``_lines_from_postings`` collapses signed (account, amount) postings into balanced one-sided journal
lines (a positive net = a debit, a negative net = a credit), carrying the item dimension. Used by
the inventory-COGS and production-variance handlers, which both build their entries from a signed
posting list.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.modules.finance.schemas import JournalLineCreate

# A signed posting (account_id, amount): positive => debit, negative => credit; the line builder
# drops zeros and splits into one-sided debit/credit lines.
_SignedPosting = tuple[uuid.UUID, Decimal]


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

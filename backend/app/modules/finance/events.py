"""Domain events finance PUBLISHES (D-011). Declarative data only — no logic, no models — so
another module's ``handlers.py`` may import these typed classes (the STRUCTURE §5 events.py
allowance). Inventory and other modules subscribe in a later phase; the payload carries the
entry id plus amount/account summaries so a subscriber needs no finance read to react.

For v1 functional amounts equal transaction amounts (single functional currency); the event
carries the functional total since that is what downstream ledger consumers reconcile against.
"""

import uuid
from decimal import Decimal
from typing import ClassVar

from app.core.events import DomainEvent


class JournalEntryPosted(DomainEvent):
    """A draft journal entry was posted (D-017). Fired inside the posting transaction after the
    DRAFT->POSTED flush; a handler runs in the SAME transaction (D-011), so any cross-module
    effect it triggers commits or rolls back with the posting."""

    key: ClassVar[str] = "finance.journal.posted"

    entry_id: uuid.UUID
    entry_number: str
    document_type: str
    posting_date: str
    currency_code: str
    total_functional_amount: Decimal
    account_ids: tuple[uuid.UUID, ...]


class JournalEntryReversed(DomainEvent):
    """A posted entry was reversed by a new reversing entry (D-017). Carries both ids so a
    subscriber can mirror the correction (e.g. reverse a derived posting)."""

    key: ClassVar[str] = "finance.journal.reversed"

    entry_id: uuid.UUID
    reversal_entry_id: uuid.UUID
    reversal_entry_number: str
    document_type: str
    reversal_date: str

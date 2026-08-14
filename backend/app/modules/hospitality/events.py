"""Domain events hospitality PUBLISHES (D-011/STRUCTURE §5). Declarative data only — no logic, no
models — so a subscriber in another module may import these typed classes.

TWO events, at the two moments that carry effects, and the SPLIT between them is the phase's whole
argument (Q4):

- ``RestaurantOrderFired`` at send-to-kitchen. This is where ingredients are consumed, because the
  kitchen has started cooking: a dish comped after service has already eaten them. Task 5
  subscribes and submits the background depletion job in THIS uow, so a D-013 replay of the fire
  returns the same job id.
- ``RestaurantOrderSettled`` at tender. Carries NO stock effect at all. Phase 19 subscribes nothing
  to it — Phase 20.6's room-charge bridge is the consumer, and it is declared now because the
  alternative is that settle grows a direct cross-module call later instead of an event (the exact
  coupling STRUCTURE §5 exists to prevent).

Neither event carries the ticket's LINES. A subscriber that needs them reads them by
``ticket_id`` — Task 5's depletion runs off-request against a job payload of primitives anyway, so
shipping a line array through the bus would be a copy nothing reads.
"""

import uuid
from decimal import Decimal
from typing import ClassVar

from app.core.events import DomainEvent
from app.modules.hospitality.constants import (
    ORDER_TICKET_FIRED_EVENT_KEY,
    ORDER_TICKET_SETTLED_EVENT_KEY,
)


class RestaurantOrderFired(DomainEvent):
    """An order ticket was sent to the kitchen (Q4).

    - ``ticket_id`` / ``ticket_number`` — the ticket, by id and by its gapless TKT- number.
    - ``document_id`` — the ticket's ``core_documents`` id, so a subscriber can hang a docflow edge
      off it (Task 5 links the ticket to the depletion job's stock moves) without a cross-module FK.
    - ``fired_at`` — when the kitchen was told. The depletion job posts its stock moves on this
      date, so a ticket fired before midnight depletes on that service's date even if the job
      drains after it.
    """

    key: ClassVar[str] = ORDER_TICKET_FIRED_EVENT_KEY

    ticket_id: uuid.UUID
    ticket_number: str
    document_id: uuid.UUID
    fired_at: str


class RestaurantOrderSettled(DomainEvent):
    """An order ticket was tendered — the money moment (Phase 20.6's room-charge bridge).

    ``total_amount`` is the ticket's maintained total, carried on the event rather than left for a
    subscriber to re-read: it is the authoritative number (Q6) and a settled ticket's total can
    never change again, so a snapshot cannot go stale.
    """

    key: ClassVar[str] = ORDER_TICKET_SETTLED_EVENT_KEY

    ticket_id: uuid.UUID
    ticket_number: str
    document_id: uuid.UUID
    total_amount: Decimal
    settled_at: str


__all__ = ["RestaurantOrderFired", "RestaurantOrderSettled"]

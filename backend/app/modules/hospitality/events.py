"""Domain events hospitality PUBLISHES (D-011/STRUCTURE §5). Declarative data only — no logic, no
models — so a subscriber in another module may import these typed classes.

THREE events. The first two are the two moments of the SALE that carry effects, and the split
between them is the phase's whole argument (Q4); the third is published by the background depletion
job, off the sale entirely.

- ``RestaurantOrderFired`` at send-to-kitchen. This is where ingredients are consumed, because the
  kitchen has started cooking: a dish comped after service has already eaten them. Task 5
  subscribes and submits the background depletion job in THIS uow, so a D-013 replay of the fire
  returns the same job id.
- ``RestaurantOrderSettled`` at tender. Carries NO stock effect at all. Phase 19 subscribes nothing
  to it — Phase 20.6's room-charge bridge is the consumer, and it is declared now because the
  alternative is that settle grows a direct cross-module call later instead of an event (the exact
  coupling STRUCTURE §5 exists to prevent).

- ``TicketIngredientsConsumed`` from the depletion job. Inventory's handler turns it into the ISSUE
  moves, because hospitality may not import inventory's service (STRUCTURE §5).

Neither SALE event carries the ticket's LINES. A subscriber that needs them reads them by
``ticket_id`` — the depletion runs off-request against a job payload of primitives anyway, so
shipping a line array through the bus would be a copy nothing reads.
"""

import uuid
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.events import DomainEvent
from app.modules.hospitality.constants import (
    ORDER_TICKET_FIRED_EVENT_KEY,
    ORDER_TICKET_SETTLED_EVENT_KEY,
    TICKET_INGREDIENTS_CONSUMED_EVENT_KEY,
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


class ConsumedIngredient(BaseModel):
    """One aggregated ingredient to issue from the storeroom — the payload inventory's handler turns
    into a stock ISSUE move. The opaque component item + SOURCE bin ids (D-029) and the quantity in
    the item's base UoM. No unit cost: an ISSUE's cost is COMPUTED by the costing engine, and no
    lot/serial: a kitchen ingredient is fungible in v1 (a tracked ingredient would need the
    depletion to pick a lot, which is a FEFO policy Phase 19 does not ship)."""

    model_config = ConfigDict(frozen=True)

    item_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal


class TicketIngredientsConsumed(DomainEvent):
    """A fired ticket's AGGREGATED ingredients left the storeroom (Q4) — published by the background
    depletion job, not by the sale.

    This is the sanctioned cross-module mechanism (STRUCTURE §5): hospitality must not import
    inventory's service, so it publishes this and inventory's ``issue_ticket_ingredients`` creates
    the moves — the same shape as sales' ``DeliveryShipped`` and manufacturing's
    ``ComponentsIssued``.
    The handler runs inside the JOB's ``run_in_uow``, so D-011's actual invariant (a goods issue
    without its COGS journal can never commit) still holds; what moved is the transaction boundary,
    not the guarantee.

    ``ingredients`` is already aggregated and de-duplicated across the ticket's lines, and bounded
    by ``DEPLETE_MAX_COMPONENTS_PER_JOB`` so the fan-out cannot reach ``MAX_DISPATCHES_PER_UOW``.
    ``move_date`` is the ticket's FIRE date, so a ticket fired before midnight depletes on that
    service's date however late the job drains.
    """

    key: ClassVar[str] = TICKET_INGREDIENTS_CONSUMED_EVENT_KEY

    ticket_id: uuid.UUID
    ticket_number: str
    document_id: uuid.UUID
    move_date: str
    ingredients: tuple[ConsumedIngredient, ...]


__all__ = [
    "ConsumedIngredient",
    "RestaurantOrderFired",
    "RestaurantOrderSettled",
    "TicketIngredientsConsumed",
]

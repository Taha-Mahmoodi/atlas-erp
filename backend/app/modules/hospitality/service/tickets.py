"""Order-ticket lifecycle (PLAN 19 Task 4, spec Q4): open a check, add lines, fire it to the
kitchen, settle it.

A ticket is an ordinary D-012 document — it registers in ``core_documents`` and claims its gapless
``TKT-`` number at creation, exactly like a sales order. What is specific to a restaurant is that
every decision bites at FIRE rather than at tender: the 86 refusal, the countdown burn and the
``RestaurantOrderFired`` publish all live in ``fire_ticket``, which documents Q4's reasons, as do
``constants.OrderTicketStatus`` (why the lifecycle is strictly sequential) and ``events`` (why the
split between fired and settled is the phase's whole argument).

Nothing here moves stock or posts a journal. Ingredient depletion is a separate, BACKGROUND concern
(Q4, Task 5) that subscribes to the fired event; keeping it out of this file is the whole design.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.models import utcnow
from app.core.money import MONEY_SCALE, quantize_money
from app.core.numbering import claim_number, ensure_sequence
from app.modules.hospitality.constants import (
    ORDER_TICKET_DOC_TYPE,
    ORDER_TICKET_NUMBER_PADDING,
    ORDER_TICKET_NUMBER_PREFIX,
    ORDER_TICKET_SEQUENCE_NAME,
    TICKET_FLOW,
    TICKET_PROGRESS_STATES,
    AvailabilityState,
    OrderTicketStatus,
)
from app.modules.hospitality.events import RestaurantOrderFired, RestaurantOrderSettled
from app.modules.hospitality.models import OrderTicket, OrderTicketLine
from app.modules.hospitality.schemas import OrderTicketCreate, OrderTicketLineCreate
from app.modules.hospitality.service import availability
from app.modules.inventory import queries as inventory_queries


async def get_ticket(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> OrderTicket:
    """The ticket, or 404 ``hospitality.ticket_not_found``."""
    ticket = await session.get(OrderTicket, ticket_id)
    if ticket is None or ticket.tenant_id != tenant_id:
        raise NotFoundError(message="Order ticket not found", code="hospitality.ticket_not_found")
    return ticket


async def get_ticket_lines(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> list[OrderTicketLine]:
    """Every line on the ticket in entry order. One query; the caller never loops for lines."""
    stmt = (
        select(OrderTicketLine)
        .where(
            OrderTicketLine.tenant_id == tenant_id,
            OrderTicketLine.ticket_id == ticket_id,
        )
        .order_by(OrderTicketLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


# --- Transitions --------------------------------------------------------------


def _require_transition(ticket: OrderTicket, to_status: OrderTicketStatus) -> None:
    """The whole lifecycle rule: a ticket moves to the NEXT state in ``TICKET_FLOW`` and nowhere
    else. Ordering the enum instead of writing a transition table means the rule cannot drift from
    the states — a new state is added in one place and lands in the right position."""
    current = OrderTicketStatus(ticket.status)
    if current not in TICKET_FLOW:
        # A state OFF the sequence (CANCELLED, D-080) is terminal: nothing follows it, and
        # `.index()` would raise ValueError -> HTTP 500 instead of the honest 409.
        raise ConflictError(
            message=f"An order ticket in {current.value} is terminal and cannot move",
            code="hospitality.ticket_transition_invalid",
            details={
                "ticket_id": str(ticket.id),
                "status": current.value,
                "requested_status": to_status.value,
            },
        )
    if TICKET_FLOW.index(to_status) != TICKET_FLOW.index(current) + 1:
        raise ConflictError(
            message=f"An order ticket cannot move from {current.value} to {to_status.value}",
            code="hospitality.ticket_transition_invalid",
            details={
                "ticket_id": str(ticket.id),
                "status": current.value,
                "requested_status": to_status.value,
            },
        )


async def _apply_transition(
    session: AsyncSession, tenant_id: uuid.UUID, ticket: OrderTicket, to_status: OrderTicketStatus
) -> None:
    """Move the ticket and mirror the state onto its registry row, so the document-flow viewer and
    the ticket never disagree (D-012)."""
    ticket.status = to_status.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, ticket.document_id, status=to_status.value
    )


# --- Lines --------------------------------------------------------------------


async def _require_items(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> None:
    """Every ordered item must exist in inventory. ``item_id`` is an OPAQUE id with no FK (D-029),
    so this validation IS the referential integrity — without it a typo becomes a ticket line the
    kitchen can never cook and Task 5's BOM explosion can never resolve. Batched into ONE query and
    reporting ALL the bad ids: a mis-typed 8-line order is one error, not eight round trips ending
    at the first failure."""
    known = await inventory_queries.existing_item_ids(session, tenant_id, item_ids)
    missing = sorted({str(item_id) for item_id in item_ids if item_id not in known})
    if missing:
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="hospitality.item_not_found",
            details={"item_ids": missing},
        )


async def _write_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    payload_lines: list[OrderTicketLineCreate],
    *,
    start_at: int,
) -> Decimal:
    """Insert the lines numbered from ``start_at`` and return what they add to the ticket total.

    The single line writer both ``create_ticket`` and ``add_lines`` go through, so a ticket opened
    with its order and one built up dish by dish produce identical rows. ``line_amount`` is the
    product rounded to ``MONEY_SCALE`` — what ``MoneyType`` will store (D-015); rounding to a
    CURRENCY's own decimals is a posting/wire concern and stays out of stored state.

    The rounding happens per line and the header sums the ROUNDED lines, deliberately. Summing the
    exact products and rounding once at the end makes Σ(line_amount as stored) differ from
    total_amount by a micro-unit whenever two lines each carry a half-quantum remainder — a check
    whose itemisation does not add up to its bottom line, which no guest can be shown.

    Assumes the caller already ran ``_require_items``; both do, BEFORE touching the numbering
    sequence (see ``create_ticket``).
    """
    total = Decimal(0)
    for offset, line in enumerate(payload_lines):
        amount = quantize_money(
            Decimal(str(line.quantity)) * Decimal(str(line.unit_price)), MONEY_SCALE
        )
        total += amount
        session.add(
            OrderTicketLine(
                tenant_id=tenant_id,
                ticket_id=ticket_id,
                line_number=start_at + offset,
                item_id=line.item_id,
                quantity=Decimal(str(line.quantity)),
                unit_price=Decimal(str(line.unit_price)),
                line_amount=amount,
                seat_number=line.seat_number,
                notes=line.notes,
            )
        )
    return total


# --- The lifecycle ------------------------------------------------------------


async def create_ticket(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: OrderTicketCreate,
    *,
    opened_on: date | None = None,
) -> OrderTicket:
    """Open a check (PLAN 19 Task 4).

    Registers the document and claims the gapless TKT- number AT CREATION (the sales-order branch,
    not finance's number-at-post branch): a ticket is referenceable by the kitchen, the guest and
    Phase 20.6's folio the moment the server opens it, so there is no draft phase to defer to.

    Lines are OPTIONAL and an empty ticket is the normal first state: a server opens the check when
    the table is seated and takes the order after. Firing an empty ticket is what is refused.

    The items are validated BEFORE the number is claimed, deliberately. ``claim_number`` holds the
    tenant's sequence row lock until COMMIT by construction (D-012 gaplessness), and Q4 flags that
    lock as what serializes every other posting in the tenant — including the hotel's. A rejected
    order must therefore never have taken it.

    The service date is TODAY. It is NOT a request field (#207) — a restaurant sells today, and a
    backdated check claims a number from another year's counter (#209). Only seating passes
    ``opened_on``, so a party sitting at 23:50 orders onto the service day it booked.
    """
    ticket_id = uuid.uuid4()
    opened_on = opened_on or date.today()
    await _require_items(session, tenant_id, [line.item_id for line in payload.lines])
    document = await docflow.register_document(
        session,
        tenant_id,
        ORDER_TICKET_DOC_TYPE,
        ticket_id,
        doc_number=None,
        status=OrderTicketStatus.OPEN.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        ORDER_TICKET_SEQUENCE_NAME,
        ORDER_TICKET_NUMBER_PREFIX,
        ORDER_TICKET_NUMBER_PADDING,
        year_reset=True,
    )
    number = await claim_number(
        session, tenant_id, ORDER_TICKET_SEQUENCE_NAME, on_date=opened_on
    )
    ticket = OrderTicket(
        id=ticket_id,
        tenant_id=tenant_id,
        document_id=document.id,
        ticket_number=number,
        status=OrderTicketStatus.OPEN.value,
        opened_date=opened_on,
        table_code=payload.table_code,
        guest_count=payload.guest_count,
        total_amount=Decimal(0),
        notes=payload.notes,
    )
    session.add(ticket)
    await session.flush()
    ticket.total_amount = await _write_lines(
        session, tenant_id, ticket_id, payload.lines, start_at=1
    )
    await session.flush()
    await docflow.set_document_status(
        session,
        tenant_id,
        document.id,
        doc_number=number,
        status=OrderTicketStatus.OPEN.value,
    )
    return ticket


async def add_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    lines: list[OrderTicketLineCreate],
) -> OrderTicket:
    """Add dishes to an OPEN check, continuing the line numbering and raising the total.

    OPEN only: a fired line is already being cooked and already counted for depletion, so allowing
    a late addition would either be cooked-but-never-depleted food or a second depletion pass this
    phase does not have. A later course is a new ticket in v1 (Phase 19 ships no coursing).
    """
    if not lines:
        raise ValidationFailedError(message="No lines to add", code="hospitality.no_lines")
    await _require_items(session, tenant_id, [line.item_id for line in lines])
    ticket = await get_ticket(session, tenant_id, ticket_id)
    if OrderTicketStatus(ticket.status) != OrderTicketStatus.OPEN:
        raise ConflictError(
            message=f"Lines cannot be added to a {ticket.status} order ticket",
            code="hospitality.ticket_not_open",
            details={"ticket_id": str(ticket_id), "status": ticket.status},
        )
    highest = (
        await session.execute(
            select(func.max(OrderTicketLine.line_number)).where(
                OrderTicketLine.tenant_id == tenant_id,
                OrderTicketLine.ticket_id == ticket_id,
            )
        )
    ).scalar_one_or_none()
    added = await _write_lines(
        session, tenant_id, ticket_id, lines, start_at=(highest or 0) + 1
    )
    ticket.total_amount = Decimal(ticket.total_amount) + added
    await session.flush()
    return ticket


async def fire_ticket(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> OrderTicket:
    """Send the check to the kitchen — the commitment moment (Q4).

    Three things happen here and nowhere else:

    1. **The 86 bites.** Availability is read ONCE for every line's item and any EIGHTY_SIXED dish
       refuses the whole fire. Hiding a sold-out dish on the website is not enough: a server's
       terminal never read the website, and the kitchen cannot cook what does not exist.
    2. **Countdowns burn** — only for items actually resolving to LIMITED, so a ticket of dishes
       with no counter costs zero extra queries. Doing it here rather than at the website's door is
       what makes a POS order and a web order decrement the same counter.
    3. **``RestaurantOrderFired`` is published**, which is what Task 5 hangs the background
       depletion job off. Publishing does not dispatch: the caller's ``run_in_uow`` drains it, so
       the job submission lands in THIS transaction (D-011) and a D-013 replay returns one job id.

    A refusal raises before any state changes, so the ticket stays OPEN and the server can drop the
    dish from the order and fire again.
    """
    ticket = await get_ticket(session, tenant_id, ticket_id)
    _require_transition(ticket, OrderTicketStatus.SENT_TO_KITCHEN)

    lines = await get_ticket_lines(session, tenant_id, ticket_id)
    if not lines:
        raise ValidationFailedError(
            message="An order ticket with no lines cannot be fired",
            code="hospitality.ticket_empty",
            details={"ticket_id": str(ticket_id)},
        )

    resolved = await availability.availability_for_items(
        session, tenant_id, [line.item_id for line in lines]
    )
    unavailable = sorted(
        {
            line.item_id
            for line in lines
            if resolved[line.item_id].state == AvailabilityState.EIGHTY_SIXED
        },
        key=str,
    )
    if unavailable:
        # NAME the dishes (#205). A server holding a six-line check cannot act on "one of these is
        # 86'd" plus six UUIDs, and the label read costs one query on a path that is already
        # refusing — never on the path that succeeds.
        labels = await inventory_queries.item_labels(session, tenant_id, unavailable)
        named = [labels.get(item_id, str(item_id)) for item_id in unavailable]
        raise ValidationFailedError(
            message=(
                f"{'This dish is' if len(named) == 1 else 'These dishes are'} 86'd and cannot be "
                f"sent to the kitchen: {', '.join(named)}"
            ),
            code="hospitality.item_unavailable",
            details={
                "ticket_id": str(ticket_id),
                "item_ids": [str(item_id) for item_id in unavailable],
                "items": named,
            },
        )

    burns: dict[uuid.UUID, Decimal] = {}
    for line in lines:
        if resolved[line.item_id].state == AvailabilityState.LIMITED:
            burns[line.item_id] = burns.get(line.item_id, Decimal(0)) + Decimal(line.quantity)
    await availability.decrement_remaining_many(session, tenant_id, burns)

    fired_at = utcnow()
    ticket.fired_at = fired_at
    await _apply_transition(session, tenant_id, ticket, OrderTicketStatus.SENT_TO_KITCHEN)
    publish(
        session,
        RestaurantOrderFired(
            tenant_id=tenant_id,
            ticket_id=ticket.id,
            ticket_number=ticket.ticket_number,
            document_id=ticket.document_id,
            fired_at=fired_at.isoformat(),
        ),
    )
    return ticket


async def advance_ticket(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    to_status: OrderTicketStatus,
) -> OrderTicket:
    """Move a fired check through the kitchen's own progress: IN_PREP → READY → SERVED. Restricted
    to those three (``TICKET_PROGRESS_STATES``): firing and settling each carry effects a generic
    status update must never skip past — the 86 check and the fired event on one side, the settled
    event on the other — so they keep their own entry points.
    """
    if to_status not in TICKET_PROGRESS_STATES:
        raise ValidationFailedError(
            message=f"{to_status.value} is not a kitchen-progress status",
            code="hospitality.status_not_advanceable",
            details={"requested_status": to_status.value},
        )
    ticket = await get_ticket(session, tenant_id, ticket_id)
    _require_transition(ticket, to_status)
    await _apply_transition(session, tenant_id, ticket, to_status)
    return ticket


async def settle_ticket(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> OrderTicket:
    """Tender the check (terminal). Publishes ``RestaurantOrderSettled`` with the authoritative
    total, which is what Phase 20.6's room-charge bridge subscribes to. Deliberately carries NO
    stock effect: the ingredients left the storeroom when the ticket fired (Q4). Phase 19 takes no
    payment either (Q1's provider interface is Phase 20+), so settling records that the check is
    closed, nothing more.
    """
    ticket = await get_ticket(session, tenant_id, ticket_id)
    _require_transition(ticket, OrderTicketStatus.SETTLED)
    settled_at = utcnow()
    ticket.settled_at = settled_at
    await _apply_transition(session, tenant_id, ticket, OrderTicketStatus.SETTLED)
    publish(
        session,
        RestaurantOrderSettled(
            tenant_id=tenant_id,
            ticket_id=ticket.id,
            ticket_number=ticket.ticket_number,
            document_id=ticket.document_id,
            total_amount=Decimal(ticket.total_amount),
            settled_at=settled_at.isoformat(),
        ),
    )
    return ticket


async def cancel_ticket(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID, reason: str
) -> OrderTicket:
    """Close an OPEN check that should never have been opened (terminal, D-080).

    The ONE transition that is not a step along ``TICKET_FLOW``, and the only state change with a
    required reason: a check opened on the wrong table or for a party that walked has cooked
    nothing and moved no money, so closing it costs nothing — while leaving it OPEN forever makes
    the floor's live list unreadable.

    Refused after firing, with the SAME code ``add_lines`` uses, because it is the same rule: past
    that point the ingredients have left the storeroom, and a comp or a walk-out on a fired check
    is a money correction the Phase 20 folio owns rather than a status a server can pick. Publishes
    nothing — there is no effect to react to.
    """
    ticket = await get_ticket(session, tenant_id, ticket_id)
    current = OrderTicketStatus(ticket.status)
    if current is not OrderTicketStatus.OPEN:
        raise ConflictError(
            message="Only an OPEN check can be cancelled; a fired check is a folio correction",
            code="hospitality.ticket_not_open",
            details={"ticket_id": str(ticket_id), "status": current.value},
        )
    ticket.cancelled_at = utcnow()
    ticket.cancel_reason = reason
    await _apply_transition(session, tenant_id, ticket, OrderTicketStatus.CANCELLED)
    return ticket


__all__ = [
    "add_lines",
    "cancel_ticket",
    "advance_ticket",
    "create_ticket",
    "fire_ticket",
    "get_ticket",
    "get_ticket_lines",
    "settle_ticket",
]

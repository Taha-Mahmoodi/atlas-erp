"""Order tickets (PLAN 19 Task 4): the document, its lifecycle, and firing to the kitchen.

A ticket is a D-012 document — it registers in ``core_documents`` and claims a gapless ``TKT-``
number at creation, like every other permanent-at-creation document in Atlas. What is specific to a
restaurant is WHERE the ordering decision bites: at FIRE (send-to-kitchen), not at tender. Q4 is
emphatic that ingredients are consumed when the kitchen starts cooking — a dish comped after
service has already eaten them — so ``RestaurantOrderFired`` is the event Task 5 hangs depletion
off, and settle carries no stock effect at all.

The 86 also bites at fire: hiding a sold-out dish on the website is not enough, because a server
enters tickets on a terminal that never read the website. The check is ONE query for the whole
ticket (Q2: a derived answer costs ~1,080 for a 60-item menu), which is asserted here rather than
assumed — a per-line check would pass every behavioural test and quietly reintroduce the N+1.

Everything runs through the REAL service inside a uow (D-025/D-011) so published events actually
drain to their handlers.
"""

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.docflow import Document
from app.core.events import DomainEvent, run_in_uow, subscribe
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import (
    ORDER_TICKET_DOC_TYPE,
    AvailabilityState,
    OrderTicketStatus,
)
from app.modules.hospitality.events import RestaurantOrderFired, RestaurantOrderSettled
from app.modules.hospitality.models import OrderTicket
from app.modules.hospitality.schemas import OrderTicketCreate, OrderTicketLineCreate
from app.modules.hospitality.service import availability, tickets
from tests.conftest import QueryCounter


def _line(item_id: uuid.UUID, quantity: str = "1", price: str = "12.00") -> OrderTicketLineCreate:
    return OrderTicketLineCreate(
        item_id=item_id, quantity=Decimal(quantity), unit_price=Decimal(price)
    )


async def _open_ticket(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    lines: list[OrderTicketLineCreate],
    *,
    table_code: str = "T12",
) -> uuid.UUID:
    """Open a ticket through the real service and return its id (an id, not the instance: the
    commit expires the object)."""
    with tenant_context(tenant_id):
        ticket = await tickets.create_ticket(
            session,
            tenant_id,
            OrderTicketCreate(table_code=table_code, guest_count=2, lines=lines),
        )
        await session.commit()
        return ticket.id


async def _run(
    session: AsyncSession, tenant_id: uuid.UUID, work: Callable[[], Awaitable[object]]
) -> None:
    """Drive a service call inside a uow so publishes drain (D-011)."""
    with tenant_context(tenant_id):
        await run_in_uow(session, work)


async def _read(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> OrderTicket:
    session.expire_all()
    with tenant_context(tenant_id):
        return await tickets.get_ticket(session, tenant_id, ticket_id)


def _capture(event_type: type[DomainEvent]) -> list[DomainEvent]:
    """Subscribe a recorder for one event type (the finance/test_journal precedent). The autouse
    ``clear_event_subscriptions`` fixture drops it after the test."""
    seen: list[DomainEvent] = []

    async def handler(_session: AsyncSession, event: DomainEvent) -> None:
        seen.append(event)

    subscribe(event_type.key, handler)
    return seen


# --- The document ------------------------------------------------------------


async def test_a_ticket_registers_a_document_and_claims_a_tkt_number(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """D-012: a ticket is a real document, not a scratch row — it is referenceable the moment it
    exists (the orders/receipts claim-at-creation branch), so Phase 20.6's folio can link to it."""
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])
    ticket = await _read(db_session, tenant_a, ticket_id)

    assert ticket.ticket_number.startswith("TKT-")
    assert ticket.status == OrderTicketStatus.OPEN

    with tenant_context(tenant_a):
        stmt = select(Document).where(
            Document.tenant_id == tenant_a,
            Document.doc_type == ORDER_TICKET_DOC_TYPE,
            Document.doc_id == ticket_id,
        )
        document = (await db_session.execute(stmt)).scalar_one()
    assert document.doc_number == ticket.ticket_number
    assert document.status == OrderTicketStatus.OPEN


async def test_the_total_is_the_sum_of_the_line_amounts(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    dish_id: uuid.UUID,
    make_dish: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """The ticket total is MAINTAINED, never recomputed on read: Q6 requires the order response to
    be authoritative over any price the website cached."""
    other = await make_dish("DISH-002", "Risotto")
    ticket_id = await _open_ticket(
        db_session,
        tenant_a,
        [_line(dish_id, "2", "12.50"), _line(other, "1", "9.00")],
    )
    assert (await _read(db_session, tenant_a, ticket_id)).total_amount == Decimal("34.00")


async def test_lines_added_later_extend_the_numbering_and_the_total(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    dish_id: uuid.UUID,
    make_dish: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    other = await make_dish("DISH-002", "Risotto")
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id, "1", "12.00")])

    with tenant_context(tenant_a):
        await tickets.add_lines(db_session, tenant_a, ticket_id, [_line(other, "1", "9.00")])
        await db_session.commit()

    with tenant_context(tenant_a):
        lines = await tickets.get_ticket_lines(db_session, tenant_a, ticket_id)
    assert [line.line_number for line in lines] == [1, 2]
    assert (await _read(db_session, tenant_a, ticket_id)).total_amount == Decimal("21.00")


async def test_an_unknown_item_cannot_be_ordered(
    db_session: AsyncSession, tenant_a: uuid.UUID, menu_setup: object
) -> None:
    """``item_id`` is an OPAQUE inventory id (D-029) with no FK, so existence is validated through
    inventory/queries — otherwise a typo becomes a ticket line the kitchen can never cook."""
    with pytest.raises(ValidationFailedError), tenant_context(tenant_a):
        await tickets.create_ticket(
            db_session, tenant_a, OrderTicketCreate(lines=[_line(uuid.uuid4())])
        )


# --- The lifecycle -----------------------------------------------------------


async def test_firing_moves_the_ticket_to_the_kitchen_and_refuses_a_second_fire(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])
    await _run(db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id))

    ticket = await _read(db_session, tenant_a, ticket_id)
    assert ticket.status == OrderTicketStatus.SENT_TO_KITCHEN
    assert ticket.fired_at is not None

    with pytest.raises(ConflictError):
        await _run(
            db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id)
        )


async def test_a_ticket_cannot_skip_the_kitchen(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """The lifecycle is strictly sequential for exactly one reason: SENT_TO_KITCHEN is where
    ingredients are consumed (Q4), so a ticket that could jump straight to SERVED or SETTLED would
    be revenue with no depletion at all."""
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])
    with pytest.raises(ConflictError), tenant_context(tenant_a):
        await tickets.advance_ticket(
            db_session, tenant_a, ticket_id, OrderTicketStatus.SERVED
        )
    with pytest.raises(ConflictError), tenant_context(tenant_a):
        await tickets.settle_ticket(db_session, tenant_a, ticket_id)


async def test_the_full_lifecycle_runs_to_settled(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])
    await _run(db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id))
    for status in (
        OrderTicketStatus.IN_PREP,
        OrderTicketStatus.READY,
        OrderTicketStatus.SERVED,
    ):
        with tenant_context(tenant_a):
            await tickets.advance_ticket(db_session, tenant_a, ticket_id, status)
            await db_session.commit()
        assert (await _read(db_session, tenant_a, ticket_id)).status == status

    await _run(db_session, tenant_a, lambda: tickets.settle_ticket(db_session, tenant_a, ticket_id))
    ticket = await _read(db_session, tenant_a, ticket_id)
    assert ticket.status == OrderTicketStatus.SETTLED
    assert ticket.settled_at is not None


async def test_lines_cannot_be_added_once_the_ticket_is_fired(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """A fired line is already being cooked and already counted for depletion; a later course is a
    new ticket in v1 (Phase 19 ships no coursing)."""
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])
    await _run(db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id))
    with pytest.raises(ConflictError), tenant_context(tenant_a):
        await tickets.add_lines(db_session, tenant_a, ticket_id, [_line(dish_id)])


async def test_an_empty_ticket_cannot_be_fired(
    db_session: AsyncSession, tenant_a: uuid.UUID, menu_setup: object
) -> None:
    ticket_id = await _open_ticket(db_session, tenant_a, [])
    with pytest.raises(ValidationFailedError):
        await _run(
            db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id)
        )


# --- Availability bites at fire ----------------------------------------------


async def test_firing_an_86d_item_is_refused(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """The 86 has to bite at fire, not only hide the dish on the website: a server's terminal never
    read the website, and the kitchen cannot cook what does not exist."""
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])
    with tenant_context(tenant_a):
        await availability.set_availability(
            db_session,
            tenant_a,
            dish_id,
            state=AvailabilityState.EIGHTY_SIXED,
            reason="out of feta",
        )
        await db_session.commit()

    with pytest.raises(ValidationFailedError) as excinfo:
        await _run(
            db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id)
        )
    assert excinfo.value.code == "hospitality.item_unavailable"
    assert (await _read(db_session, tenant_a, ticket_id)).status == OrderTicketStatus.OPEN


async def test_the_availability_check_is_one_query_for_the_whole_ticket(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    make_dish: Callable[..., Awaitable[uuid.UUID]],
    query_counter: Callable[[], QueryCounter],
) -> None:
    """Q2's N+1 in miniature. A per-line 86 check passes every behavioural test above and still
    costs one query per line; the batched read is the point, so it is asserted directly."""
    dishes = [await make_dish(f"DISH-{index:03d}", f"Dish {index}") for index in range(8)]
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish) for dish in dishes])

    with query_counter() as counted, tenant_context(tenant_a):
        await tickets.fire_ticket(db_session, tenant_a, ticket_id)

    availability_reads = [
        statement for statement in counted.statements if "hsp_menu_availability" in statement
    ]
    assert len(availability_reads) == 1, "\n".join(counted.statements)


async def test_firing_burns_a_countdown_and_86s_the_dish_at_zero(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """The countdown burns at FIRE, not at the website's door: a dish ordered on a server's
    terminal must decrement the same counter, or the last portion is sold twice."""
    with tenant_context(tenant_a):
        await availability.set_availability(
            db_session,
            tenant_a,
            dish_id,
            state=AvailabilityState.LIMITED,
            remaining_qty=Decimal(2),
        )
        await db_session.commit()

    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id, "2")])
    await _run(db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id))

    with tenant_context(tenant_a):
        resolved = await availability.availability_for_items(db_session, tenant_a, [dish_id])
    assert resolved[dish_id].state == AvailabilityState.EIGHTY_SIXED


# --- Events ------------------------------------------------------------------


async def test_fire_publishes_the_fired_event_and_settle_does_not(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """Q4: ingredients are consumed at fire, not at tender — a dish comped after service has
    already eaten them, and a depletion hanging off settle would also block the guest's payment."""
    fired = _capture(RestaurantOrderFired)
    settled = _capture(RestaurantOrderSettled)

    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])
    await _run(db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id))

    assert [event.ticket_id for event in fired] == [ticket_id]  # type: ignore[attr-defined]
    assert settled == []


async def test_settle_publishes_the_settled_event_with_the_total(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """Settle is the money moment Phase 20.6's room-charge bridge subscribes to, so the event
    carries the authoritative total rather than making a subscriber re-read the ticket."""
    settled = _capture(RestaurantOrderSettled)

    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id, "2", "12.50")])
    await _run(db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id))
    for status in (
        OrderTicketStatus.IN_PREP,
        OrderTicketStatus.READY,
        OrderTicketStatus.SERVED,
    ):
        with tenant_context(tenant_a):
            await tickets.advance_ticket(db_session, tenant_a, ticket_id, status)
            await db_session.commit()
    await _run(db_session, tenant_a, lambda: tickets.settle_ticket(db_session, tenant_a, ticket_id))

    assert len(settled) == 1
    assert settled[0].total_amount == Decimal("25.00")  # type: ignore[attr-defined]


# --- Tenancy -----------------------------------------------------------------


async def test_another_tenant_cannot_read_the_ticket(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID, dish_id: uuid.UUID
) -> None:
    from app.core.exceptions import NotFoundError

    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])
    with pytest.raises(NotFoundError), tenant_context(tenant_b):
        await tickets.get_ticket(db_session, tenant_b, ticket_id)


# --- Cancelling an OPEN check (#206, D-080) ------------------------------------


async def test_an_open_check_can_be_cancelled_with_a_reason(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """A check opened on the wrong table has cooked nothing and moved no money, so it closes —
    and says why. Without this the floor's live list fills with dead checks it cannot tell from
    live ones."""
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])

    await _run(
        db_session,
        tenant_a,
        lambda: tickets.cancel_ticket(db_session, tenant_a, ticket_id, "opened on the wrong table"),
    )

    ticket = await _read(db_session, tenant_a, ticket_id)
    assert ticket.status == OrderTicketStatus.CANCELLED
    assert ticket.cancel_reason == "opened on the wrong table"
    assert ticket.cancelled_at is not None


async def test_a_fired_check_cannot_be_cancelled(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """The line the cancel stops at: past the fire the ingredients have left the storeroom, so a
    walk-out is a money correction the folio owns, not a status a server can pick."""
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])
    await _run(db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id))

    with pytest.raises(ConflictError) as excinfo:
        await _run(
            db_session,
            tenant_a,
            lambda: tickets.cancel_ticket(db_session, tenant_a, ticket_id, "party walked"),
        )

    assert excinfo.value.code == "hospitality.ticket_not_open"
    ticket = await _read(db_session, tenant_a, ticket_id)
    assert ticket.status == OrderTicketStatus.SENT_TO_KITCHEN


async def test_a_cancelled_check_is_terminal(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """CANCELLED is a branch off OPEN, not a step in TICKET_FLOW: nothing may follow it, and it
    cannot be cancelled twice."""
    ticket_id = await _open_ticket(db_session, tenant_a, [_line(dish_id)])
    await _run(
        db_session,
        tenant_a,
        lambda: tickets.cancel_ticket(db_session, tenant_a, ticket_id, "walked"),
    )

    with pytest.raises(ConflictError):
        await _run(
            db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id)
        )
    with pytest.raises(ConflictError):
        await _run(
            db_session,
            tenant_a,
            lambda: tickets.cancel_ticket(db_session, tenant_a, ticket_id, "again"),
        )


# --- The 86 refusal names the dish (#205) --------------------------------------


async def test_the_86_refusal_names_every_offending_dish(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    dish_id: uuid.UUID,
    make_dish: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """A server holding a multi-line check cannot act on "one of these is 86'd" and a UUID. The
    message names the dishes, and the details carry them for the UI."""
    second = await make_dish(item_code="DISH-SOUP", name="Onion Soup")
    third = await make_dish(item_code="DISH-TART", name="Apple Tart")
    ticket_id = await _open_ticket(
        db_session, tenant_a, [_line(dish_id), _line(second), _line(third)]
    )
    with tenant_context(tenant_a):
        for item_id, reason in ((second, "no onions"), (third, "no apples")):
            await availability.set_availability(
                db_session, tenant_a, item_id, state=AvailabilityState.EIGHTY_SIXED, reason=reason
            )
        await db_session.commit()

    with pytest.raises(ValidationFailedError) as excinfo:
        await _run(
            db_session, tenant_a, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id)
        )

    error = excinfo.value
    assert error.code == "hospitality.item_unavailable"
    assert "DISH-SOUP — Onion Soup" in error.message
    assert "DISH-TART — Apple Tart" in error.message
    # The available dish is not named, and the raw ids stay for machine callers.
    assert "DISH-TART" in str(error.details["items"])
    assert len(error.details["item_ids"]) == 2

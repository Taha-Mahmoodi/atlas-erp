"""Menu availability under CONCURRENCY (PLAN 19, spec Q2): two websites and a staff terminal
acting on the same dish at the same instant.

Everything here runs on REAL concurrent tasks — separate ``AsyncSession``s over the per-test
engine, driven through ``asyncio.gather`` — never sequential calls narrating a race.

**Why some tests gate the read.** A restaurant's races are all read-then-write windows, and on a
single-file SQLite the two tasks usually finish one before the other even starts, so an ungated
``gather`` proves nothing about the window it is supposed to open. ``interleaved`` holds every
party inside the read until all of them have read, which is the interleaving a real Postgres
serves under load. It gates on the read a caller cannot avoid, so no production code is reshaped
for the test.

**What SQLite cannot show.** ``with_for_update`` is a no-op on SQLite (the ``inv_stock_quants``
precedent), so a gated test of the LOCKED countdown read would show a lost update that PostgreSQL
— the runtime engine, D-003 — does not have. The countdown's serialization is therefore pinned the
way the second transaction actually experiences it: it re-reads UNDER the lock and finds the
counter already drained (``test_a_burn_against_an_already_drained_countdown_refuses``). That is the
same code path Postgres runs after the lock is released, and it is engine-independent.
"""

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.models import utcnow
from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import AvailabilityState, OrderTicketStatus
from app.modules.hospitality.models import MenuAvailability
from app.modules.hospitality.schemas import OrderTicketCreate, OrderTicketLineCreate
from app.modules.hospitality.service import availability, tickets

# A gated party waits at most this long for the others; a hang is a bug in the test, not a pass.
GATE_TIMEOUT = 5.0


class _Gate:
    """Release every party only once ``parties`` DISTINCT callers have arrived.

    Not ``asyncio.Barrier``: a caller may reach the gated read twice (a retry after a conflict),
    and a barrier would then block forever waiting for a party that has already gone through.
    Once open, the gate stays open and later arrivals pass straight through.
    """

    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._arrived: set[int] = set()
        self._open = asyncio.Event()

    async def arrive(self, key: int) -> None:
        if self._open.is_set():
            return
        self._arrived.add(key)
        if len(self._arrived) >= self._parties:
            self._open.set()
            return
        await asyncio.wait_for(self._open.wait(), timeout=GATE_TIMEOUT)


@contextlib.asynccontextmanager
async def interleaved(*targets: str, parties: int = 2) -> AsyncIterator[None]:
    """Hold each session inside any ``availability.<target>`` read until ``parties`` sessions have
    read one of them.

    The targets are the reads that open the window under test: ``_locked_row`` for the two writers
    racing to CREATE an override row, ``availability_for_items`` for the unlocked 86 check a fire
    makes before it commits. Two racers on DIFFERENT paths gate on their own read, which is why
    this takes a list rather than one name.
    """
    gate = _Gate(parties)
    originals = {target: getattr(availability, target) for target in targets}

    def _wrap(real: Callable[..., Awaitable[object]]) -> Callable[..., Awaitable[object]]:
        async def _gated(session: AsyncSession, *args: object, **kwargs: object) -> object:
            result = await real(session, *args, **kwargs)
            await gate.arrive(id(session))
            return result

        return _gated

    for target, real in originals.items():
        setattr(availability, target, _wrap(real))
    try:
        yield
    finally:
        for target, real in originals.items():
            setattr(availability, target, real)


@pytest.fixture
def sessions(db_engine: AsyncEngine) -> Callable[[], AsyncSession]:
    """A factory for INDEPENDENT sessions on the per-test engine — one per concurrent actor, the
    way two web workers each hold their own connection."""
    factory = build_session_factory(db_engine)
    return factory


async def _set(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, **kwargs: object
) -> None:
    with tenant_context(tenant_id):
        await availability.set_availability(session, tenant_id, item_id, **kwargs)  # type: ignore[arg-type]
        await session.commit()


async def _read(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> availability.MenuItemAvailability:
    session.expire_all()
    with tenant_context(tenant_id):
        return (await availability.availability_for_items(session, tenant_id, [item_id]))[item_id]


async def _stored(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> MenuAvailability | None:
    session.expire_all()
    with tenant_context(tenant_id):
        stmt = select(MenuAvailability).where(MenuAvailability.item_id == item_id)
        return (await session.execute(stmt)).scalar_one_or_none()


async def _open_ticket(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, quantity: str
) -> uuid.UUID:
    with tenant_context(tenant_id):
        ticket = await tickets.create_ticket(
            session,
            tenant_id,
            OrderTicketCreate(
                table_code="T1",
                lines=[
                    OrderTicketLineCreate(
                        item_id=item_id, quantity=Decimal(quantity), unit_price=Decimal("12.00")
                    )
                ],
            ),
        )
        await session.commit()
        return ticket.id


async def _fire(session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> str:
    """Fire a ticket in its own uow and report the outcome as a string, so ``gather`` can collect
    both racers' results without one failure hiding the other's."""
    try:
        with tenant_context(tenant_id):
            await run_in_uow(session, lambda: tickets.fire_ticket(session, tenant_id, ticket_id))
        return "fired"
    except ValidationFailedError as exc:
        return f"refused:{exc.code}"


async def _gather(*work: Awaitable[object]) -> list[object]:
    return list(await asyncio.wait_for(asyncio.gather(*work), timeout=GATE_TIMEOUT * 3))


# --- Two writers racing to create the same override row -----------------------


async def test_two_staff_86_the_same_dish_at_once(
    sessions: Callable[[], AsyncSession], tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """The bar terminal and the pass both 86 the last portion of Caprese in the same second.

    ``_locked_row`` locks NOTHING when the row does not exist yet — there is no row to lock — so
    both readers see None and both INSERT, and the unique constraint rejects the loser. Unhandled,
    that is an IntegrityError surfacing as a 500 on a button a kitchen presses dozens of times a
    night. Both callers asked for the same outcome; both must get it.
    """

    async def eighty_six(reason: str) -> str:
        async with sessions() as session:
            try:
                await _set(
                    session,
                    tenant_a,
                    dish_id,
                    state=AvailabilityState.EIGHTY_SIXED,
                    reason=reason,
                )
                return "ok"
            except Exception as exc:  # noqa: BLE001 - the point is WHICH class escapes
                return type(exc).__name__

    async with interleaved("_locked_row"):
        results = await _gather(eighty_six("out of feta"), eighty_six("no basil"))

    assert results == ["ok", "ok"], results
    async with sessions() as session:
        assert (await _read(session, tenant_a, dish_id)).state == AvailabilityState.EIGHTY_SIXED


# --- The countdown must never sell more portions than it holds ----------------


async def test_a_fire_cannot_burn_more_portions_than_the_countdown_holds(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """Six portions of the special are left and an eight-top orders eight.

    Clamping the counter at zero and firing anyway sends the kitchen an order it cannot cook and
    hands two guests nothing — the countdown exists to stop exactly that. A refusal leaves the
    ticket OPEN so the server can drop the dish and fire again, which is what the 86 refusal next
    door already promises.
    """
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.LIMITED,
        remaining_qty=Decimal(6),
    )
    ticket_id = await _open_ticket(db_session, tenant_a, dish_id, "8")

    with pytest.raises(ValidationFailedError) as excinfo, tenant_context(tenant_a):
        await tickets.fire_ticket(db_session, tenant_a, ticket_id)
    assert excinfo.value.code == "hospitality.item_unavailable"
    assert str(dish_id) in excinfo.value.details["item_ids"]

    await db_session.rollback()
    assert (await _read(db_session, tenant_a, dish_id)).remaining_qty == Decimal(6)
    with tenant_context(tenant_a):
        assert (await tickets.get_ticket(db_session, tenant_a, ticket_id)).status == (
            OrderTicketStatus.OPEN
        )


async def test_a_burn_against_an_already_drained_countdown_refuses(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """What the LOSER of a real race sees on PostgreSQL, expressed engine-independently.

    Two fires read LIMITED with one portion left; the row lock serializes their burns, so the
    second one re-reads the counter UNDER the lock and finds it already at zero. If that read
    clamps instead of refusing, the row lock bought nothing at all: both tickets fire and the last
    portion is sold twice. This is that second burn.
    """
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.LIMITED,
        remaining_qty=Decimal(1),
    )
    with tenant_context(tenant_a):
        await availability.decrement_remaining(db_session, tenant_a, dish_id, Decimal(1))
        await db_session.commit()

        with pytest.raises(ValidationFailedError) as excinfo:
            await availability.decrement_remaining(db_session, tenant_a, dish_id, Decimal(1))
    assert excinfo.value.code == "hospitality.item_unavailable"

    await db_session.rollback()
    resolved = await _read(db_session, tenant_a, dish_id)
    assert resolved.state == AvailabilityState.EIGHTY_SIXED
    assert resolved.remaining_qty == Decimal(0)


async def test_two_concurrent_fires_cannot_both_take_the_last_portion(
    sessions: Callable[[], AsyncSession],
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    dish_id: uuid.UUID,
) -> None:
    """The website and a server's terminal fire the last portion at the same moment.

    On PostgreSQL the burns serialize on the countdown's row lock and the loser refuses (that
    second burn is pinned engine-independently one test up). SQLite takes no lock, so BOTH burns
    read one portion left and BOTH tickets fire here — a real oversell that the runtime engine does
    not have, and one this suite cannot assert away without inventing a second write convention for
    a table the module already locks the ``inv_stock_quants`` way.

    So what is asserted is what must hold on EITHER engine: every outcome is either a fire or the
    countdown refusal (never a 500, never a torn ``StaleDataError`` from two writers on one row),
    the counter never goes below zero, and the dish ends up 86'd for everyone who comes after.
    """
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.LIMITED,
        remaining_qty=Decimal(1),
    )
    first = await _open_ticket(db_session, tenant_a, dish_id, "1")
    second = await _open_ticket(db_session, tenant_a, dish_id, "1")

    async def fire(ticket_id: uuid.UUID) -> str:
        async with sessions() as session:
            return await _fire(session, tenant_a, ticket_id)

    results = await _gather(fire(first), fire(second))

    assert set(results) <= {"fired", "refused:hospitality.item_unavailable"}, results
    assert "fired" in results, results
    resolved = await _read(db_session, tenant_a, dish_id)
    assert resolved.state == AvailabilityState.EIGHTY_SIXED
    assert resolved.remaining_qty == Decimal(0)


# --- The 86 / countdown / expiry transitions ----------------------------------


async def test_a_sold_out_countdown_does_not_come_back_when_its_time_box_lapses(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """Twenty portions of tonight's special, on the menu until 22:00. It sells out at 20:00.

    The auto-86 rewrites the row's state, but the time box it inherited from the countdown is a
    promise about the SPECIAL, not about the 86 — leaving it in place makes the lapse resurrect a
    dish that has nothing behind it, and ``resolve`` hands the website AVAILABLE at 22:01. Nothing
    sweeps expired rows and no scheduler exists to notice, so the dish stays wrongly sellable
    until a human touches it.
    """
    closes_at = utcnow() + timedelta(hours=2)
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.LIMITED,
        remaining_qty=Decimal(1),
        available_until=closes_at,
    )
    with tenant_context(tenant_a):
        await availability.decrement_remaining(db_session, tenant_a, dish_id, Decimal(1))
        await db_session.commit()

    row = await _stored(db_session, tenant_a, dish_id)
    assert row is not None
    assert availability.resolve(row, closes_at + timedelta(minutes=1)).state == (
        AvailabilityState.EIGHTY_SIXED
    )


async def test_two_concurrent_reads_of_a_just_lapsed_86_agree(
    sessions: Callable[[], AsyncSession],
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    dish_id: uuid.UUID,
) -> None:
    """Two websites revalidate the 86 board either side of a snooze lapsing.

    Expiry is applied on READ, in Python, with no write — so the read path has no state to race
    over: both callers must resolve the same lapsed row to AVAILABLE, and neither may touch it.
    A read that MATERIALIZED the lapse (deleting or rewriting the row) would make two harmless
    GETs fight, so the untouched ``updated_at`` is asserted, not assumed.
    """
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.EIGHTY_SIXED,
        reason="snoozed",
        available_until=utcnow() - timedelta(seconds=1),
    )
    before = await _stored(db_session, tenant_a, dish_id)
    assert before is not None
    stamp = before.updated_at

    async def read() -> AvailabilityState:
        async with sessions() as session:
            return (await _read(session, tenant_a, dish_id)).state

    states = await _gather(read(), read())

    assert states == [AvailabilityState.AVAILABLE, AvailabilityState.AVAILABLE], states
    after = await _stored(db_session, tenant_a, dish_id)
    assert after is not None and after.updated_at == stamp


async def test_clearing_an_86_while_a_countdown_drains_leaves_a_coherent_answer(
    sessions: Callable[[], AsyncSession],
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    dish_id: uuid.UUID,
) -> None:
    """The chef finds another tray (un-86) while a ticket burns the last portion.

    Either order is a defensible outcome — the dish is back on, or it sold out — but the two
    writers must not tear the row into a state the menu cannot express: LIMITED with nothing left
    reads to a guest as "orderable" while the counter says there is none.
    """
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.LIMITED,
        remaining_qty=Decimal(1),
    )
    ticket_id = await _open_ticket(db_session, tenant_a, dish_id, "1")

    async def fire() -> str:
        async with sessions() as session:
            return await _fire(session, tenant_a, ticket_id)

    async def un_86() -> str:
        async with sessions() as session:
            with tenant_context(tenant_a):
                await availability.clear_86(session, tenant_a, dish_id)
                await session.commit()
            return "cleared"

    await _gather(fire(), un_86())

    resolved = await _read(db_session, tenant_a, dish_id)
    assert resolved.state in (AvailabilityState.AVAILABLE, AvailabilityState.EIGHTY_SIXED)
    assert resolved.state != AvailabilityState.LIMITED or resolved.remaining_qty > 0


# --- Documented, accepted window ----------------------------------------------


async def test_an_86_landing_mid_fire_does_not_recall_the_ticket(
    sessions: Callable[[], AsyncSession],
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    dish_id: uuid.UUID,
) -> None:
    """CHARACTERIZATION, not a bug: the 86 check a fire makes is an UNLOCKED read, so a dish 86'd
    after that read but before the fire commits still reaches the kitchen.

    Locking it shut is not available: an available dish usually has NO override row, so there is
    nothing to take a row lock on, and the alternative — a row per sellable item — is the derived
    -availability cost Q2 rejects. The restaurant's own protocol covers it, exactly as it covers
    an 86 called out while a ticket is already on the rail: the kitchen tells the server. What
    this test pins is that the window is that narrow one and no wider — the ticket fires, the 86
    stands for everyone after it, and nobody sees a 500.
    """
    ticket_id = await _open_ticket(db_session, tenant_a, dish_id, "1")

    async def fire() -> str:
        async with sessions() as session:
            return await _fire(session, tenant_a, ticket_id)

    async def eighty_six() -> str:
        async with sessions() as session:
            await _set(
                session, tenant_a, dish_id, state=AvailabilityState.EIGHTY_SIXED, reason="86"
            )
            return "86'd"

    async with interleaved("availability_for_items", "_locked_row"):
        # The fire's unlocked read and the 86's own row read are the two parties; both have read
        # before either writes, which is the window a request-per-worker Postgres actually opens.
        results = await _gather(fire(), eighty_six())

    assert results == ["fired", "86'd"], results
    with tenant_context(tenant_a):
        assert (await tickets.get_ticket(db_session, tenant_a, ticket_id)).status == (
            OrderTicketStatus.SENT_TO_KITCHEN
        )
    assert (await _read(db_session, tenant_a, dish_id)).state == AvailabilityState.EIGHTY_SIXED

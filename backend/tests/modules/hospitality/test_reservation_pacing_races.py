"""The pacing counter under CONCURRENCY (Phase 21, spec Q3): two parties racing the last covers,
and a cancellation racing a booking on the same slot.

**These are ``-m pg`` tests, and that is the point.** ``with_for_update`` is a NO-OP on SQLite
(D-003/D-020, the ``inv_stock_quants`` precedent), so a gated race there shows a lost update that
PostgreSQL — the runtime engine — does not have. The neighbouring
``test_availability_races.py`` handles that by asserting a SET of acceptable outcomes on both
engines; the counter here has an EXACT answer on the engine that takes the lock, so it is asserted
where it is true rather than weakened until it is true everywhere. The engine-independent halves
(a full slot refuses, a release restores) are covered in ``test_table_reservations.py``.

Everything runs on REAL concurrent tasks — separate ``AsyncSession``s over one Postgres engine,
driven through ``asyncio.gather`` — never sequential calls narrating a race. ``interleaved`` holds
each party inside a read it cannot avoid until both have got there, so the two really are inside
the window; it gates BEFORE the locked slot read, never inside it, because a gate held while one
task owns the row lock would simply deadlock the other against it.
"""

import asyncio
import contextlib
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.models import utcnow
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.models import Tenant
from app.modules.hospitality.models import ServiceSlot, TableReservation
from app.modules.hospitality.reservation_schemas import TableReservationCreate
from app.modules.hospitality.service import pacing, reservations

_URL = os.environ.get("ATLAS_DATABASE_URL", "")

# A gated party waits at most this long for the other; a hang is a bug in the test, not a pass.
GATE_TIMEOUT = 5.0

# Every table these races touch, plus the tenant root they hang off. TRUNCATE rather than a
# per-test schema: the pg job runs against one migrated database (the test_allocation precedent).
_TABLES = (
    "hsp_table_reservations, hsp_service_slots, hsp_reservation_settings, "
    "hsp_order_ticket_lines, hsp_order_tickets, core_audit_log, core_doc_links, "
    "core_documents, core_number_sequences, adm_tenants"
)


@pytest.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """A real Postgres engine for the -m pg variant; skipped on the SQLite run."""
    if not _URL.startswith("postgresql"):
        pytest.skip("pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL")
    engine = create_async_engine(_URL)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
    yield engine
    await engine.dispose()


@pytest.fixture
async def pg_tenant(pg_engine: AsyncEngine) -> uuid.UUID:
    """One tenant to book against. A reservation references no item, no price and no stock, so this
    is the entire fixture surface the phase needs."""
    async with build_session_factory(pg_engine)() as session:
        with system_context():
            tenant = Tenant(slug=f"rsv-{uuid.uuid4().hex[:8]}", name="Pacing")
            session.add(tenant)
            await session.commit()
            return tenant.id


class _Gate:
    """Release every party only once ``parties`` DISTINCT callers have arrived (the
    ``test_availability_races`` shape: not ``asyncio.Barrier``, because a caller may reach the
    gated read twice and a barrier would then wait forever for a party already through)."""

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
async def interleaved(*targets: tuple[object, str], parties: int = 2) -> AsyncIterator[None]:
    """Hold each session inside one of the named ``(module, function)`` reads until ``parties``
    sessions have passed one of them, so both racers are genuinely inside the window.

    The targets are always reads taken BEFORE the slot's ``with_for_update``: a booking's settings
    read, a cancellation's reservation load. Gating inside the locked read instead would have one
    task holding the row lock while it waits for a task that is blocked on that very lock.
    """
    gate = _Gate(parties)
    originals = [(module, name, getattr(module, name)) for module, name in targets]

    def _wrap(real: Callable[..., Awaitable[object]]) -> Callable[..., Awaitable[object]]:
        async def _gated(session: AsyncSession, *args: object, **kwargs: object) -> object:
            result = await real(session, *args, **kwargs)
            await gate.arrive(id(session))
            return result

        return _gated

    for module, name, real in originals:
        setattr(module, name, _wrap(real))
    try:
        yield
    finally:
        for module, name, real in originals:
            setattr(module, name, real)


def _service_date() -> date:
    return utcnow().date() + timedelta(days=1)


def _slot(service_date: date) -> datetime:
    return datetime.combine(service_date, time(19, 0), tzinfo=UTC)


async def _book(
    factory: Callable[[], AsyncSession], tenant_id: uuid.UUID, party_size: int, guest: str
) -> str:
    """One booking in its own session and uow, reporting its outcome as a string so ``gather`` can
    collect both racers without one failure hiding the other's."""
    service_date = _service_date()
    async with factory() as session:
        try:
            with tenant_context(tenant_id):
                await run_in_uow(
                    session,
                    lambda: reservations.create_reservation(
                        session,
                        tenant_id,
                        TableReservationCreate(
                            service_date=service_date,
                            slot_start=_slot(service_date),
                            party_size=party_size,
                            guest_name=guest,
                        ),
                    ),
                )
            return "confirmed"
        except ValidationFailedError as exc:
            return f"refused:{exc.code}"


async def _counters(pg_engine: AsyncEngine, tenant_id: uuid.UUID) -> tuple[int, int]:
    async with build_session_factory(pg_engine)() as session:
        with tenant_context(tenant_id):
            row = (
                await session.execute(
                    select(ServiceSlot).where(ServiceSlot.service_date == _service_date())
                )
            ).scalar_one()
            return row.covers_booked, row.parties_booked


@pytest.mark.pg
async def test_two_bookings_racing_the_last_covers_serialize(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID
) -> None:
    """Six covers left at 19:00 and two parties of four book at the same instant. EXACTLY ONE
    confirms; the loser gets ``hospitality.slot_full``.

    This is the whole reason the counter is LOCKED and not merely CHECKed. Without the row lock both
    bookings read ``covers_booked = 4``, both pass their pre-flight against ``covers_max = 10``, and
    the room is sold twelve covers it does not have — and the CHECK does not fire either, because
    each write on its own is legal. The oversell is silent, and the only thing that prevents it is
    the second booking re-reading the counter UNDER the lock and refusing, which is the answer a
    website can turn into "19:15 instead?".

    The slot is MATERIALISED FIRST, deliberately. On an empty slot the two racers collide on
    ``uq_hsp_service_slots_...`` instead and PostgreSQL serializes them on the unique index, so the
    test would pass with the lock deleted — proving the constraint, not the mechanism.
    """
    factory = build_session_factory(pg_engine)
    async with factory() as session:
        with tenant_context(pg_tenant):
            await pacing.set_settings(
                session, pg_tenant, pacing.ResolvedSettings(default_covers_max=10)
            )
            await session.commit()
    assert await _book(factory, pg_tenant, 4, "Already seated") == "confirmed"

    async with interleaved((pacing, "get_settings")):
        results = await asyncio.wait_for(
            asyncio.gather(
                _book(factory, pg_tenant, 4, "Adeyemi"), _book(factory, pg_tenant, 4, "Bianchi")
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert sorted(results) == ["confirmed", "refused:hospitality.slot_full"], results
    assert await _counters(pg_engine, pg_tenant) == (8, 2)


@pytest.mark.pg
async def test_a_cancel_racing_a_booking_never_tears_the_counter(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID
) -> None:
    """A four-top cancels at the same instant a six-top books the same slot. The counter must end
    at exactly six, whichever order the two land in.

    This is the read-modify-write window: both writers compute their new value from a counter they
    read, so an unserialized pair loses one of the two updates and the night is left holding either
    ten covers it does not have or none of the six it does. The row lock is what orders them, and
    the ``CHECK (covers_booked >= 0)`` pair is the backstop under it — but a backstop only turns a
    torn counter into a 500, so the exact end state is what has to be asserted.
    """
    factory = build_session_factory(pg_engine)
    assert await _book(factory, pg_tenant, 4, "Cancelling") == "confirmed"
    async with factory() as session:
        with tenant_context(pg_tenant):
            booked = (
                await session.execute(
                    select(TableReservation).where(
                        TableReservation.service_date == _service_date()
                    )
                )
            ).scalar_one()
            reservation_id = booked.id

    async def cancel() -> str:
        async with factory() as session:
            with tenant_context(pg_tenant):
                await run_in_uow(
                    session,
                    lambda: reservations.cancel_reservation(session, pg_tenant, reservation_id),
                )
            return "cancelled"

    async with interleaved((pacing, "get_settings"), (reservations, "get_reservation")):
        results = await asyncio.wait_for(
            asyncio.gather(_book(factory, pg_tenant, 6, "Arriving"), cancel()),
            timeout=GATE_TIMEOUT * 3,
        )

    assert results == ["confirmed", "cancelled"], results
    assert await _counters(pg_engine, pg_tenant) == (6, 1)

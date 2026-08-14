"""Menu availability (PLAN 19, spec Q2): STORED state with lazy expiry.

Availability is a row, never a derivation over stock. Q2 rejects derived-as-truth on four counts,
and the decisive one is the ETag trap: ``collection_etag`` (``core/conditional.py``) is
``COUNT(id), MAX(updated_at)``, so a derived answer would let the property's website hold a 304
asserting a sold-out dish is available. These tests pin the stored contract — absence means
available, expiry lapses on READ (Atlas has no scheduler), the countdown flips to 86 at zero, and
a whole menu reads in ONE query — plus the ETag consequence itself: a flip must move
``updated_at``, or the invalidation Q2 buys with stored state does not actually happen.

A menu item IS an ordinary inventory ``Item`` (no new entity), so items come from the inventory
factories and availability is written through the REAL service under a tenant context (D-025).
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import as_utc
from app.core.exceptions import ValidationFailedError
from app.core.models import utcnow
from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import AvailabilityState
from app.modules.hospitality.models import MenuAvailability
from app.modules.hospitality.service import availability
from tests.conftest import QueryCounter
from tests.modules.inventory.factories import InventorySetup

# ``menu_setup`` / ``dish_id`` moved to tests/modules/hospitality/conftest.py in Task 4, where
# test_tickets.py shares them (STRUCTURE §6: fixtures used by more than one module live in the
# package conftest).


async def _set(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, **kwargs: object
) -> None:
    # The commit stays INSIDE the tenant context: the D-007 before_flush listener stamps and
    # validates tenant_id at flush time, so a commit outside is a TenancyError (the factories'
    # convention too).
    with tenant_context(tenant_id):
        await availability.set_availability(session, tenant_id, item_id, **kwargs)  # type: ignore[arg-type]
        await session.commit()


async def _read(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, availability.MenuItemAvailability]:
    with tenant_context(tenant_id):
        return await availability.availability_for_items(session, tenant_id, item_ids)


async def _stored_updated_at(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> datetime:
    """The raw row's ``updated_at`` — what ``collection_etag``'s MAX() aggregates over."""
    session.expire_all()
    with tenant_context(tenant_id):
        stmt = select(MenuAvailability).where(MenuAvailability.item_id == item_id)
        return as_utc((await session.execute(stmt)).scalar_one().updated_at)


async def test_an_86_persists_and_reads_back(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.EIGHTY_SIXED,
        reason="out of feta",
    )
    got = await _read(db_session, tenant_a, [dish_id])
    assert got[dish_id].state == AvailabilityState.EIGHTY_SIXED
    assert got[dish_id].reason == "out of feta"


async def test_an_item_with_no_row_is_available(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """A dish nobody has ever 86'd is sellable: absence is not unavailability."""
    got = await _read(db_session, tenant_a, [dish_id])
    assert got[dish_id].state == AvailabilityState.AVAILABLE


async def test_an_expired_86_lapses_when_it_is_read(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """Atlas has no scheduler, so a time-boxed 86 must lapse on READ, not when a job runs."""
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.EIGHTY_SIXED,
        available_until=utcnow() - timedelta(minutes=1),
    )
    got = await _read(db_session, tenant_a, [dish_id])
    assert got[dish_id].state == AvailabilityState.AVAILABLE


async def test_an_unexpired_86_still_bites(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """The other half of lazy expiry: a window still open must NOT lapse."""
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.EIGHTY_SIXED,
        available_until=utcnow() + timedelta(hours=1),
    )
    got = await _read(db_session, tenant_a, [dish_id])
    assert got[dish_id].state == AvailabilityState.EIGHTY_SIXED


async def test_a_countdown_flips_to_86_at_zero(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.LIMITED,
        remaining_qty=Decimal(2),
    )
    with tenant_context(tenant_a):
        await availability.decrement_remaining(db_session, tenant_a, dish_id, Decimal(1))
        await db_session.commit()
    assert (await _read(db_session, tenant_a, [dish_id]))[dish_id].state == (
        AvailabilityState.LIMITED
    )

    with tenant_context(tenant_a):
        await availability.decrement_remaining(db_session, tenant_a, dish_id, Decimal(1))
        await db_session.commit()
    got = await _read(db_session, tenant_a, [dish_id])
    assert got[dish_id].state == AvailabilityState.EIGHTY_SIXED
    assert got[dish_id].remaining_qty == Decimal(0)


async def test_a_countdown_flip_moves_updated_at_so_the_menu_etag_invalidates(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """Q2's decisive argument, asserted rather than assumed: stored state only beats derived state
    because ``collection_etag``'s MAX(updated_at) MOVES when the last portion sells. If the flip
    left the stamp untouched, the website would keep receiving a 304 for a sold-out dish — the
    exact failure derivation was rejected for."""
    await _set(
        db_session,
        tenant_a,
        dish_id,
        state=AvailabilityState.LIMITED,
        remaining_qty=Decimal(1),
    )
    before = await _stored_updated_at(db_session, tenant_a, dish_id)

    with tenant_context(tenant_a):
        await availability.decrement_remaining(db_session, tenant_a, dish_id, Decimal(1))
        await db_session.commit()

    assert await _stored_updated_at(db_session, tenant_a, dish_id) > before


async def test_decrementing_an_item_with_no_countdown_does_nothing(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """The website decrements every ordered line; most dishes have no counter and must not be
    86'd by being ordered."""
    with tenant_context(tenant_a):
        await availability.decrement_remaining(db_session, tenant_a, dish_id, Decimal(3))
        await db_session.commit()
    assert (await _read(db_session, tenant_a, [dish_id]))[dish_id].state == (
        AvailabilityState.AVAILABLE
    )


async def test_clearing_an_86_makes_the_dish_sellable_again(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    await _set(db_session, tenant_a, dish_id, state=AvailabilityState.EIGHTY_SIXED)
    with tenant_context(tenant_a):
        await availability.clear_86(db_session, tenant_a, dish_id)
        await db_session.commit()
    assert (await _read(db_session, tenant_a, [dish_id]))[dish_id].state == (
        AvailabilityState.AVAILABLE
    )


async def test_a_limited_state_without_a_count_is_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """LIMITED is the countdown state; without a positive count there is nothing to count down and
    the dish would never flip."""
    with pytest.raises(ValidationFailedError), tenant_context(tenant_a):
        await availability.set_availability(
            db_session, tenant_a, dish_id, state=AvailabilityState.LIMITED
        )


async def test_availability_cannot_be_set_for_an_unknown_item(
    db_session: AsyncSession, tenant_a: uuid.UUID, menu_setup: InventorySetup
) -> None:
    """``item_id`` is an OPAQUE inventory id (D-029) with no FK, so existence is validated through
    ``inventory/queries`` — otherwise a typo writes an 86 nobody can ever clear."""
    with pytest.raises(ValidationFailedError), tenant_context(tenant_a):
        await availability.set_availability(
            db_session, tenant_a, uuid.uuid4(), state=AvailabilityState.EIGHTY_SIXED
        )


async def test_reading_a_whole_menus_availability_is_one_query(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    dish_id: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The guest read path must not scale with menu size (Q2: derived costs ~1,080 queries for a
    60-item menu, 360x over PERFORMANCE §2). One stored dish plus 59 with no row exercises both
    branches — the answer for every id comes out of the SAME statement."""
    item_ids = [dish_id, *(uuid.uuid4() for _ in range(59))]
    await _set(db_session, tenant_a, dish_id, state=AvailabilityState.EIGHTY_SIXED)

    with query_counter() as counted:
        got = await _read(db_session, tenant_a, item_ids)

    assert counted.count == 1, "\n".join(counted.statements)
    assert len(got) == 60
    assert got[dish_id].state == AvailabilityState.EIGHTY_SIXED
    assert got[item_ids[1]].state == AvailabilityState.AVAILABLE

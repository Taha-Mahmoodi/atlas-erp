"""Menu availability: stored state, lazy expiry (PLAN 19, spec Q2).

Four functions and one value object. Two writers (a human 86-ing a dish, a countdown decremented
by an order), one batched reader, and expiry that happens when somebody looks — Atlas has no
scheduler and Phase 19 does not add one.

THE EXPIRY RULE LIVES IN EXACTLY ONE PLACE (``_is_expired``) and is evaluated in PYTHON, not as a
``WHERE available_until > now()`` predicate. aiosqlite round-trips ``DateTime(timezone=True)`` as
NAIVE datetimes (see ``core/auth.as_utc``), which is why both existing credential-expiry checks in
core compare in Python too (``core/deps.py``, ``core/security_router.py``). It costs nothing here:
the read already loads the row, so the filter is a comprehension rather than a second statement,
and the countdown path reuses the same predicate instead of drifting from it.

Availability moves no stock and posts no journal, so nothing on this path publishes an event or
needs a uow of its own — the caller's transaction commits it. Ingredient depletion is a separate,
BACKGROUND concern (Q4, Task 5); this file must stay off the settle path entirely.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import as_utc
from app.core.exceptions import ValidationFailedError
from app.core.models import utcnow
from app.modules.hospitality.constants import AvailabilitySource, AvailabilityState
from app.modules.hospitality.models import MenuAvailability
from app.modules.inventory import queries as inventory_queries


@dataclass(frozen=True)
class MenuItemAvailability:
    """What one item's availability resolves to RIGHT NOW — the flat, already-expired-out answer
    the website and the staff UI both read. Frozen and detached from the ORM so a caller can hold
    it across a commit (the sales ``AvailabilityResult`` precedent)."""

    state: AvailabilityState
    remaining_qty: Decimal | None = None
    available_until: datetime | None = None
    reason: str | None = None
    source: AvailabilitySource | None = None


# The answer for an item with no override row, and for one whose 86 has lapsed. Shared instance:
# the dataclass is frozen, and a 60-item menu should not allocate 60 identical objects.
_AVAILABLE = MenuItemAvailability(state=AvailabilityState.AVAILABLE)


def _is_expired(row: MenuAvailability, now: datetime) -> bool:
    """Whether a time-boxed override has lapsed. ``as_utc`` normalizes the SQLite naive round-trip
    before comparing (core/auth)."""
    return row.available_until is not None and as_utc(row.available_until) <= now


def lapsed_count_expr(now: datetime | None = None) -> ColumnElement[int]:
    """``_is_expired`` as an AGGREGATE — how many stored overrides have already lapsed at ``now``.

    The ONE place this module speaks about expiry in SQL, and it exists for the conditional GET,
    not for filtering. ``collection_etag`` is ``COUNT(id), MAX(updated_at)``, and TIME PASSING IS
    NOT A WRITE: when a snooze lapses at 22:00 the row is untouched, so both aggregates hold still
    while ``resolve`` starts answering AVAILABLE — and the website revalidating at 22:01 is handed
    a 304 that keeps the dish sold out for every guest. Folding this count into the validator is
    what makes the lapse a version change; it is monotone in time (a lapsed row never un-lapses
    without a write, which moves ``MAX(updated_at)`` anyway), so each staggered boundary moves the
    tag exactly once. Selected in the same aggregate statement, so the read still costs one query.

    The docstring at the top of this file says the expiry rule is evaluated in PYTHON, and that
    still holds for every row the reader RESOLVES — this is a COUNT, never a row filter, so a
    lapsed row is still returned to ``resolve`` and still tells the reader the dish is back on.
    The comparison is safe in SQL because both sides are UTC: SQLAlchemy's SQLite bind processor
    formats a bound aware datetime with the same format it stored the column with, and PostgreSQL
    compares ``timestamptz`` properly. ``test_availability_etag`` pins the two spellings agreeing.
    """
    return func.count(case((MenuAvailability.available_until <= (now or utcnow()), 1)))


def resolve(row: MenuAvailability, now: datetime | None = None) -> MenuItemAvailability:
    """What ONE stored row means right now, expiry applied — a lapsed override reads AVAILABLE.

    Public because the website's availability page reads the stored rows directly (it publishes the
    override board, not a per-item lookup) and must apply the SAME expiry rule; keeping one resolver
    is what stops a SQL predicate and a Python predicate drifting apart.
    """
    if now is None:
        now = utcnow()
    if _is_expired(row, now):
        return _AVAILABLE
    return MenuItemAvailability(
        state=AvailabilityState(row.state),
        remaining_qty=None if row.remaining_qty is None else Decimal(row.remaining_qty),
        available_until=None if row.available_until is None else as_utc(row.available_until),
        reason=row.reason,
        source=AvailabilitySource(row.source),
    )


async def _locked_row(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> MenuAvailability | None:
    """The item's override row FOR UPDATE, or None. The row lock serializes two concurrent orders
    racing the last portion of a countdown on Postgres; SQLite omits it as a no-op (the
    ``inv_stock_quants`` precedent, ``inventory/service/stock_quants.py``).

    Deliberately does NOT filter on expiry: a lapsed row is still THE row for this item, and a
    write must overwrite it rather than insert a duplicate the unique constraint would reject.
    """
    stmt = (
        select(MenuAvailability)
        .where(MenuAvailability.tenant_id == tenant_id, MenuAvailability.item_id == item_id)
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def set_availability(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    state: AvailabilityState,
    remaining_qty: Decimal | None = None,
    available_until: datetime | None = None,
    reason: str | None = None,
    source: AvailabilitySource = AvailabilitySource.MANUAL,
) -> MenuItemAvailability:
    """Write the stored answer for one item, replacing whatever was there.

    ``LIMITED`` requires a positive ``remaining_qty`` — it IS the countdown state, and without a
    count there is nothing to count down and the dish would never flip. Every other state clears
    the counter, so an 86 followed by a countdown cannot inherit a stale number.
    """
    if state == AvailabilityState.LIMITED and (remaining_qty is None or remaining_qty <= 0):
        raise ValidationFailedError(
            message="A LIMITED menu item needs a positive remaining quantity",
            code="hospitality.countdown_required",
            details={"item_id": str(item_id)},
        )
    if not await inventory_queries.item_exists(session, tenant_id, item_id):
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="hospitality.item_not_found",
            details={"item_id": str(item_id)},
        )

    row = await _locked_row(session, tenant_id, item_id)
    if row is None:
        row = MenuAvailability(tenant_id=tenant_id, item_id=item_id)
        session.add(row)
    row.state = state.value
    row.remaining_qty = remaining_qty if state == AvailabilityState.LIMITED else None
    row.available_until = available_until
    row.reason = reason
    row.source = source.value
    return resolve(row, utcnow())


async def clear_86(session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """Put the dish back on the menu by DELETING its override row.

    Absence is the canonical AVAILABLE (see ``availability_for_items``), so clearing removes the
    override rather than storing a second spelling of "nothing is wrong" — which also keeps the
    table at the size of the overrides in force, not of everything ever 86'd. Deleting moves
    ``collection_etag``'s ``COUNT(id)``, so the website's cached menu still invalidates. A no-op
    if the item was never 86'd.
    """
    row = await _locked_row(session, tenant_id, item_id)
    if row is not None:
        await session.delete(row)


async def decrement_remaining(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, quantity: Decimal
) -> None:
    """Burn ``quantity`` off a countdown, flipping the item to EIGHTY_SIXED at zero.

    This is the ONLY automatic 86 in Phase 19 — a per-item counter, exactly what Toast's and
    Square's auto-86 is, and NOT a recipe explosion (Q2: a BOM-derived answer over-reports on
    shared ingredients and cannot be the guest-facing number). Recipe math stays advisory, in the
    staff-facing "at risk" list.

    A no-op unless the item has a live countdown: most dishes have no counter and must not be 86'd
    merely by being ordered, and a LAPSED row already reads AVAILABLE, so decrementing it would
    resurrect an override the read path has stopped honouring.
    """
    row = await _locked_row(session, tenant_id, item_id)
    now = utcnow()
    if row is None or row.remaining_qty is None or _is_expired(row, now):
        return
    remaining = Decimal(row.remaining_qty) - quantity
    row.remaining_qty = max(remaining, Decimal(0))
    if row.remaining_qty <= 0:
        row.state = AvailabilityState.EIGHTY_SIXED.value
        row.source = AvailabilitySource.AUTO.value


async def availability_for_items(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, MenuItemAvailability]:
    """The stored answer for every requested item, in ONE query, expiry already applied.

    Every id gets an entry: an item with no row — or with one that has lapsed — resolves to
    AVAILABLE, because absence of an override is not unavailability. The caller bounds the id list
    (it is a page of the menu, D-014 caps a page at 200), so the ``IN`` clause stays small; an
    empty list short-circuits without touching the database.
    """
    ids = list(dict.fromkeys(item_ids))
    if not ids:
        return {}
    stmt = select(MenuAvailability).where(
        MenuAvailability.tenant_id == tenant_id, MenuAvailability.item_id.in_(ids)
    )
    rows = (await session.execute(stmt)).scalars().all()
    now = utcnow()
    resolved: dict[uuid.UUID, MenuItemAvailability] = dict.fromkeys(ids, _AVAILABLE)
    resolved.update({row.item_id: resolve(row, now) for row in rows})
    return resolved

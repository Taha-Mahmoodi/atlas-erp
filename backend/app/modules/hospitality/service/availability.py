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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, and_, case, func, literal, null, or_, select, update
from sqlalchemy.exc import IntegrityError
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


async def _locked_rows(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: Iterable[uuid.UUID]
) -> list[MenuAvailability]:
    """Whichever of ``item_ids`` have an override row, FOR UPDATE. The row lock serializes two
    concurrent orders racing the last portion of a countdown on Postgres; SQLite omits it as a
    no-op (the ``inv_stock_quants`` precedent, ``inventory/service/stock_quants.py``).

    ONE locked read for every writer in this module, singular and batched alike, so the lock-order
    rule below cannot hold for one write path and not the other.

    A stable lock order. Two tickets sharing two countdown dishes used to take the row locks in
    their own line order, which is the classic deadlock shape; ordering the read makes the common
    index-scan plan acquire them in the same sequence for both.

    Deliberately does NOT filter on expiry: a lapsed row is still THE row for this item, and a
    write must overwrite it rather than insert a duplicate the unique constraint would reject.
    """
    stmt = (
        select(MenuAvailability)
        .where(
            MenuAvailability.tenant_id == tenant_id,
            MenuAvailability.item_id.in_(list(item_ids)),
        )
        .order_by(MenuAvailability.item_id)
        .with_for_update()
    )
    return list((await session.execute(stmt)).scalars().all())


async def _locked_row(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> MenuAvailability | None:
    """The item's override row FOR UPDATE, or None — the one-item spelling of ``_locked_rows``."""
    rows = await _locked_rows(session, tenant_id, [item_id])
    return rows[0] if rows else None


async def _insert_or_reload(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> MenuAvailability:
    """Create the item's override row, or take over the one another writer just committed.

    ``_locked_row`` locks NOTHING when the row does not exist — there is no row to lock — so the
    bar terminal and the pass 86-ing the same dish in the same second both read None and both
    INSERT, and ``uq_hsp_menu_availability_tenant_id_item_id`` rejects the loser with an
    IntegrityError the API surfaces as a 500. The SAVEPOINT turns that into the answer both
    callers actually asked for: roll the failed insert back, re-read the winner's row under the
    lock, and let ``set_availability`` overwrite it. Last write wins, which is the same contract
    the PUT already has for an item whose row exists.

    Portable by construction (D-003): a savepoint plus a re-read is the same on SQLite and
    PostgreSQL, unlike a dialect-specific ``ON CONFLICT`` upsert — and the ORM write is what moves
    ``updated_at`` for ``collection_etag``, which a bulk upsert statement would bypass.
    """
    savepoint = await session.begin_nested()
    row = MenuAvailability(tenant_id=tenant_id, item_id=item_id)
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await savepoint.rollback()
        winner = await _locked_row(session, tenant_id, item_id)
        if winner is None:
            # Not the uniqueness conflict this exists for (a FK or CHECK failure): re-raise it.
            raise
        return winner
    return row


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

    row = await _locked_row(session, tenant_id, item_id) or await _insert_or_reload(
        session, tenant_id, item_id
    )
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


async def _burn_all(
    session: AsyncSession, burns: Sequence[tuple[MenuAvailability, Decimal]]
) -> None:
    """Write every countdown's new value in ONE statement, each row's counter the burn was
    COMPUTED FROM pinned in the WHERE clause. The only write in this module that is not a plain
    ORM mutation, for two reasons.

    THE PIN. A burn is decided from a read and applied afterwards, and ``clear_86`` DELETES the
    row — the chef finding another tray while the ticket is firing. Mutating the loaded row
    instead leaves the write to a later autoflush (in ``fire_ticket`` that is the ticket's own
    transition, three statements downstream), and the ORM's UPDATE for a row somebody deleted in
    between matches zero rows and raises ``StaleDataError``: an HTTP 500 on the fire, with a table
    sitting waiting to eat. The row lock does not prevent it wherever ``with_for_update`` is a
    no-op — SQLite, D-003, where every test and the local demo run — because there the DELETE
    simply commits inside the window. Pinning ``(id, remaining_qty)`` per row makes the write
    self-checking on EVERY engine instead of trusting a lock only one of them takes: a burn lands
    only while its countdown still holds exactly what was counted, and matching nothing means
    another writer removed or moved that countdown in the window. There is then nothing left to
    burn — the dish is back on the menu, or its counter is already somebody else's — so the burn
    is dropped rather than blindly restated over the winner, which is what would tear the row into
    LIMITED with nothing left: a state the menu reads to a guest as orderable while the counter
    says there is none. On PostgreSQL the row lock makes the zero-match branch unreachable (the
    deleter blocks on it until this transaction commits, which a probe pins directly); the pin is
    what gives SQLite the same two outcomes instead of a 500.

    ONE STATEMENT. Firing burns a countdown per LINE, and a per-row spelling of this write is one
    UPDATE per line on the request a guest waits on — the N+1 shape PERFORMANCE §2 bans, caught by
    ``test_firing_does_not_scale_with_countdown_lines`` the first time this function was written
    per-row. The per-row pins become OR'd ``(id, counter)`` pairs and the per-row values CASE arms
    on ``id``, so a 24-line ticket and a 2-line one cost the same one statement. The statement is
    ORM-enabled, so D-007's do_orm_execute listener injects the tenant predicate exactly as it
    does for the locked read; ``synchronize_session`` cannot evaluate these CASE values, so it is
    off and each loaded row is expired instead — nothing on the fire path reads them again, so the
    expiry costs no query until somebody does.

    ``updated_at`` still moves: ``TimestampMixin``'s Python ``onupdate`` fires for a Core UPDATE
    exactly as it does for a flush (models.py #34), so ``collection_etag`` still invalidates the
    website's cached menu when a countdown auto-86s a dish.
    """
    if not burns:
        return
    values: dict[str, object] = {
        # ``literal`` with the COLUMN'S type: a bare Decimal in a CASE arm has no column context,
        # so it binds through the default Numeric — skipping QuantityType's micro-unit scaling on
        # SQLite and landing as value/10^6. Invisible on Postgres, where NUMERIC(18,6) binds plain.
        "remaining_qty": case(
            *[
                (
                    MenuAvailability.id == row.id,
                    literal(remaining, MenuAvailability.remaining_qty.type),
                )
                for row, remaining in burns
            ]
        )
    }
    if zero_ids := [row.id for row, remaining in burns if remaining <= 0]:
        # The time box came with the COUNTDOWN ("twenty portions, until 22:00"); it says nothing
        # about the 86 that replaces it. Left in place it lapses at 22:00 and ``resolve`` hands the
        # website AVAILABLE for a dish with nothing behind it — and nothing sweeps expired rows, so
        # it stays wrongly sellable until a human notices.
        hit_zero = MenuAvailability.id.in_(zero_ids)
        values |= {
            "state": case(
                (hit_zero, AvailabilityState.EIGHTY_SIXED.value), else_=MenuAvailability.state
            ),
            "source": case(
                (hit_zero, AvailabilitySource.AUTO.value), else_=MenuAvailability.source
            ),
            "available_until": case((hit_zero, null()), else_=MenuAvailability.available_until),
        }
    await session.execute(
        update(MenuAvailability)
        .where(
            or_(
                *[
                    and_(
                        MenuAvailability.id == row.id,
                        MenuAvailability.remaining_qty == row.remaining_qty,
                    )
                    for row, _ in burns
                ]
            )
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    for row, _ in burns:
        session.expire(row)


async def decrement_remaining(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, quantity: Decimal
) -> None:
    """Burn ``quantity`` off ONE item's countdown — the single-item spelling of
    :func:`decrement_remaining_many`, which is where the rule lives."""
    await decrement_remaining_many(session, tenant_id, {item_id: quantity})


async def decrement_remaining_many(
    session: AsyncSession, tenant_id: uuid.UUID, quantities: Mapping[uuid.UUID, Decimal]
) -> None:
    """Burn a whole ticket's countdowns in ONE locked read, flipping each item to EIGHTY_SIXED at
    zero.

    This is the ONLY automatic 86 in Phase 19 — a per-item counter, exactly what Toast's and
    Square's auto-86 is, and NOT a recipe explosion (Q2: a BOM-derived answer over-reports on
    shared ingredients and cannot be the guest-facing number). Recipe math stays advisory, in the
    staff-facing "at risk" list.

    BATCHED because the caller is a ticket, not an item. Firing burns one countdown per LINE, so a
    per-item locked read cost two statements a line (the SELECT, plus the autoflushed UPDATE of the
    previous one) on the request a guest waits on — 58 statements for a 24-line ticket against 14
    for a 2-line one, and neither ``OrderTicketCreate`` nor ``WebsiteOrderCreate`` caps ``lines``.
    The caller sums per item first, which also collapses two lines of the same dish into one burn.

    A no-op unless the item has a live countdown: most dishes have no counter and must not be 86'd
    merely by being ordered, and a LAPSED row already reads AVAILABLE, so decrementing it would
    resurrect an override the read path has stopped honouring. An item with no row at all is simply
    absent from the result set.

    REFUSES rather than clamping when a counter cannot cover its burn, and that refusal is what
    makes the row lock worth taking. Two fires reading LIMITED with one portion left serialize
    here; the loser re-reads the counter UNDER the lock and finds it at zero, so clamping at zero
    would let both tickets fire and sell the last portion twice — the lock would have bought
    nothing. The same guard catches the un-raced spelling: six portions left and an eight-top
    ordering eight. Raised BEFORE anything is mutated, so ``fire_ticket``'s promise that a refusal
    leaves the ticket OPEN holds without depending on the transaction rollback.
    """
    if not quantities:
        return
    now = utcnow()
    burns: list[tuple[MenuAvailability, Decimal]] = []
    exhausted: list[str] = []
    for row in await _locked_rows(session, tenant_id, list(quantities)):
        if row.remaining_qty is None or _is_expired(row, now):
            continue
        remaining = Decimal(row.remaining_qty) - quantities[row.item_id]
        if remaining < 0:
            exhausted.append(str(row.item_id))
        else:
            burns.append((row, remaining))
    if exhausted:
        raise ValidationFailedError(
            message="An ordered item has fewer portions left than the order asks for",
            code="hospitality.item_unavailable",
            details={"item_ids": sorted(exhausted)},
        )
    await _burn_all(session, burns)


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

"""D-012 gapless per-tenant numbering, proven against the real session/db on the migrated
template (D-025 — real commits work, so rollback-returns-the-number is testable as designed).

Covers: sequential claims format prefix+year+padding; year reset restarts at 1 with the new
year segment; the atomic UPDATE...RETURNING claim never hands out a duplicate (many claims
in one tenant, plus two concurrent sessions); a rolled-back claim returns the number to the
pool so the next committed claim reuses it (gaplessness for committed documents — the D-012
claim-timing rule); tenants with the same sequence name keep independent counters;
ensure_sequence is idempotent.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.db import build_session_factory
from app.core.exceptions import NotFoundError
from app.core.numbering import (
    NumberSequence,
    NumberSequenceCounter,
    claim_number,
    ensure_sequence,
)
from app.core.tenancy import tenant_context

SequenceFactory = Callable[..., Awaitable[None]]


async def _claim(
    session: AsyncSession, tenant_id: uuid.UUID, name: str, year: int
) -> str:
    with tenant_context(tenant_id):
        return await claim_number(
            session, tenant_id, name, on_date=date(year, 6, 1)
        )


# --- sequential claim: prefix + year + padding ---------------------------------


async def test_sequential_claims_increment_with_prefix_year_and_padding(
    db_session: AsyncSession, tenant_a: uuid.UUID, make_sequence: SequenceFactory
) -> None:
    await make_sequence(tenant_a, name="finance.invoice", prefix="INV", padding=5)

    first = await _claim(db_session, tenant_a, "finance.invoice", 2026)
    second = await _claim(db_session, tenant_a, "finance.invoice", 2026)
    third = await _claim(db_session, tenant_a, "finance.invoice", 2026)

    assert first == "INV-2026-00001"
    assert second == "INV-2026-00002"
    assert third == "INV-2026-00003"


async def test_non_year_resetting_sequence_omits_the_year_segment(
    db_session: AsyncSession, tenant_a: uuid.UUID, make_sequence: SequenceFactory
) -> None:
    await make_sequence(
        tenant_a, name="sales.order", prefix="SO", padding=4, year_reset=False
    )

    first = await _claim(db_session, tenant_a, "sales.order", 2026)
    second = await _claim(db_session, tenant_a, "sales.order", 2026)

    assert first == "SO-0001"
    assert second == "SO-0002"


# --- year reset: a new year restarts at 1 with the new year segment ------------


async def test_year_reset_restarts_counter_in_a_new_year(
    db_session: AsyncSession, tenant_a: uuid.UUID, make_sequence: SequenceFactory
) -> None:
    await make_sequence(tenant_a, name="finance.invoice", prefix="INV", padding=5)

    in_2026_a = await _claim(db_session, tenant_a, "finance.invoice", 2026)
    in_2026_b = await _claim(db_session, tenant_a, "finance.invoice", 2026)
    in_2027_a = await _claim(db_session, tenant_a, "finance.invoice", 2027)
    in_2027_b = await _claim(db_session, tenant_a, "finance.invoice", 2027)

    assert in_2026_a == "INV-2026-00001"
    assert in_2026_b == "INV-2026-00002"
    # New year: counter restarts at 1 and the year segment advances.
    assert in_2027_a == "INV-2027-00001"
    assert in_2027_b == "INV-2027-00002"


# --- atomicity: no duplicate numbers ever -------------------------------------


async def test_many_claims_never_duplicate_a_number(
    db_session: AsyncSession, tenant_a: uuid.UUID, make_sequence: SequenceFactory
) -> None:
    await make_sequence(tenant_a, name="finance.invoice", prefix="INV", padding=5)

    claimed = [
        await _claim(db_session, tenant_a, "finance.invoice", 2026) for _ in range(50)
    ]

    assert len(set(claimed)) == 50
    assert claimed[0] == "INV-2026-00001"
    assert claimed[-1] == "INV-2026-00050"


async def test_two_sessions_claiming_never_return_the_same_number(
    db_engine: AsyncEngine, tenant_a: uuid.UUID, make_sequence: SequenceFactory
) -> None:
    # make_sequence committed the sequence on the shared db_session; two fresh sessions on
    # the SAME engine now claim and commit independently. The atomic UPDATE...RETURNING (row
    # lock; SQLite's single-writer lock serializes) guarantees distinct values across both.
    await make_sequence(tenant_a, name="finance.invoice", prefix="INV", padding=5)
    factory = build_session_factory(db_engine)

    claimed: list[str] = []
    for _ in range(10):
        async with factory() as session_one:
            claimed.append(await _claim(session_one, tenant_a, "finance.invoice", 2026))
            await session_one.commit()
        async with factory() as session_two:
            claimed.append(await _claim(session_two, tenant_a, "finance.invoice", 2026))
            await session_two.commit()

    assert len(set(claimed)) == len(claimed) == 20


# --- rollback returns the number to the pool (gaplessness for committed docs) --


async def test_rolled_back_claim_is_reused_by_the_next_committed_claim(
    db_engine: AsyncEngine, tenant_a: uuid.UUID, make_sequence: SequenceFactory
) -> None:
    await make_sequence(tenant_a, name="finance.invoice", prefix="INV", padding=5)
    factory = build_session_factory(db_engine)

    # Claim inside a transaction that ROLLS BACK — the counter increment rolls back with it.
    async with factory() as rolling_back:
        burned = await _claim(rolling_back, tenant_a, "finance.invoice", 2026)
        assert burned == "INV-2026-00001"
        await rolling_back.rollback()

    # The next COMMITTED claim reuses the very value the rolled-back transaction "burned":
    # gaplessness for committed documents falls out of ACID (D-012 claim-timing rule).
    async with factory() as committing:
        reused = await _claim(committing, tenant_a, "finance.invoice", 2026)
        await committing.commit()

    assert reused == "INV-2026-00001"


# --- tenant isolation: independent counters under the same sequence name -------


async def test_two_tenants_have_independent_counters_for_the_same_name(
    db_engine: AsyncEngine,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    make_sequence: SequenceFactory,
) -> None:
    await make_sequence(tenant_a, name="finance.invoice", prefix="INV", padding=5)
    await make_sequence(tenant_b, name="finance.invoice", prefix="INV", padding=5)
    factory = build_session_factory(db_engine)

    async with factory() as session:
        a_first = await _claim(session, tenant_a, "finance.invoice", 2026)
        a_second = await _claim(session, tenant_a, "finance.invoice", 2026)
        b_first = await _claim(session, tenant_b, "finance.invoice", 2026)
        await session.commit()

    # Tenant B's counter is untouched by tenant A's two claims.
    assert a_first == "INV-2026-00001"
    assert a_second == "INV-2026-00002"
    assert b_first == "INV-2026-00001"


# --- ensure_sequence is idempotent --------------------------------------------


async def test_ensure_sequence_is_idempotent(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        first = await ensure_sequence(
            db_session, tenant_a, "finance.invoice", "INV", 5, True
        )
        # A second call with the SAME name must not create a duplicate or reset the counter.
        await claim_number(
            db_session, tenant_a, "finance.invoice", on_date=date(2026, 6, 1)
        )
        second = await ensure_sequence(
            db_session, tenant_a, "finance.invoice", "INV", 5, True
        )
        await db_session.commit()

        rows = (
            await db_session.execute(
                select(NumberSequence).where(NumberSequence.name == "finance.invoice")
            )
        ).scalars().all()
        counters = (
            await db_session.execute(
                select(NumberSequenceCounter).where(
                    NumberSequenceCounter.sequence_id == first.id
                )
            )
        ).scalars().all()

    assert first.id == second.id
    assert len(rows) == 1
    # The counter advanced by the one claim between the two ensure calls (not reset to 1).
    assert len(counters) == 1
    assert counters[0].next_value == 2


async def test_claiming_a_missing_sequence_raises_not_found(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await claim_number(db_session, tenant_a, "does.not.exist", on_date=date(2026, 6, 1))


# --- issue #209: a backdated claim must not disturb the current year's counter --


async def test_a_backdated_claim_keeps_its_own_year_series(
    db_session: AsyncSession, tenant_a: uuid.UUID, make_sequence: SequenceFactory
) -> None:
    """The defect this test pins: a claim dated in a PAST year used to reset the ONE counter to
    1 and stamp it with that past year, so the next current-year claim re-handed a number that
    was already on a document — a duplicate the document table's unique index turned into a 500,
    permanently. Each year owning its own counter is what makes backdating safe."""
    await make_sequence(tenant_a, name="hospitality.order_ticket", prefix="TKT", padding=6)

    live = [await _claim(db_session, tenant_a, "hospitality.order_ticket", 2026) for _ in range(3)]
    backdated = await _claim(db_session, tenant_a, "hospitality.order_ticket", 2022)
    after = await _claim(db_session, tenant_a, "hospitality.order_ticket", 2026)

    assert live == ["TKT-2026-000001", "TKT-2026-000002", "TKT-2026-000003"]
    # The old year gets its own series starting at 1 — it does not borrow the live counter.
    assert backdated == "TKT-2022-000001"
    # And the live year carries on exactly where it was: no reset, no duplicate.
    assert after == "TKT-2026-000004"


async def test_backdated_claims_continue_their_own_year(
    db_session: AsyncSession, tenant_a: uuid.UUID, make_sequence: SequenceFactory
) -> None:
    """A second document entered for the same past year continues that year's series rather than
    restarting it — the counter is per (sequence, year), not a stamp that flips back and forth."""
    await make_sequence(tenant_a, name="finance.invoice", prefix="INV", padding=5)

    await _claim(db_session, tenant_a, "finance.invoice", 2026)
    first_2025 = await _claim(db_session, tenant_a, "finance.invoice", 2025)
    await _claim(db_session, tenant_a, "finance.invoice", 2026)
    second_2025 = await _claim(db_session, tenant_a, "finance.invoice", 2025)

    assert first_2025 == "INV-2025-00001"
    assert second_2025 == "INV-2025-00002"

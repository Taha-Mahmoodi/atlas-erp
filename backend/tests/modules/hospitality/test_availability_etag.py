"""Adversarial review of the availability VALIDATOR (PLAN 19 Task 7, spec Q2/Q6).

``test_website_api.py`` proves the validator moves when a human 86s a dish. This file attacks the
same validator from every other direction, because ``collection_etag`` is ``COUNT(id),
MAX(updated_at)`` and that pair is blind to anything that is not an INSERT, an UPDATE or a DELETE.

**The hole this file was written to find.** Task 3 evaluates ``available_until`` LAZILY, on read.
Time passing is not a write: when a time-boxed 86 lapses at 22:00 the row is untouched, so COUNT
does not move and MAX(updated_at) does not move — while the BODY changes, because ``resolve``
starts returning AVAILABLE for that row. A website revalidating at 22:01 is handed a 304 and keeps
serving the dish as 86'd. That is Q2's ETag trap reintroduced through the clock instead of through
stock, and it is what ``test_a_lapsing_86_moves_the_validator`` pins.

The clock is advanced two ways, deliberately. ``_lapse`` moves the boundary into the past while
PRESERVING ``updated_at``, which is byte-for-byte the state real time produces and is deterministic;
``test_..._on_the_real_clock`` does the same thing with a real one-second boundary and a real sleep,
so the finding cannot be dismissed as an artefact of the simulation.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import utcnow
from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import AvailabilityState
from app.modules.hospitality.models import MenuAvailability
from app.modules.hospitality.service import availability
from tests.conftest import QueryCounter
from tests.modules.hospitality.conftest import WebsiteApi
from tests.modules.hospitality.factories import (
    HospitalityPrincipal,
    build_dish,
    build_menu_price,
    mint_website_key,
)

MENU_URL = "/api/v1/hospitality/menu"
AVAILABILITY_URL = "/api/v1/hospitality/menu/availability"


async def _etag(website_api: WebsiteApi) -> str:
    response = await website_api.client.get(AVAILABILITY_URL)
    assert response.status_code == 200, response.text
    return response.headers["etag"]


async def _86(
    website_api: WebsiteApi,
    session: AsyncSession,
    item_id: uuid.UUID,
    **kwargs: object,
) -> None:
    with tenant_context(website_api.tenant_id):
        await availability.set_availability(
            session,
            website_api.tenant_id,
            item_id,
            state=AvailabilityState.EIGHTY_SIXED,
            **kwargs,  # type: ignore[arg-type]
        )
        await session.commit()


async def _lapse(session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """Advance the clock past this row's ``available_until``, WITHOUT touching ``updated_at``.

    Real time does exactly this to the validator's inputs: the row is not rewritten, so COUNT(id)
    is unchanged and MAX(updated_at) is unchanged, while ``resolve`` flips the row to AVAILABLE.
    ``updated_at`` is passed explicitly so TimestampMixin's ``onupdate`` cannot fire and hide the
    bug behind a write that would never happen in production.
    """
    with tenant_context(tenant_id):
        stmt = select(MenuAvailability).where(MenuAvailability.item_id == item_id)
        row = (await session.execute(stmt)).scalar_one()
        await session.execute(
            update(MenuAvailability)
            .where(MenuAvailability.id == row.id)
            .values(available_until=utcnow() - timedelta(seconds=1), updated_at=row.updated_at)
        )
        await session.commit()
        session.expire_all()


def _state_of(body: dict[str, object], item_id: uuid.UUID) -> str:
    rows = {row["item_id"]: row for row in body["items"]}  # type: ignore[union-attr]
    return rows[str(item_id)]["state"]


# --- The known suspected flaw: time passing is not a write --------------------


async def test_a_lapsing_86_moves_the_validator(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """A time-boxed 86 that lapses MUST bust the validator.

    Without this the dish is back on the menu server-side and gone from it for every guest, for as
    long as the website keeps revalidating — ``Cache-Control: no-cache, must-revalidate`` does not
    save it, because the client dutifully revalidates and is dutifully told 304.
    """
    pasta = website_api.kitchen.dishes["PASTA"]
    await _86(website_api, db_session, pasta, available_until=utcnow() + timedelta(hours=2))

    live = await website_api.client.get(AVAILABILITY_URL)
    assert _state_of(live.json(), pasta) == AvailabilityState.EIGHTY_SIXED.value
    before = live.headers["etag"]

    await _lapse(db_session, website_api.tenant_id, pasta)

    revalidated = await website_api.client.get(
        AVAILABILITY_URL, headers={"If-None-Match": before}
    )
    assert revalidated.status_code == 200, (
        "the 86 has lapsed and the dish reads AVAILABLE server-side, but the validator did not "
        "move, so the website is told 304 and keeps the guest-facing menu sold out"
    )
    assert _state_of(revalidated.json(), pasta) == AvailabilityState.AVAILABLE.value
    assert revalidated.headers["etag"] != before


async def test_a_lapsing_86_moves_the_validator_on_the_real_clock(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """The same thing with a real boundary and a real sleep — no simulation anywhere."""
    beer = website_api.kitchen.dishes["BEER"]
    await _86(website_api, db_session, beer, available_until=utcnow() + timedelta(seconds=1))

    live = await website_api.client.get(AVAILABILITY_URL)
    assert _state_of(live.json(), beer) == AvailabilityState.EIGHTY_SIXED.value, (
        "the 86 lapsed before the first read even ran; widen the boundary"
    )
    before = live.headers["etag"]

    await asyncio.sleep(1.2)

    revalidated = await website_api.client.get(
        AVAILABILITY_URL, headers={"If-None-Match": before}
    )
    assert revalidated.status_code == 200, "a lapsed 86 must not be served as 304"
    assert _state_of(revalidated.json(), beer) == AvailabilityState.AVAILABLE.value


async def test_a_second_boundary_moves_the_validator_again(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """Two staggered snoozes lapse at two different times, and BOTH must invalidate.

    A validator that merely notices "some boundary has passed" would move once at 22:00 and then
    sit still through the 23:00 one — the second dish would stay sold out on the website forever.
    """
    pasta, beer = website_api.kitchen.dishes["PASTA"], website_api.kitchen.dishes["BEER"]
    await _86(website_api, db_session, pasta, available_until=utcnow() + timedelta(hours=1))
    await _86(website_api, db_session, beer, available_until=utcnow() + timedelta(hours=2))
    both_live = await _etag(website_api)

    await _lapse(db_session, website_api.tenant_id, pasta)
    one_lapsed = await _etag(website_api)
    assert one_lapsed != both_live

    await _lapse(db_session, website_api.tenant_id, beer)
    both_lapsed = await _etag(website_api)
    assert both_lapsed != one_lapsed, (
        "the second boundary lapsed without moving the validator — the website keeps the second "
        "dish sold out"
    )
    assert both_lapsed != both_live


# --- The writes that must move it ---------------------------------------------


async def test_un_86ing_moves_the_validator(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """``clear_86`` DELETES the row, so the dish disappears from the board entirely."""
    pasta = website_api.kitchen.dishes["PASTA"]
    await _86(website_api, db_session, pasta)
    sold_out = await _etag(website_api)

    with tenant_context(website_api.tenant_id):
        await availability.clear_86(db_session, website_api.tenant_id, pasta)
        await db_session.commit()

    back_on = await website_api.client.get(AVAILABILITY_URL, headers={"If-None-Match": sold_out})
    assert back_on.status_code == 200
    assert back_on.json()["items"] == []


async def test_a_countdown_decrement_moves_the_validator(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """A countdown ticking 5 -> 4 changes no state and no row count — only ``remaining_qty``. The
    guest-facing number changed, so the validator has to."""
    pasta = website_api.kitchen.dishes["PASTA"]
    with tenant_context(website_api.tenant_id):
        await availability.set_availability(
            db_session,
            website_api.tenant_id,
            pasta,
            state=AvailabilityState.LIMITED,
            remaining_qty=Decimal(5),
        )
        await db_session.commit()
    five_left = await _etag(website_api)

    with tenant_context(website_api.tenant_id):
        await availability.decrement_remaining(
            db_session, website_api.tenant_id, pasta, Decimal(1)
        )
        await db_session.commit()

    after = await website_api.client.get(AVAILABILITY_URL, headers={"If-None-Match": five_left})
    assert after.status_code == 200, "a countdown decrement was served as 304"
    rows = {row["item_id"]: row for row in after.json()["items"]}
    assert Decimal(rows[str(pasta)]["remaining_qty"]) == Decimal(4)


async def test_the_countdown_hitting_zero_moves_the_validator(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """The auto-86 — the one flip Q2 says a derived validator would miss completely."""
    pasta = website_api.kitchen.dishes["PASTA"]
    with tenant_context(website_api.tenant_id):
        await availability.set_availability(
            db_session,
            website_api.tenant_id,
            pasta,
            state=AvailabilityState.LIMITED,
            remaining_qty=Decimal(1),
        )
        await db_session.commit()
    last_portion = await _etag(website_api)

    with tenant_context(website_api.tenant_id):
        await availability.decrement_remaining(
            db_session, website_api.tenant_id, pasta, Decimal(1)
        )
        await db_session.commit()

    after = await website_api.client.get(AVAILABILITY_URL, headers={"If-None-Match": last_portion})
    assert after.status_code == 200
    assert _state_of(after.json(), pasta) == AvailabilityState.EIGHTY_SIXED.value


# --- The changes it must IGNORE (menu <-> availability independence) ----------


async def test_a_new_dish_does_not_bust_the_availability_validator(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """A dish nobody has 86'd is absent from the board, so the board's answer did not change and a
    304 is correct. Coupling the two would make every menu edit re-download the 86 board."""
    unchanged = await _etag(website_api)
    await build_dish(
        db_session,
        website_api.tenant_id,
        website_api.kitchen.setup,
        item_code="NEW-DISH",
        recipe={},
    )
    still = await website_api.client.get(AVAILABILITY_URL, headers={"If-None-Match": unchanged})
    assert still.status_code == 304


async def test_a_reprice_does_not_bust_the_availability_validator(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """Price lives in ``sales_price_list_items`` and availability in ``hsp_menu_availability``;
    the validator is computed over the latter alone, so the two resources are independent."""
    unchanged = await _etag(website_api)
    await build_menu_price(
        db_session,
        website_api.tenant_id,
        website_api.price_list_id,
        website_api.kitchen.dishes["STEAK"],
        "32.00",
    )
    still = await website_api.client.get(AVAILABILITY_URL, headers={"If-None-Match": unchanged})
    assert still.status_code == 304


async def test_the_menu_read_ships_no_validator_at_all(website_api: WebsiteApi) -> None:
    """The other half of the independence answer, and it is a deliberate ABSENCE, not a bug: a
    collection ETag over ``inv_items`` would 304 through a reprice forever, because price is in
    another table that ``COUNT(id), MAX(updated_at)`` never reads. The menu is bounded by
    ``max-age`` instead. Pinned here so nobody "fixes" it by adding the lying validator.
    """
    response = await website_api.client.get(MENU_URL)
    assert response.status_code == 200, response.text
    assert "etag" not in response.headers
    assert "max-age=60" in response.headers["cache-control"]


# --- Tenancy ------------------------------------------------------------------


async def test_a_validator_never_crosses_tenants(
    website_api: WebsiteApi,
    db_session: AsyncSession,
    client: AsyncClient,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> None:
    """D-007 belt-and-suspenders: two properties with identically-shaped boards must still hold
    different validators, or one restaurant's 86 board is served to another's guests as a 304."""
    pasta = website_api.kitchen.dishes["PASTA"]
    await _86(website_api, db_session, pasta, reason="tenant A is out of basil")
    tenant_a_tag = await _etag(website_api)

    other = await hospitality_user_factory(slug="hsp-other", email="chef@hsp-other.test")
    other_dish = await build_dish(
        db_session,
        other.tenant_id,
        await _stock_setup_for(db_session, other.tenant_id),
        item_code="OTHER-DISH",
        recipe={},
    )
    with tenant_context(other.tenant_id):
        await availability.set_availability(
            db_session,
            other.tenant_id,
            other_dish,
            state=AvailabilityState.EIGHTY_SIXED,
            reason="tenant B is out of everything",
        )
        await db_session.commit()

    client.headers["Authorization"] = f"Bearer {await mint_website_key(db_session, other)}"
    cross = await client.get(AVAILABILITY_URL, headers={"If-None-Match": tenant_a_tag})
    assert cross.status_code == 200, "tenant A's validator was accepted for tenant B's board"
    assert cross.headers["etag"] != tenant_a_tag
    reasons = [row["reason"] for row in cross.json()["items"]]
    assert reasons == ["tenant B is out of everything"]


async def _stock_setup_for(session: AsyncSession, tenant_id: uuid.UUID):  # type: ignore[no-untyped-def]
    from tests.modules.inventory.factories import build_stock_setup

    return await build_stock_setup(session, tenant_id)


# --- The two spellings of the expiry rule must agree (D-003) -------------------


async def test_the_sql_lapsed_count_agrees_with_the_python_rule(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    make_dish: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """``lapsed_count_expr`` is the validator's half of the expiry rule and it runs in SQL, which
    is exactly what this module's docstring warns drifts from the Python half.

    Both spellings are pinned here against the same instant, INCLUDING the boundary itself
    (``<=``, so a row expiring at exactly ``now`` is lapsed in both). This is also the D-003 check
    that comparing a tz-aware bound parameter against a ``DateTime(timezone=True)`` column
    round-trips correctly on the SQLite test engine, where the column comes back naive.
    """
    now = utcnow()
    boundaries = {
        await make_dish("EXP-PAST", "lapsed"): now - timedelta(hours=1),
        await make_dish("EXP-EDGE", "on the boundary"): now,
        await make_dish("EXP-SOON", "still snoozed"): now + timedelta(hours=1),
        await make_dish("EXP-NEVER", "no boundary"): None,
    }
    with tenant_context(tenant_a):
        for item_id, until in boundaries.items():
            await availability.set_availability(
                db_session,
                tenant_a,
                item_id,
                state=AvailabilityState.EIGHTY_SIXED,
                available_until=until,
            )
        await db_session.commit()

        rows = (await db_session.execute(select(MenuAvailability))).scalars().all()
        in_python = sum(availability._is_expired(row, now) for row in rows)
        in_sql = (
            await db_session.execute(select(availability.lapsed_count_expr(now)))
        ).scalar_one()

    assert in_python == 2, "the past and the exactly-on-the-boundary rows are both lapsed"
    assert in_sql == in_python, (
        f"the SQL expiry predicate counted {in_sql} lapsed rows and the Python one {in_python} — "
        "the validator and the body would disagree about which dishes are back on"
    )


# --- Cost ---------------------------------------------------------------------


async def test_the_availability_read_stays_within_the_query_budget(
    website_api: WebsiteApi,
    db_session: AsyncSession,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """PERFORMANCE §2. Whatever shuts the expiry hole must not buy it with a second aggregate: the
    200 path is auth + validator + page, and the 304 path must stay cheaper than the 200."""
    await _86(website_api, db_session, website_api.kitchen.dishes["PASTA"])
    await website_api.client.get(AVAILABILITY_URL)  # warm the D-009 RBAC TTL cache

    with query_counter() as full:
        served = await website_api.client.get(AVAILABILITY_URL)
    assert served.status_code == 200, served.text
    with query_counter() as conditional:
        not_modified = await website_api.client.get(
            AVAILABILITY_URL, headers={"If-None-Match": served.headers["etag"]}
        )
    assert not_modified.status_code == 304

    assert full.count <= 3, (
        f"the availability read ran {full.count} statements (PERFORMANCE §2 budgets 3):\n"
        + "\n".join(full.statements)
    )
    assert conditional.count < full.count, (
        "a 304 must be cheaper than the 200 it replaces, or the validator is not paying for itself"
    )

"""Read-path statement budgets for the three hospitality reads (PERFORMANCE §2).

The module's own tests already pin that the menu read and the at-risk list do not grow with the
number of DISHES. This file attacks the dimensions those tests leave open, because a flatness claim
is only as strong as the axis it was measured on:

* the menu read's extra dishes are UNPRICED there, so the price-resolution join is measured over a
  couple of matching rows — here every dish on a 60-item menu is on the price list;
* the at-risk list's extra dishes carry ONE component there — here 60 dishes carry seven each, and
  a separate case nests a BOM under a BOM, which is where a recursive explosion would start
  charging a query per level;
* the website's ``/menu/availability`` had no query-count coverage at all, on either the 200 or the
  304 branch;
* Phase 20.1's HOTEL reads grow along a different axis again — how many rooms a property has, and
  how many tasks a day's departures put on the housekeeping board.

Each test asserts EQUALITY between the small and large shapes as well as the ≤3 budget. A budget
alone is satisfiable by a shape that still grows per row until it hits the wall; the pair is what
pins "does not scale". Absolute counts are named in the assertion messages so a failure reports the
measurement rather than just the verdict.
"""

from collections.abc import Callable
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import AvailabilityState
from app.modules.hospitality.service import availability
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.hospitality.conftest import HospitalityApi, RoomsApi, WebsiteApi
from tests.modules.hospitality.factories import build_dish, build_menu_price
from tests.modules.hospitality.test_housekeeping import TASKS_URL, raise_task
from tests.modules.hospitality.test_rooms import (
    RATE_PLANS_URL,
    ROOM_TYPES_URL,
    ROOMS_URL,
    make_room,
    make_room_type,
)

MENU_URL = "/api/v1/hospitality/menu"
AVAILABILITY_URL = "/api/v1/hospitality/menu/availability"
AT_RISK_URL = "/api/v1/hospitality/menu/at-risk"

# The menu size Q2 costed the rejected derived-availability shape at (~1,080 statements).
MENU_SIZE = 60
# PERFORMANCE §2: the auth principal plus the read's own statements.
READ_BUDGET = 3


async def test_the_priced_menu_read_does_not_scale_with_the_menu(
    website_api: WebsiteApi,
    db_session: AsyncSession,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """A 60-item menu where EVERY dish resolves a price, against the seeded 4-item one.

    The existing flatness test widens the menu with unpriced items, so the batched price join
    returns two rows either way and a per-item price resolution would barely show. Pricing all 60
    is what makes ``resolve_list_prices`` do real work; it must still be the same ONE statement.
    """
    client = website_api.client
    await client.get(MENU_URL)  # warm the D-009 RBAC TTL cache

    with query_counter() as small:
        first = await client.get(MENU_URL, params={"limit": 200})
    assert first.status_code == 200, first.text
    seeded = len(first.json()["items"])

    for index in range(MENU_SIZE - seeded):
        dish = await build_dish(
            db_session,
            website_api.tenant_id,
            website_api.kitchen.setup,
            item_code=f"MENU-{index:03d}",
            recipe={},
        )
        await build_menu_price(
            db_session, website_api.tenant_id, website_api.price_list_id, dish, "12.00"
        )

    with query_counter() as large:
        second = await client.get(MENU_URL, params={"limit": 200})
    assert second.status_code == 200, second.text

    rows = second.json()["items"]
    assert len(rows) == MENU_SIZE
    assert sum(1 for row in rows if row["price"] is not None) >= MENU_SIZE - seeded
    assert large.count == small.count, (
        f"the menu read cost {small.count} statements for {seeded} dishes and {large.count} for "
        f"{MENU_SIZE} priced ones:\n" + "\n".join(large.statements)
    )
    assert large.count <= READ_BUDGET, (
        f"the menu read ran {large.count} statements at {MENU_SIZE} dishes "
        f"(PERFORMANCE §2 budgets {READ_BUDGET}):\n" + "\n".join(large.statements)
    )


async def test_the_availability_read_does_not_scale_with_the_86_board(
    website_api: WebsiteApi,
    db_session: AsyncSession,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The guest-facing 86 board, on both branches of its conditional GET.

    This is the read the website makes on EVERY request — ``no-cache, must-revalidate`` — so its
    cost is the one that multiplies by the property's traffic rather than by its menu. An empty
    board and a fully-86'd 60-item menu must cost the same, and the 304 must cost strictly less
    than the 200 or revalidating would be pointless.
    """
    client = website_api.client
    await client.get(AVAILABILITY_URL)  # warm the D-009 RBAC TTL cache

    with query_counter() as empty:
        blank = await client.get(AVAILABILITY_URL, params={"limit": 200})
    assert blank.status_code == 200, blank.text
    assert blank.json()["items"] == []

    dishes = [
        await build_dish(
            db_session,
            website_api.tenant_id,
            website_api.kitchen.setup,
            item_code=f"BOARD-{index:03d}",
            recipe={},
        )
        for index in range(MENU_SIZE)
    ]
    with tenant_context(website_api.tenant_id):
        for dish in dishes:
            await availability.set_availability(
                db_session, website_api.tenant_id, dish, state=AvailabilityState.EIGHTY_SIXED
            )
        await db_session.commit()

    with query_counter() as full:
        response = await client.get(AVAILABILITY_URL, params={"limit": 200})
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == MENU_SIZE

    assert full.count == empty.count, (
        f"the availability read cost {empty.count} statements for an empty board and "
        f"{full.count} for {MENU_SIZE} 86'd dishes:\n" + "\n".join(full.statements)
    )
    assert full.count <= READ_BUDGET, (
        f"the availability read ran {full.count} statements (PERFORMANCE §2 budgets "
        f"{READ_BUDGET}):\n" + "\n".join(full.statements)
    )

    with query_counter() as revalidated:
        not_modified = await client.get(
            AVAILABILITY_URL,
            params={"limit": 200},
            headers={"If-None-Match": response.headers["etag"]},
        )
    assert not_modified.status_code == 304, not_modified.text
    assert revalidated.count < full.count, (
        f"a 304 cost {revalidated.count} statements against the 200's {full.count} — the validator "
        "is not saving the page read:\n" + "\n".join(revalidated.statements)
    )


async def test_the_at_risk_list_does_not_scale_with_recipe_size_or_depth(
    hospitality_api: HospitalityApi,
    db_session: AsyncSession,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The staff coverage scan, widened on the two axes its own test holds constant.

    ``at_risk_menu_items`` is TWO set-based statements — one whole-tenant BOM explosion, then one
    batched on-hand read over the ingredients it named — and neither the components per dish nor
    the nesting of a BOM under a BOM may add a third. Depth is the interesting one: the explosion
    is single-level by design, and the obvious "fix" for that (walking each sub-recipe) is a query
    per level, which is how a 2-statement scan becomes Q2's ~1,080.
    """
    client = hospitality_api.client
    kitchen = hospitality_api.kitchen
    url = f"{AT_RISK_URL}?threshold=1000000&limit=200"
    await client.get(url)  # warm the D-009 RBAC TTL cache

    with query_counter() as small:
        first = await client.get(url)
    assert first.status_code == 200, first.text

    # Seven ingredients a dish — the plan's own restaurant shape — across a 60-dish menu.
    pantry = list(kitchen.ingredients.values())
    while len(pantry) < 7:
        pantry.append(
            await build_dish(
                db_session,
                hospitality_api.tenant_id,
                kitchen.setup,
                item_code=f"PANTRY-{len(pantry):03d}",
                recipe={},
            )
        )
    recipe = {item_id: Decimal(1) for item_id in pantry}
    for index in range(MENU_SIZE):
        await build_dish(
            db_session,
            hospitality_api.tenant_id,
            kitchen.setup,
            item_code=f"WIDE-{index:03d}",
            recipe=recipe,
        )

    # A three-level chain: PLATE -> SAUCE -> the pantry. Each level is a parent with its own ACTIVE
    # default BOM, which is what a recursive exploder would charge an extra round trip for.
    sauce = await build_dish(
        db_session, hospitality_api.tenant_id, kitchen.setup, item_code="SAUCE", recipe=recipe
    )
    await build_dish(
        db_session,
        hospitality_api.tenant_id,
        kitchen.setup,
        item_code="PLATE",
        recipe={sauce: Decimal(2)},
    )

    with query_counter() as large:
        second = await client.get(url)
    assert second.status_code == 200, second.text
    assert len(second.json()) > len(first.json())

    assert large.count == small.count, (
        f"the at-risk list cost {small.count} statements for the seeded menu and {large.count} for "
        f"{MENU_SIZE} seven-ingredient dishes plus a nested BOM:\n" + "\n".join(large.statements)
    )
    assert large.count <= READ_BUDGET, (
        f"the at-risk list ran {large.count} statements (PERFORMANCE §2 budgets {READ_BUDGET}):\n"
        + "\n".join(large.statements)
    )


# --- The hotel reads (Phase 20.1) ---------------------------------------------
# Same argument as the three above, on the two axes a PROPERTY grows along: how many rooms it has,
# and how many tasks a day's departures put on the housekeeping board. Both reads are one paginated
# statement by construction, and the pair of assertions (equality + the ceiling) is what pins that
# rather than just bounding it.

# Big enough that a per-row query would show against the ≤3 budget, small enough to seed quickly.
PROPERTY_SIZE = 40
BOARD_SIZE = 30


async def test_the_room_list_does_not_scale_with_the_property(
    rooms_api: RoomsApi, query_counter: Callable[[], QueryCounter]
) -> None:
    """A 40-room property must cost the same as a 1-room one: the auth principal plus ONE page
    select, on both the unfiltered read and the two filters the board uses."""
    client = rooms_api.client
    room_type_id = await make_room_type(client)
    await make_room(client, room_type_id, "000")

    await client.get(ROOMS_URL)  # warm the D-009 RBAC TTL cache
    with query_counter() as small:
        first = await client.get(ROOMS_URL, params={"limit": 200})
    assert first.status_code == 200, first.text

    for index in range(1, PROPERTY_SIZE):
        await make_room(client, room_type_id, f"{index:03d}")

    with query_counter() as large:
        second = await client.get(ROOMS_URL, params={"limit": 200})
    assert second.status_code == 200, second.text
    assert len(second.json()["items"]) == PROPERTY_SIZE

    assert large.count == small.count, (
        f"the room list cost {small.count} statements for 1 room and {large.count} for "
        f"{PROPERTY_SIZE}:\n" + "\n".join(large.statements)
    )
    assert large.count <= READ_BUDGET, (
        f"the room list ran {large.count} statements at {PROPERTY_SIZE} rooms "
        f"(PERFORMANCE §2 budgets {READ_BUDGET}):\n" + "\n".join(large.statements)
    )

    with query_counter() as filtered:
        by_type = await client.get(
            ROOMS_URL, params={"room_type_id": str(room_type_id), "limit": 200}
        )
    assert by_type.status_code == 200, by_type.text
    assert filtered.count <= READ_BUDGET, (
        f"the filtered room list ran {filtered.count} statements:\n"
        + "\n".join(filtered.statements)
    )


async def test_the_housekeeping_board_does_not_scale_with_the_days_departures(
    rooms_api: RoomsApi, query_counter: Callable[[], QueryCounter]
) -> None:
    """A 30-task board must cost the same as a 1-task one: one page select, whatever the day's
    departures were. The board is the read a supervisor refreshes all morning."""
    client = rooms_api.client
    room_type_id = await make_room_type(client)
    room_ids = [
        (await make_room(client, room_type_id, f"{index:03d}"))["id"]
        for index in range(BOARD_SIZE)
    ]
    await raise_task(client, room_ids[0])

    await client.get(TASKS_URL)  # warm the D-009 RBAC TTL cache
    with query_counter() as small:
        first = await client.get(TASKS_URL, params={"limit": 200})
    assert first.status_code == 200, first.text

    for room_id in room_ids[1:]:
        await raise_task(client, room_id)

    with query_counter() as large:
        second = await client.get(TASKS_URL, params={"limit": 200})
    assert second.status_code == 200, second.text
    assert len(second.json()["items"]) == BOARD_SIZE

    assert large.count == small.count, (
        f"the board cost {small.count} statements for 1 task and {large.count} for "
        f"{BOARD_SIZE}:\n" + "\n".join(large.statements)
    )
    assert large.count <= READ_BUDGET, (
        f"the board ran {large.count} statements at {BOARD_SIZE} tasks (PERFORMANCE §2 budgets "
        f"{READ_BUDGET}):\n" + "\n".join(large.statements)
    )


async def test_the_room_type_rate_plan_and_board_reads_meet_the_shared_helper(
    rooms_api: RoomsApi, query_counter: Callable[[], QueryCounter]
) -> None:
    """The remaining three Phase 20.1 reads, through the ≤3 helper every module's API tests reuse.
    Seeded with a row each so the budget is measured over a page that actually returns something."""
    client = rooms_api.client
    room_type_id = await make_room_type(client)
    await raise_task(client, (await make_room(client, room_type_id, "101"))["id"])
    await client.post(
        RATE_PLANS_URL,
        json={
            "code": "BAR",
            "name": "Best available rate",
            "room_type_id": str(room_type_id),
            "nightly_amount": "149.99",
            "currency_code": "USD",
            "valid_from": "2026-01-01",
        },
    )

    await assert_query_budget(client, query_counter, ROOM_TYPES_URL)
    await assert_query_budget(client, query_counter, RATE_PLANS_URL)
    await assert_query_budget(client, query_counter, TASKS_URL)

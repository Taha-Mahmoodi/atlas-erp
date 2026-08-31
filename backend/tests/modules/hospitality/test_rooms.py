"""The rooms masters and the housekeeping state machine (PLAN 20.1).

Three masters (room type, room, rate plan) in the ordinary Atlas master anatomy — a user-supplied
code unique PER TENANT, a friendly ``*_code_conflict`` before the DB UNIQUE, a keyset-paginated
list — plus the one thing here that is not ordinary CRUD: ``Room.housekeeping_status``.

**Why the status has its own endpoint and its own transition table.** Phase 20 Task 4 hangs the
allotment counter off OUT_OF_ORDER — a room out of service lowers ``rooms_sellable`` on the future
dates it covers, and coming back raises it. That only works if there is exactly ONE function that
moves the column, so these tests pin that a plain PATCH cannot move it and that every illegal move
is refused by ``HOUSEKEEPING_FLOW`` rather than by whoever wrote the caller.
"""

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import (
    HOSPITALITY_HOUSEKEEPING_MANAGE,
    HOSPITALITY_ROOMS_MANAGE,
    HOSPITALITY_ROOMS_READ,
    HousekeepingStatus,
)
from app.modules.hospitality.rooms_schemas import RoomCreate, RoomTypeCreate
from app.modules.hospitality.service import rooms
from tests.modules.hospitality.conftest import RoomsApi

RoomsApiFactory = Callable[..., Awaitable[RoomsApi]]

ROOM_TYPES_URL = "/api/v1/hospitality/room-types"
ROOMS_URL = "/api/v1/hospitality/rooms"
RATE_PLANS_URL = "/api/v1/hospitality/rate-plans"

# Big enough that a per-row query would show against the ≤3 budget, small enough to seed quickly.
PROPERTY_SIZE = 40


async def make_room_type(
    client: AsyncClient, *, code: str = "DBL", capacity: int = 2
) -> uuid.UUID:
    response = await client.post(
        ROOM_TYPES_URL,
        json={"code": code, "name": f"{code} room", "base_capacity": capacity},
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


async def make_room(
    client: AsyncClient, room_type_id: uuid.UUID, number: str
) -> dict[str, Any]:
    response = await client.post(
        ROOMS_URL, json={"room_number": number, "room_type_id": str(room_type_id)}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def set_status(
    client: AsyncClient, room_id: uuid.UUID | str, status: HousekeepingStatus
) -> Response:
    return await client.post(
        f"{ROOMS_URL}/{room_id}/housekeeping-status", json={"status": status.value}
    )


# --- Creation and per-tenant uniqueness ---------------------------------------


async def test_a_room_type_a_room_and_a_rate_plan_are_created_and_read_back(
    rooms_api: RoomsApi,
) -> None:
    """The happy path across all three masters, including the money round trip.

    ``nightly_amount`` is a ``MoneyType`` (D-015): it must come back as the EXACT decimal it went
    in as, because a rate is what the night audit will multiply into revenue.
    """
    client = rooms_api.client
    room_type_id = await make_room_type(client, code="DLX", capacity=3)

    room = await make_room(client, room_type_id, "101")
    assert room["room_number"] == "101"
    assert room["room_type_id"] == str(room_type_id)

    response = await client.post(
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
    assert response.status_code == 201, response.text
    plan = response.json()
    assert Decimal(plan["nightly_amount"]) == Decimal("149.99")
    assert plan["valid_to"] is None

    listed = await client.get(RATE_PLANS_URL, params={"room_type_id": str(room_type_id)})
    assert listed.status_code == 200, listed.text
    assert [row["code"] for row in listed.json()["items"]] == ["BAR"]


async def test_a_new_room_starts_dirty_rather_than_sellable(rooms_api: RoomsApi) -> None:
    """A room the property has just added has not been made up by anybody, so it starts DIRTY and
    has to be walked through the cycle like any other. The create payload carries no status field
    at all — the ONE path that moves the column is the transition endpoint (Task 4's hook)."""
    client = rooms_api.client
    room = await make_room(client, await make_room_type(client), "201")
    assert room["housekeeping_status"] == HousekeepingStatus.DIRTY.value


async def test_a_room_type_code_is_unique_within_the_tenant(rooms_api: RoomsApi) -> None:
    """The second SGL is refused with a friendly 409 before the DB UNIQUE would raise — the
    ``inventory.item_code_conflict`` shape."""
    client = rooms_api.client
    await make_room_type(client, code="SGL")

    response = await client.post(
        ROOM_TYPES_URL, json={"code": "SGL", "name": "Single again", "base_capacity": 1}
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "hospitality.room_type_code_conflict"


async def test_a_room_number_is_unique_within_the_tenant(rooms_api: RoomsApi) -> None:
    """Two rooms numbered 101 is a data-entry mistake every time — a property has one 101."""
    client = rooms_api.client
    room_type_id = await make_room_type(client)
    await make_room(client, room_type_id, "101")

    response = await client.post(
        ROOMS_URL, json={"room_number": "101", "room_type_id": str(room_type_id)}
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "hospitality.room_number_conflict"


async def test_two_tenants_may_each_have_a_room_101(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """D-007: uniqueness is PER TENANT. Driven at the service layer because the assertion is about
    two tenants, and a bearer-token client only ever holds one."""
    for tenant_id in (tenant_a, tenant_b):
        with tenant_context(tenant_id):
            room_type = await rooms.create_room_type(
                db_session, tenant_id, RoomTypeCreate(code="DBL", name="Double", base_capacity=2)
            )
            await rooms.create_room(
                db_session,
                tenant_id,
                RoomCreate(room_number="101", room_type_id=room_type.id),
            )
            await db_session.commit()


async def test_a_room_cannot_be_hung_off_another_tenants_room_type(
    rooms_api: RoomsApi, db_session: AsyncSession, tenant_b: uuid.UUID
) -> None:
    """The room type is resolved through the tenant-scoped getter, so a foreign id is a 404 rather
    than a room quietly attached to somebody else's inventory."""
    with tenant_context(tenant_b):
        foreign = await rooms.create_room_type(
            db_session, tenant_b, RoomTypeCreate(code="FGN", name="Foreign", base_capacity=2)
        )
        foreign_id = foreign.id
        await db_session.commit()

    response = await rooms_api.client.post(
        ROOMS_URL, json={"room_number": "301", "room_type_id": str(foreign_id)}
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "hospitality.room_type_not_found"


async def test_a_rate_plan_may_not_end_before_it_starts(rooms_api: RoomsApi) -> None:
    """A validity window is the whole of v1's rate calendar (no date ranges beyond it), so the one
    thing that must not be storable is a window that covers nothing."""
    client = rooms_api.client
    response = await client.post(
        RATE_PLANS_URL,
        json={
            "code": "BAD",
            "name": "Backwards",
            "room_type_id": str(await make_room_type(client)),
            "nightly_amount": "100.00",
            "currency_code": "USD",
            "valid_from": "2026-06-01",
            "valid_to": "2026-05-01",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "hospitality.rate_plan_window_invalid"


# --- The housekeeping state machine -------------------------------------------


async def test_a_room_walks_the_full_housekeeping_cycle(rooms_api: RoomsApi) -> None:
    """DIRTY -> IN_PROGRESS -> CLEAN -> INSPECTED -> DIRTY: the day's loop, one move at a time."""
    client = rooms_api.client
    room = await make_room(client, await make_room_type(client), "401")

    for status in (
        HousekeepingStatus.IN_PROGRESS,
        HousekeepingStatus.CLEAN,
        HousekeepingStatus.INSPECTED,
        HousekeepingStatus.DIRTY,
    ):
        response = await set_status(client, room["id"], status)
        assert response.status_code == 200, response.text
        assert response.json()["housekeeping_status"] == status.value


async def test_a_dirty_room_cannot_be_declared_clean_without_being_cleaned(
    rooms_api: RoomsApi,
) -> None:
    """DIRTY -> CLEAN is not in ``HOUSEKEEPING_FLOW``: somebody has to be in the room. The refusal
    is the transition table's, not a caller's — which is what stops the two writers of this column
    (this endpoint and a housekeeping task completing) drifting apart."""
    client = rooms_api.client
    room = await make_room(client, await make_room_type(client), "402")

    response = await set_status(client, room["id"], HousekeepingStatus.CLEAN)
    assert response.status_code == 409, response.text
    body = response.json()["error"]
    assert body["code"] == "hospitality.room_not_transitionable"
    assert body["details"]["housekeeping_status"] == HousekeepingStatus.DIRTY.value


@pytest.mark.parametrize(
    "reached_via",
    [
        (HousekeepingStatus.OUT_OF_ORDER,),
        (HousekeepingStatus.IN_PROGRESS, HousekeepingStatus.OUT_OF_ORDER),
        (
            HousekeepingStatus.IN_PROGRESS,
            HousekeepingStatus.CLEAN,
            HousekeepingStatus.OUT_OF_ORDER,
        ),
    ],
)
async def test_a_room_can_go_out_of_order_from_any_state(
    rooms_api: RoomsApi, reached_via: tuple[HousekeepingStatus, ...]
) -> None:
    """A pipe bursts whatever condition the room was in, so OUT_OF_ORDER is reachable from
    everywhere. This is the transition Task 4 decrements ``rooms_sellable`` on, which is why it
    must not depend on where the room happened to be."""
    client = rooms_api.client
    room = await make_room(client, await make_room_type(client), "501")

    for status in reached_via:
        response = await set_status(client, room["id"], status)
        assert response.status_code == 200, response.text
    assert response.json()["housekeeping_status"] == HousekeepingStatus.OUT_OF_ORDER.value


async def test_a_room_out_of_order_comes_back_dirty_and_not_sellable(
    rooms_api: RoomsApi,
) -> None:
    """OUT_OF_ORDER leaves only to DIRTY. A room that has had a refit is not sellable on a
    supervisor's word — it is cleaned first, which is also what gives Task 4 a single, symmetric
    place to put the counter back."""
    client = rooms_api.client
    room = await make_room(client, await make_room_type(client), "502")
    ooo = await set_status(client, room["id"], HousekeepingStatus.OUT_OF_ORDER)
    assert ooo.status_code == 200, ooo.text

    refused = await set_status(client, room["id"], HousekeepingStatus.CLEAN)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "hospitality.room_not_transitionable"

    back = await set_status(client, room["id"], HousekeepingStatus.DIRTY)
    assert back.status_code == 200, back.text
    assert back.json()["housekeeping_status"] == HousekeepingStatus.DIRTY.value


async def test_editing_a_room_cannot_move_its_housekeeping_status(rooms_api: RoomsApi) -> None:
    """The PATCH renames and re-types a room and CANNOT touch the status — ``extra="forbid"`` on
    the update schema. Task 4's counter hook lives on the transition function, so a second writer
    reaching the column would be an oversell nothing tests."""
    client = rooms_api.client
    room = await make_room(client, await make_room_type(client), "601")

    response = await client.patch(
        f"{ROOMS_URL}/{room['id']}",
        json={"housekeeping_status": HousekeepingStatus.CLEAN.value},
    )
    assert response.status_code == 422, response.text

    renamed = await client.patch(f"{ROOMS_URL}/{room['id']}", json={"room_number": "601A"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["room_number"] == "601A"
    assert renamed.json()["housekeeping_status"] == HousekeepingStatus.DIRTY.value


async def test_renumbering_a_room_onto_a_taken_number_is_a_conflict(rooms_api: RoomsApi) -> None:
    """The COLLIDING rename, which the create path has always refused and the update path did not.

    ``uq_hsp_rooms_tenant_id_room_number`` is the backstop either way, but reaching it raises an
    unhandled IntegrityError — a 500 on a value the caller supplied. Both paths go through the same
    pre-check now, so a property that renumbers 402 onto 401 gets the same readable 409 it gets for
    creating a second 401. Renumbering a room onto the number it already has stays a no-op.
    """
    client = rooms_api.client
    room_type_id = await make_room_type(client)
    first = await make_room(client, room_type_id, "401")
    second = await make_room(client, room_type_id, "402")

    refused = await client.patch(f"{ROOMS_URL}/{second['id']}", json={"room_number": "401"})
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "hospitality.room_number_conflict"
    assert (await client.get(f"{ROOMS_URL}/{second['id']}")).json()["room_number"] == "402"

    idle = await client.patch(f"{ROOMS_URL}/{first['id']}", json={"room_number": "401"})
    assert idle.status_code == 200, idle.text
    assert idle.json()["room_number"] == "401"


async def test_patching_a_room_field_to_null_leaves_it_alone(rooms_api: RoomsApi) -> None:
    """Both columns are NOT NULL, so an explicit ``null`` must be dropped rather than flushed.

    ``exclude_unset`` distinguishes "not sent" from "sent as null" and the PATCH shape accepts
    either; setting the attribute to None reaches the NOT NULL constraint as an IntegrityError,
    which is the same 500-on-a-supplied-value the renumber path had. Neither field has a meaning
    for null the way ``RatePlanUpdate.valid_to`` does.
    """
    client = rooms_api.client
    room = await make_room(client, await make_room_type(client), "403")

    response = await client.patch(
        f"{ROOMS_URL}/{room['id']}", json={"room_number": None, "room_type_id": None}
    )
    assert response.status_code == 200, response.text
    assert response.json()["room_number"] == "403"
    assert response.json()["room_type_id"] == room["room_type_id"]


async def test_patching_a_room_type_field_to_null_leaves_it_alone(rooms_api: RoomsApi) -> None:
    """The same NOT NULL rule as rooms, on the sibling endpoint that did not get the guard.

    ``update_room`` filtered explicit nulls; ``update_room_type`` did not, so ``{"name": null}``
    reached the flush as a 500. Both now route through ``_sent_fields`` — the fix belongs in one
    place, because this defect survived being fixed once.
    """
    client = rooms_api.client
    room_type_id = await make_room_type(client, code="NUL", capacity=2)

    response = await client.patch(
        f"{ROOM_TYPES_URL}/{room_type_id}", json={"name": None, "base_capacity": None}
    )
    assert response.status_code == 200, response.text
    assert response.json()["base_capacity"] == 2


async def test_patching_a_rate_plan_keeps_null_meaningful_only_for_valid_to(
    rooms_api: RoomsApi,
) -> None:
    """``valid_to: null`` OPENS the window and must keep working; every other null is dropped.

    ``valid_from: null`` additionally crashed inside ``_require_window`` comparing a date against
    None — a service-layer TypeError before the flush, so filtering the null is what fixes it, not
    a guard at the constraint.
    """
    client = rooms_api.client
    room_type_id = await make_room_type(client, code="WIN", capacity=2)
    created = await client.post(
        RATE_PLANS_URL,
        json={
            "code": "WKND",
            "name": "Weekend rate",
            "room_type_id": str(room_type_id),
            "nightly_amount": "200.00",
            "currency_code": "USD",
            "valid_from": "2026-01-01",
            "valid_to": "2026-03-31",
        },
    )
    assert created.status_code == 201, created.text
    plan = created.json()

    dropped = await client.patch(
        f"{RATE_PLANS_URL}/{plan['id']}",
        json={"name": None, "nightly_amount": None, "valid_from": None},
    )
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["name"] == "Weekend rate"
    assert Decimal(dropped.json()["nightly_amount"]) == Decimal("200.00")
    assert dropped.json()["valid_from"] == "2026-01-01"

    opened = await client.patch(f"{RATE_PLANS_URL}/{plan['id']}", json={"valid_to": None})
    assert opened.status_code == 200, opened.text
    assert opened.json()["valid_to"] is None


# --- Permission gating (D-009) ------------------------------------------------


async def test_reading_rooms_needs_the_read_key(rooms_api_factory: RoomsApiFactory) -> None:
    api = await rooms_api_factory(slug="hsp-noread", email="a@hsp-noread.test", keys=())
    assert (await api.client.get(ROOMS_URL)).status_code == 403


async def test_creating_a_room_needs_the_manage_key_not_the_read_key(
    rooms_api_factory: RoomsApiFactory,
) -> None:
    """A reader may look at the property and change nothing."""
    api = await rooms_api_factory(
        slug="hsp-ro", email="a@hsp-ro.test", keys=(HOSPITALITY_ROOMS_READ,)
    )
    assert (await api.client.get(ROOMS_URL)).status_code == 200
    response = await api.client.post(
        ROOM_TYPES_URL, json={"code": "X", "name": "X", "base_capacity": 1}
    )
    assert response.status_code == 403, response.text


async def test_setting_a_housekeeping_status_needs_the_housekeeping_key(
    rooms_api: RoomsApi,
    rooms_api_factory: RoomsApiFactory,
) -> None:
    """The third key earns its place: whoever edits the room master is not automatically whoever
    takes a room out of service, because that move has a revenue consequence (Task 4). Seeded by
    the full-rights principal, then driven by a narrowed one in the SAME tenant."""
    room = await make_room(rooms_api.client, await make_room_type(rooms_api.client), "701")

    narrowed = await rooms_api_factory(
        slug="hsp-hk",
        email="a@hsp-hk.test",
        keys=(HOSPITALITY_ROOMS_READ, HOSPITALITY_ROOMS_MANAGE),
    )
    refused = await set_status(narrowed.client, room["id"], HousekeepingStatus.IN_PROGRESS)
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["details"]["permission"] == HOSPITALITY_HOUSEKEEPING_MANAGE


async def test_the_room_list_is_paginated_and_filterable(rooms_api: RoomsApi) -> None:
    """Keyset pagination (D-014, never OFFSET) plus the two filters the board actually uses: by
    room type, and by housekeeping status."""
    client = rooms_api.client
    doubles = await make_room_type(client, code="DBL")
    singles = await make_room_type(client, code="SGL", capacity=1)
    for index in range(4):
        await make_room(client, doubles, f"1{index:02d}")
    solo = await make_room(client, singles, "900")
    await set_status(client, solo["id"], HousekeepingStatus.IN_PROGRESS)

    page = await client.get(ROOMS_URL, params={"limit": 2})
    assert page.status_code == 200, page.text
    body = page.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]

    second = await client.get(ROOMS_URL, params={"limit": 2, "cursor": body["next_cursor"]})
    assert second.status_code == 200, second.text
    assert {row["id"] for row in second.json()["items"]}.isdisjoint(
        {row["id"] for row in body["items"]}
    )

    by_type = await client.get(ROOMS_URL, params={"room_type_id": str(singles), "limit": 200})
    assert [row["room_number"] for row in by_type.json()["items"]] == ["900"]

    by_status = await client.get(
        ROOMS_URL,
        params={"housekeeping_status": HousekeepingStatus.IN_PROGRESS.value, "limit": 200},
    )
    assert [row["room_number"] for row in by_status.json()["items"]] == ["900"]

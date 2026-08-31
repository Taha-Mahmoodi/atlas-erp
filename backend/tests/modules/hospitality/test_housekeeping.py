"""The housekeeping task — a D-012 DOCUMENT, not a checkbox on the room (PLAN 20.1).

A task registers in ``core_documents``, claims a gapless ``HKT-`` number at creation (the
order-ticket branch: the board and the attendant's sheet both quote it the moment it is raised),
and carries a doc-flow edge back to whatever raised it — which is how Task 4's check-out will make
``GET /api/v1/documents/{id}/chain`` read reservation -> housekeeping task without this file
changing.

**The task and the room hold two different facts**, and these tests pin that they never drift: the
task's ``status`` is the work order's progress, the room's ``housekeeping_status`` is the room's
condition. Starting and finishing the work moves BOTH, through the same
``rooms.set_housekeeping_status`` the manual endpoint uses; cancelling the work moves only the task,
because a room nobody cleaned is still dirty.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient, Response

from app.modules.hospitality.constants import (
    HOSPITALITY_HOUSEKEEPING_MANAGE,
    HOSPITALITY_ROOMS_READ,
    HousekeepingStatus,
    HousekeepingTaskStatus,
    HousekeepingTrigger,
)
from tests.modules.hospitality.conftest import RoomsApi
from tests.modules.hospitality.test_rooms import (
    ROOMS_URL,
    make_room,
    make_room_type,
    set_status,
)

TASKS_URL = "/api/v1/hospitality/housekeeping-tasks"
RoomsApiFactory = Callable[..., Awaitable[RoomsApi]]

# One board's worth of tasks — enough that a per-row read would show against the ≤3 budget.
BOARD_SIZE = 30


async def raise_task(
    client: AsyncClient,
    room_id: str,
    *,
    trigger: HousekeepingTrigger = HousekeepingTrigger.CHECKOUT,
    **extra: Any,
) -> dict[str, Any]:
    response = await client.post(
        TASKS_URL,
        json={"room_id": room_id, "trigger": trigger.value, **extra},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def move_task(client: AsyncClient, task_id: str, **body: Any) -> Response:
    return await client.patch(f"{TASKS_URL}/{task_id}", json=body)


async def a_dirty_room(client: AsyncClient, number: str = "101") -> dict[str, Any]:
    return await make_room(client, await make_room_type(client), number)


async def test_a_task_is_a_numbered_registered_document(rooms_api: RoomsApi) -> None:
    """D-012: registered in ``core_documents`` with its gapless number claimed AT CREATION, so the
    board can quote a reference before anybody has touched the room."""
    client = rooms_api.client
    room = await a_dirty_room(client)
    task = await raise_task(client, room["id"])

    assert task["task_number"].startswith("HKT-")
    assert task["status"] == HousekeepingTaskStatus.OPEN.value
    assert task["trigger"] == HousekeepingTrigger.CHECKOUT.value

    chain = await client.get(f"/api/v1/documents/{task['document_id']}/chain")
    assert chain.status_code == 200, chain.text
    node = next(n for n in chain.json()["nodes"] if n["document_id"] == task["document_id"])
    assert node["doc_number"] == task["task_number"]
    assert node["doc_type"] == "hospitality.housekeeping_task"
    assert node["status"] == HousekeepingTaskStatus.OPEN.value


async def test_a_task_links_to_the_document_that_raised_it(rooms_api: RoomsApi) -> None:
    """The doc-flow edge, exercised today with a task raised FROM another task's document.

    Task 4's check-out passes the departing reservation's ``document_id`` through the same
    ``predecessor_document_id`` field, so the edge it needs already exists and is already tested —
    nothing in this file has to change when the reservation document lands.
    """
    client = rooms_api.client
    room = await a_dirty_room(client)
    first = await raise_task(client, room["id"])
    second = await raise_task(
        client,
        room["id"],
        trigger=HousekeepingTrigger.GUEST_REQUEST,
        predecessor_document_id=first["document_id"],
    )

    chain = await client.get(f"/api/v1/documents/{first['document_id']}/chain")
    assert chain.status_code == 200, chain.text
    assert chain.json()["edges"] == [
        {
            "predecessor_document_id": first["document_id"],
            "successor_document_id": second["document_id"],
            "link_type": "triggers_housekeeping",
        }
    ]


async def test_a_retried_raise_returns_the_first_task_rather_than_a_second(
    rooms_api: RoomsApi,
) -> None:
    """D-013: raising a task registers a document and burns a gapless number, so a retried request
    must return the first task — a housekeeper's flaky tablet must not double the board."""
    client = rooms_api.client
    room = await a_dirty_room(client)
    body = {"room_id": room["id"], "trigger": HousekeepingTrigger.CHECKOUT.value}
    headers = {"Idempotency-Key": "hk-retry-1"}

    first = await client.post(TASKS_URL, json=body, headers=headers)
    second = await client.post(TASKS_URL, json=body, headers=headers)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]

    listed = await client.get(TASKS_URL, params={"limit": 200})
    assert len(listed.json()["items"]) == 1


async def test_working_a_task_moves_the_room_with_it(rooms_api: RoomsApi) -> None:
    """Start the work and the room is IN_PROGRESS; finish it and the room is CLEAN. One writer:
    the task service calls the same ``set_housekeeping_status`` the manual endpoint calls, so
    Task 4's allotment hook cannot be bypassed by going through the board."""
    client = rooms_api.client
    room = await a_dirty_room(client)
    task = await raise_task(client, room["id"])

    started = await move_task(client, task["id"], status=HousekeepingTaskStatus.IN_PROGRESS.value)
    assert started.status_code == 200, started.text
    assert (await client.get(f"{ROOMS_URL}/{room['id']}")).json()[
        "housekeeping_status"
    ] == HousekeepingStatus.IN_PROGRESS.value

    done = await move_task(client, task["id"], status=HousekeepingTaskStatus.DONE.value)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == HousekeepingTaskStatus.DONE.value
    assert (await client.get(f"{ROOMS_URL}/{room['id']}")).json()[
        "housekeeping_status"
    ] == HousekeepingStatus.CLEAN.value


async def test_cancelling_a_task_leaves_the_room_exactly_as_dirty_as_it_was(
    rooms_api: RoomsApi,
) -> None:
    """The attendant was pulled off the room mid-clean. The work order is closed; the room is DIRTY
    again, not clean (nobody cleaned it) and not stuck IN_PROGRESS with no open task and no
    transition left that reaches it. This is the case that proves the two states are separate facts
    — and the leak this test caught before the code shipped."""
    client = rooms_api.client
    room = await a_dirty_room(client)
    task = await raise_task(client, room["id"])
    await move_task(client, task["id"], status=HousekeepingTaskStatus.IN_PROGRESS.value)

    cancelled = await move_task(client, task["id"], status=HousekeepingTaskStatus.CANCELLED.value)
    assert cancelled.status_code == 200, cancelled.text
    assert (await client.get(f"{ROOMS_URL}/{room['id']}")).json()[
        "housekeeping_status"
    ] == HousekeepingStatus.DIRTY.value


async def test_cancelling_a_task_nobody_started_changes_nothing(rooms_api: RoomsApi) -> None:
    """The other half of the cancel branch. An unconditional CANCELLED -> DIRTY would be refused
    here (DIRTY -> DIRTY is not a legal move) and a supervisor could never clear the board of work
    that was raised by mistake."""
    client = rooms_api.client
    room = await a_dirty_room(client)
    task = await raise_task(client, room["id"])

    cancelled = await move_task(client, task["id"], status=HousekeepingTaskStatus.CANCELLED.value)
    assert cancelled.status_code == 200, cancelled.text
    assert (await client.get(f"{ROOMS_URL}/{room['id']}")).json()[
        "housekeeping_status"
    ] == HousekeepingStatus.DIRTY.value


async def test_a_finished_task_cannot_be_reopened(rooms_api: RoomsApi) -> None:
    """DONE is terminal in ``HOUSEKEEPING_TASK_FLOW``: a room that needs more work gets a NEW task,
    so the board shows what is outstanding rather than reopened history."""
    client = rooms_api.client
    room = await a_dirty_room(client)
    task = await raise_task(client, room["id"])
    await move_task(client, task["id"], status=HousekeepingTaskStatus.IN_PROGRESS.value)
    await move_task(client, task["id"], status=HousekeepingTaskStatus.DONE.value)

    refused = await move_task(client, task["id"], status=HousekeepingTaskStatus.IN_PROGRESS.value)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "hospitality.housekeeping_task_not_transitionable"


async def test_a_task_cannot_be_worked_on_a_room_that_is_out_of_order(
    rooms_api: RoomsApi,
) -> None:
    """OUT_OF_ORDER leaves only to DIRTY (``HOUSEKEEPING_FLOW``), so starting the work is refused
    by the room's own transition rule — the board cannot quietly return a room to sale that the
    property has taken out of service, which is exactly the invariant Task 4's counter rests on."""
    client = rooms_api.client
    room = await a_dirty_room(client)
    task = await raise_task(client, room["id"])
    ooo = await set_status(client, room["id"], HousekeepingStatus.OUT_OF_ORDER)
    assert ooo.status_code == 200, ooo.text

    refused = await move_task(client, task["id"], status=HousekeepingTaskStatus.IN_PROGRESS.value)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "hospitality.room_not_transitionable"
    assert (await client.get(f"{TASKS_URL}/{task['id']}")).json()["status"] == (
        HousekeepingTaskStatus.OPEN.value
    )


async def test_a_task_can_be_reassigned_without_moving_its_status(rooms_api: RoomsApi) -> None:
    """One PATCH does both, the ``amend_reservation`` shape: a supervisor hands the room to
    somebody else without pretending the work has progressed."""
    client = rooms_api.client
    room = await a_dirty_room(client)
    task = await raise_task(client, room["id"])
    attendant = uuid.uuid4()

    response = await move_task(client, task["id"], assigned_user_id=str(attendant))
    assert response.status_code == 200, response.text
    assert response.json()["assigned_user_id"] == str(attendant)
    assert response.json()["status"] == HousekeepingTaskStatus.OPEN.value


async def test_a_task_on_another_tenants_room_is_not_found(rooms_api: RoomsApi) -> None:
    """The room is resolved through the tenant-scoped getter, so an unknown id is a 404 rather
    than a task hanging off nothing."""
    response = await rooms_api.client.post(
        TASKS_URL,
        json={"room_id": str(uuid.uuid4()), "trigger": HousekeepingTrigger.CHECKOUT.value},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "hospitality.room_not_found"


async def test_raising_a_task_needs_the_housekeeping_key(
    rooms_api: RoomsApi, rooms_api_factory: RoomsApiFactory
) -> None:
    """Reading the board is ``rooms.read``; raising and moving work is ``housekeeping.manage``."""
    room = await a_dirty_room(rooms_api.client)

    narrowed = await rooms_api_factory(
        slug="hsp-board", email="a@hsp-board.test", keys=(HOSPITALITY_ROOMS_READ,)
    )
    assert (await narrowed.client.get(TASKS_URL)).status_code == 200
    refused = await narrowed.client.post(
        TASKS_URL,
        json={"room_id": room["id"], "trigger": HousekeepingTrigger.CHECKOUT.value},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["details"]["permission"] == HOSPITALITY_HOUSEKEEPING_MANAGE


async def test_the_board_is_filterable_by_room_and_by_status(rooms_api: RoomsApi) -> None:
    """The two questions a supervisor asks: what is outstanding, and what is happening in 101."""
    client = rooms_api.client
    room_type_id = await make_room_type(client)
    first = await make_room(client, room_type_id, "101")
    second = await make_room(client, room_type_id, "102")
    open_task = await raise_task(client, first["id"])
    other = await raise_task(client, second["id"])
    await move_task(client, other["id"], status=HousekeepingTaskStatus.IN_PROGRESS.value)

    by_room = await client.get(TASKS_URL, params={"room_id": first["id"], "limit": 200})
    assert [row["id"] for row in by_room.json()["items"]] == [open_task["id"]]

    by_status = await client.get(
        TASKS_URL, params={"status": HousekeepingTaskStatus.OPEN.value, "limit": 200}
    )
    assert [row["id"] for row in by_status.json()["items"]] == [open_task["id"]]


@pytest.mark.parametrize(
    ("trigger", "walk_to"),
    [
        (
            HousekeepingTrigger.GUEST_REQUEST,
            (HousekeepingStatus.IN_PROGRESS, HousekeepingStatus.CLEAN),
        ),
        (
            HousekeepingTrigger.SCHEDULED,
            (
                HousekeepingStatus.IN_PROGRESS,
                HousekeepingStatus.CLEAN,
                HousekeepingStatus.INSPECTED,
            ),
        ),
    ],
)
async def test_a_task_can_be_started_on_a_room_that_is_already_made_up(
    rooms_api: RoomsApi,
    trigger: HousekeepingTrigger,
    walk_to: tuple[HousekeepingStatus, ...],
) -> None:
    """The two NON-CHECKOUT triggers, each on the room state it is actually raised from.

    A guest asks for towels mid-stay and the room is CLEAN; a stayover service is planned on a room
    a supervisor has already INSPECTED. Both need ``-> IN_PROGRESS`` out of a made-up room, and
    without those two edges in ``HOUSEKEEPING_FLOW`` the board can RAISE either task and never
    START it — the departure clean would be the only trigger that works, while the enum and the
    module guide present all three as first-class.

    Finishing lands the room on CLEAN whichever state it came from: somebody has been in the room
    since the supervisor signed it off, so an INSPECTED room needs inspecting again.
    """
    client = rooms_api.client
    room = await a_dirty_room(client)
    for status in walk_to:
        assert (await set_status(client, room["id"], status)).status_code == 200
    assert (await client.get(f"{ROOMS_URL}/{room['id']}")).json()[
        "housekeeping_status"
    ] == walk_to[-1].value

    task = await raise_task(client, room["id"], trigger=trigger)
    started = await move_task(client, task["id"], status=HousekeepingTaskStatus.IN_PROGRESS.value)
    assert started.status_code == 200, started.text
    assert (await client.get(f"{ROOMS_URL}/{room['id']}")).json()[
        "housekeeping_status"
    ] == HousekeepingStatus.IN_PROGRESS.value

    done = await move_task(client, task["id"], status=HousekeepingTaskStatus.DONE.value)
    assert done.status_code == 200, done.text
    assert (await client.get(f"{ROOMS_URL}/{room['id']}")).json()[
        "housekeeping_status"
    ] == HousekeepingStatus.CLEAN.value

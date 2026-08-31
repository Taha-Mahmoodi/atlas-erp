"""The rooms and housekeeping HTTP surface (PLAN 20.1).

A FOURTH hospitality router on the same ``/api/v1/hospitality`` prefix — the ``menu_router`` /
``reservation_router`` precedent (D-030/D-031) — because ``router.py`` is at 372 lines against the
STRUCTURE §8.4 cap and this is a different audience again: the property setting up the rooms it
sells and the supervisor running the housekeeping board, not the floor mid-service.

STAFF ONLY, deliberately. There is no website half here: a guest site asks about AVAILABILITY and
books, which is Phase 20 Task 4's counter, and the room master, the rate sheet and the housekeeping
board are all internal (a leaked website key must never be able to read that a property has taken
six rooms out of order). Task 4 adds its own website router in the Q6 shape.

Thin by construction: every route is a guard, a uow and a schema. Which housekeeping moves are
legal, and which of them move a room, live in ``service/rooms.py`` and ``service/housekeeping.py``
so the board and the manual endpoint cannot drift.
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.hospitality.constants import (
    HOSPITALITY_HOUSEKEEPING_MANAGE,
    HOSPITALITY_ROOMS_MANAGE,
    HOSPITALITY_ROOMS_READ,
    HousekeepingStatus,
    HousekeepingTaskStatus,
)
from app.modules.hospitality.rooms_schemas import (
    HousekeepingTaskCreate,
    HousekeepingTaskRead,
    HousekeepingTaskUpdate,
    RatePlanCreate,
    RatePlanRead,
    RatePlanUpdate,
    RoomCreate,
    RoomHousekeepingWrite,
    RoomRead,
    RoomTypeCreate,
    RoomTypeRead,
    RoomTypeUpdate,
    RoomUpdate,
)
from app.modules.hospitality.service import housekeeping, rate_plans, rooms

router = APIRouter(prefix="/api/v1/hospitality", tags=["hospitality-rooms"])

CursorParamsDep = Depends(cursor_params)
_ReadGuard = Depends(require_permission(HOSPITALITY_ROOMS_READ))
_ManageGuard = Depends(require_permission(HOSPITALITY_ROOMS_MANAGE))
_HousekeepingGuard = Depends(require_permission(HOSPITALITY_HOUSEKEEPING_MANAGE))
_TaskIdempotentDep = Depends(Idempotent("hospitality.housekeeping_task.create"))


# --- Room types ---------------------------------------------------------------


@router.get("/room-types", response_model=Page[RoomTypeRead], dependencies=[_ReadGuard])
async def list_room_types(
    current: CurrentUserDep, session: SessionDep, params: CursorParams = CursorParamsDep
) -> Page[RoomTypeRead]:
    """What the property sells a night of, in code order (D-014 keyset, never OFFSET)."""
    page = await rooms.list_room_types(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, RoomTypeRead)


@router.post(
    "/room-types", response_model=RoomTypeRead, status_code=201, dependencies=[_ManageGuard]
)
async def create_room_type(
    payload: RoomTypeCreate, current: CurrentUserDep, session: SessionDep
) -> RoomTypeRead:
    """Add a unit of sale. No idempotency key: a room type claims no number and registers no
    document, and a retry is refused by the per-tenant UNIQUE on its code."""
    holder: dict[str, RoomTypeRead] = {}

    async def work() -> None:
        room_type = await rooms.create_room_type(session, current.tenant_id, payload)
        await session.refresh(room_type)
        holder["read"] = RoomTypeRead.model_validate(room_type)

    await run_in_uow(session, work)
    return holder["read"]


@router.patch(
    "/room-types/{room_type_id}", response_model=RoomTypeRead, dependencies=[_ManageGuard]
)
async def update_room_type(
    room_type_id: uuid.UUID,
    payload: RoomTypeUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> RoomTypeRead:
    """Rename or re-capacity a type. ``code`` is immutable — every printed rate sheet quotes it."""
    holder: dict[str, RoomTypeRead] = {}

    async def work() -> None:
        room_type = await rooms.update_room_type(session, current.tenant_id, room_type_id, payload)
        await session.refresh(room_type)
        holder["read"] = RoomTypeRead.model_validate(room_type)

    await run_in_uow(session, work)
    return holder["read"]


# --- Rooms --------------------------------------------------------------------


@router.get("/rooms", response_model=Page[RoomRead], dependencies=[_ReadGuard])
async def list_rooms(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    room_type_id: uuid.UUID | None = None,
    housekeeping_status: HousekeepingStatus | None = None,
) -> Page[RoomRead]:
    """The property's rooms in number order, filterable by type and by condition — the two
    questions the front desk and housekeeping ask. Flat in the property's size (PERFORMANCE §2)."""
    page = await rooms.list_rooms(
        session,
        current.tenant_id,
        room_type_id=room_type_id,
        housekeeping_status=housekeeping_status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, RoomRead)


@router.post("/rooms", response_model=RoomRead, status_code=201, dependencies=[_ManageGuard])
async def create_room(
    payload: RoomCreate, current: CurrentUserDep, session: SessionDep
) -> RoomRead:
    """Add a physical room. It starts DIRTY — nobody has made it up yet."""
    holder: dict[str, RoomRead] = {}

    async def work() -> None:
        room = await rooms.create_room(session, current.tenant_id, payload)
        await session.refresh(room)
        holder["read"] = RoomRead.model_validate(room)

    await run_in_uow(session, work)
    return holder["read"]


@router.get("/rooms/{room_id}", response_model=RoomRead, dependencies=[_ReadGuard])
async def get_room(
    room_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RoomRead:
    return RoomRead.model_validate(await rooms.get_room(session, current.tenant_id, room_id))


@router.patch("/rooms/{room_id}", response_model=RoomRead, dependencies=[_ManageGuard])
async def update_room(
    room_id: uuid.UUID, payload: RoomUpdate, current: CurrentUserDep, session: SessionDep
) -> RoomRead:
    """Renumber a room or move it to another type. It CANNOT move the housekeeping status: the
    schema forbids the field, so the attempt is a 422 rather than a silent no-op."""
    holder: dict[str, RoomRead] = {}

    async def work() -> None:
        room = await rooms.update_room(session, current.tenant_id, room_id, payload)
        await session.refresh(room)
        holder["read"] = RoomRead.model_validate(room)

    await run_in_uow(session, work)
    return holder["read"]


@router.post(
    "/rooms/{room_id}/housekeeping-status",
    response_model=RoomRead,
    dependencies=[_HousekeepingGuard],
)
async def set_housekeeping_status(
    room_id: uuid.UUID,
    payload: RoomHousekeepingWrite,
    current: CurrentUserDep,
    session: SessionDep,
) -> RoomRead:
    """Move a room's condition — its own action under its OWN key, not ``rooms.manage``.

    Taking a room OUT_OF_ORDER stops it being sold, which Phase 20 Task 4 turns into a decrement of
    the per-date allotment: an operational decision with a revenue consequence, and a different
    authority from editing the room master (the ``ticket.settle`` precedent). No idempotency key —
    re-sending the same target status is refused by the transition table as a no-op move, so a
    retry can never double anything.
    """
    holder: dict[str, RoomRead] = {}

    async def work() -> None:
        # ``ApiModel`` sets ``use_enum_values``, so the schema hands over the STRING; coerced back
        # to the enum the service's transition table is keyed by.
        room = await rooms.set_housekeeping_status(
            session, current.tenant_id, room_id, HousekeepingStatus(payload.status)
        )
        await session.refresh(room)
        holder["read"] = RoomRead.model_validate(room)

    await run_in_uow(session, work)
    return holder["read"]


# --- Rate plans ---------------------------------------------------------------


@router.get("/rate-plans", response_model=Page[RatePlanRead], dependencies=[_ReadGuard])
async def list_rate_plans(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    room_type_id: uuid.UUID | None = None,
) -> Page[RatePlanRead]:
    """The rate sheet, optionally for one room type."""
    page = await rate_plans.list_rate_plans(
        session,
        current.tenant_id,
        room_type_id=room_type_id,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, RatePlanRead)


@router.post(
    "/rate-plans", response_model=RatePlanRead, status_code=201, dependencies=[_ManageGuard]
)
async def create_rate_plan(
    payload: RatePlanCreate, current: CurrentUserDep, session: SessionDep
) -> RatePlanRead:
    """Price a room type over a window. Manual in v1 — no rate calendar, no yield rules."""
    holder: dict[str, RatePlanRead] = {}

    async def work() -> None:
        plan = await rate_plans.create_rate_plan(session, current.tenant_id, payload)
        await session.refresh(plan)
        holder["read"] = RatePlanRead.model_validate(plan)

    await run_in_uow(session, work)
    return holder["read"]


@router.patch(
    "/rate-plans/{rate_plan_id}", response_model=RatePlanRead, dependencies=[_ManageGuard]
)
async def update_rate_plan(
    rate_plan_id: uuid.UUID,
    payload: RatePlanUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> RatePlanRead:
    """Re-price or re-window. Code, room type and currency are immutable: each of them changes what
    the stored amount MEANS, and a plan that needs a different one is a different plan."""
    holder: dict[str, RatePlanRead] = {}

    async def work() -> None:
        plan = await rate_plans.update_rate_plan(session, current.tenant_id, rate_plan_id, payload)
        await session.refresh(plan)
        holder["read"] = RatePlanRead.model_validate(plan)

    await run_in_uow(session, work)
    return holder["read"]


# --- The housekeeping board ---------------------------------------------------


@router.get(
    "/housekeeping-tasks", response_model=Page[HousekeepingTaskRead], dependencies=[_ReadGuard]
)
async def list_housekeeping_tasks(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    room_id: uuid.UUID | None = None,
    status: HousekeepingTaskStatus | None = None,
) -> Page[HousekeepingTaskRead]:
    """THE BOARD, newest first — a supervisor reads what has just come in. Reading it is
    ``rooms.read``: an attendant's device needs the room list and the board together."""
    page = await housekeeping.list_tasks(
        session,
        current.tenant_id,
        room_id=room_id,
        status=status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, HousekeepingTaskRead)


@router.post(
    "/housekeeping-tasks",
    response_model=HousekeepingTaskRead,
    status_code=201,
    dependencies=[_HousekeepingGuard],
)
async def raise_housekeeping_task(
    payload: HousekeepingTaskCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _TaskIdempotentDep,
) -> HousekeepingTaskRead:
    """Raise work on a room.

    IDEMPOTENT (D-013): a task registers a document and burns a gapless ``HKT-`` number, so a
    housekeeper's flaky tablet retrying must get the first task back rather than double the board.
    """
    holder: dict[str, HousekeepingTaskRead] = {}

    async def work() -> None:
        task = await housekeeping.create_task(session, current.tenant_id, payload)
        await session.refresh(task)
        holder["read"] = await idem.capture(
            HousekeepingTaskRead.model_validate(task), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]


@router.get(
    "/housekeeping-tasks/{task_id}",
    response_model=HousekeepingTaskRead,
    dependencies=[_ReadGuard],
)
async def get_housekeeping_task(
    task_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> HousekeepingTaskRead:
    task = await housekeeping.get_task(session, current.tenant_id, task_id)
    return HousekeepingTaskRead.model_validate(task)


@router.patch(
    "/housekeeping-tasks/{task_id}",
    response_model=HousekeepingTaskRead,
    dependencies=[_HousekeepingGuard],
)
async def update_housekeeping_task(
    task_id: uuid.UUID,
    payload: HousekeepingTaskUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> HousekeepingTaskRead:
    """Move the work on, hand it to somebody else, or both.

    Starting the work makes the room IN_PROGRESS and finishing it makes the room CLEAN — through
    ``rooms.set_housekeeping_status``, so a room the property has taken OUT_OF_ORDER refuses the
    move and the whole request fails. Cancelling moves only the task: a room nobody cleaned is
    still dirty.
    """
    holder: dict[str, HousekeepingTaskRead] = {}

    async def work() -> None:
        task = await housekeeping.update_task(session, current.tenant_id, task_id, payload)
        await session.refresh(task)
        holder["read"] = HousekeepingTaskRead.model_validate(task)

    await run_in_uow(session, work)
    return holder["read"]

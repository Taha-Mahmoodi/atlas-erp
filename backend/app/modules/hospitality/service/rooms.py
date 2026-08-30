"""The rooms masters and the one state machine among them (PLAN 20.1).

Ordinary tenant-scoped master CRUD in the ``inventory/service/items.py`` anatomy — a friendly
``*_conflict`` before the DB UNIQUE would raise, a tenant-scoped getter that 404s rather than
leaking, keyset-paginated reads (D-014) — for three masters, plus ``set_housekeeping_status``,
which is not CRUD.

**Why the reads live here and not in ``queries.py``.** STRUCTURE §5 reserves ``queries.py`` for the
reads OTHER modules import, nothing imports hospitality, and that file is at 362 lines against the
§8.4 cap. The Phase 19 note in its own docstring already says reads land wherever there is room;
these three sit next to the writes they page over.

**``set_housekeeping_status`` is the file's whole point.** Phase 20 Task 4 hangs the per-date
allotment counter off OUT_OF_ORDER — a room taken out of service must lower ``rooms_sellable`` on
the future dates it covers, and coming back must raise it. That is a set-based counter touch, and
it only works if the column has ONE writer. So: the update schema cannot carry the column, the
housekeeping board calls this function rather than writing the room itself, and Task 4 adds its
``adjust_allotment`` call inside the ``if`` below without touching any caller.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.hospitality.constants import HOUSEKEEPING_FLOW, HousekeepingStatus
from app.modules.hospitality.models import RatePlan, Room, RoomType
from app.modules.hospitality.rooms_schemas import (
    RatePlanCreate,
    RatePlanUpdate,
    RoomCreate,
    RoomTypeCreate,
    RoomTypeUpdate,
    RoomUpdate,
)


async def _require_code_free(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    model: type[RoomType] | type[RatePlan],
    code: str,
    *,
    label: str,
    error_code: str,
) -> None:
    """Friendly 409 before the per-tenant UNIQUE would raise (the ``create_item`` shape). The
    constraint is still the backstop — this only turns a duplicate into a readable error instead
    of an IntegrityError the caller cannot act on."""
    taken = (
        await session.execute(
            select(model.id).where(model.tenant_id == tenant_id, model.code == code)
        )
    ).first()
    if taken is not None:
        raise ConflictError(
            message=f"A {label} with code {code} already exists",
            code=error_code,
            details={"code": code},
        )


# --- Room types ---------------------------------------------------------------


async def get_room_type(
    session: AsyncSession, tenant_id: uuid.UUID, room_type_id: uuid.UUID
) -> RoomType:
    """The type, or 404 ``hospitality.room_type_not_found`` — including for another tenant's id,
    which is what stops a room being hung off somebody else's inventory."""
    room_type = await session.get(RoomType, room_type_id)
    if room_type is None or room_type.tenant_id != tenant_id:
        raise NotFoundError(
            message="Room type not found", code="hospitality.room_type_not_found"
        )
    return room_type


async def create_room_type(
    session: AsyncSession, tenant_id: uuid.UUID, payload: RoomTypeCreate
) -> RoomType:
    await _require_code_free(
        session,
        tenant_id,
        RoomType,
        payload.code,
        label="room type",
        error_code="hospitality.room_type_code_conflict",
    )
    room_type = RoomType(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        base_capacity=payload.base_capacity,
    )
    session.add(room_type)
    await session.flush()
    return room_type


async def update_room_type(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    room_type_id: uuid.UUID,
    payload: RoomTypeUpdate,
) -> RoomType:
    """Partial update (D-010: mutate the loaded object so the audit listener sees a diff)."""
    room_type = await get_room_type(session, tenant_id, room_type_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(room_type, field, value)
    await session.flush()
    return room_type


async def list_room_types(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[RoomType]:
    """Every type the property sells, in its own code order (D-014 keyset, never OFFSET)."""
    stmt = select(RoomType).where(RoomType.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(RoomType.code, SortDirection.ASC)],
        pk=RoomType.id,
        cursor=cursor,
        limit=limit,
    )


# --- Rooms --------------------------------------------------------------------


async def get_room(session: AsyncSession, tenant_id: uuid.UUID, room_id: uuid.UUID) -> Room:
    """The room, or 404 ``hospitality.room_not_found``."""
    room = await session.get(Room, room_id)
    if room is None or room.tenant_id != tenant_id:
        raise NotFoundError(message="Room not found", code="hospitality.room_not_found")
    return room


async def create_room(
    session: AsyncSession, tenant_id: uuid.UUID, payload: RoomCreate
) -> Room:
    """Add a physical room. It starts DIRTY (see ``HousekeepingStatus``): nobody has made it up,
    and starting sellable is the assumption that walks a guest into an unserviced room."""
    taken = (
        await session.execute(
            select(Room.id).where(
                Room.tenant_id == tenant_id, Room.room_number == payload.room_number
            )
        )
    ).first()
    if taken is not None:
        raise ConflictError(
            message=f"Room {payload.room_number} already exists",
            code="hospitality.room_number_conflict",
            details={"room_number": payload.room_number},
        )
    await get_room_type(session, tenant_id, payload.room_type_id)
    room = Room(
        tenant_id=tenant_id,
        room_number=payload.room_number,
        room_type_id=payload.room_type_id,
        housekeeping_status=HousekeepingStatus.DIRTY.value,
    )
    session.add(room)
    await session.flush()
    return room


async def update_room(
    session: AsyncSession, tenant_id: uuid.UUID, room_id: uuid.UUID, payload: RoomUpdate
) -> Room:
    """Renumber a room or move it to another type. It CANNOT move the housekeeping status — the
    schema has no such field, so the attempt is a 422 rather than a silent no-op."""
    room = await get_room(session, tenant_id, room_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("room_type_id") is not None:
        await get_room_type(session, tenant_id, data["room_type_id"])
    for field, value in data.items():
        setattr(room, field, value)
    await session.flush()
    return room


async def set_housekeeping_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    room_id: uuid.UUID,
    to_status: HousekeepingStatus,
) -> Room:
    """Move a room's condition — the ONLY writer of ``Room.housekeeping_status``.

    The legality of the move is ``HOUSEKEEPING_FLOW``'s call, not a caller's, so the manual
    endpoint and the housekeeping board cannot disagree about whether a dirty room can be declared
    clean (it cannot: somebody has to be in it).

    **This is the Task 4 hook.** Crossing into or out of ``HOUSEKEEPING_UNSELLABLE`` is the moment
    the property's sellable-room count changes, so Task 4's ``adjust_allotment`` call goes in the
    branch below — comparing ``current`` and ``to_status`` against that set — and every caller in
    this module already routes through here. Nothing above needs to change.
    """
    room = await get_room(session, tenant_id, room_id)
    current = HousekeepingStatus(room.housekeeping_status)
    if to_status not in HOUSEKEEPING_FLOW[current]:
        raise ConflictError(
            message=f"A room cannot move from {current.value} to {to_status.value}",
            code="hospitality.room_not_transitionable",
            details={
                "room_id": str(room_id),
                "housekeeping_status": current.value,
                "requested_status": to_status.value,
            },
        )
    room.housekeeping_status = to_status.value
    await session.flush()
    return room


async def list_rooms(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    room_type_id: uuid.UUID | None = None,
    housekeeping_status: HousekeepingStatus | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Room]:
    """The property's rooms in number order — the two filters the board actually uses.

    ONE statement whatever the property's size (PERFORMANCE §2): both filters are served by the
    tenant-leading indexes declared on the model, and nothing is loaded per row.
    """
    stmt = select(Room).where(Room.tenant_id == tenant_id)
    if room_type_id is not None:
        stmt = stmt.where(Room.room_type_id == room_type_id)
    if housekeeping_status is not None:
        stmt = stmt.where(Room.housekeeping_status == housekeeping_status.value)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Room.room_number, SortDirection.ASC)],
        pk=Room.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(room_type_id, housekeeping_status),
    )


# --- Rate plans ---------------------------------------------------------------


async def get_rate_plan(
    session: AsyncSession, tenant_id: uuid.UUID, rate_plan_id: uuid.UUID
) -> RatePlan:
    """The plan, or 404 ``hospitality.rate_plan_not_found``."""
    plan = await session.get(RatePlan, rate_plan_id)
    if plan is None or plan.tenant_id != tenant_id:
        raise NotFoundError(message="Rate plan not found", code="hospitality.rate_plan_not_found")
    return plan


def _require_window(valid_from: date, valid_to: date | None) -> None:
    """A validity window is the whole of v1's rate calendar, so the one thing it must not be is
    backwards — a window covering no night is a rate nothing can ever resolve. The DB CHECK is the
    backstop; this is the readable refusal."""
    if valid_to is not None and valid_to < valid_from:
        raise ValidationFailedError(
            message="A rate plan cannot end before it starts",
            code="hospitality.rate_plan_window_invalid",
            details={"valid_from": str(valid_from), "valid_to": str(valid_to)},
        )


async def create_rate_plan(
    session: AsyncSession, tenant_id: uuid.UUID, payload: RatePlanCreate
) -> RatePlan:
    await _require_code_free(
        session,
        tenant_id,
        RatePlan,
        payload.code,
        label="rate plan",
        error_code="hospitality.rate_plan_code_conflict",
    )
    _require_window(payload.valid_from, payload.valid_to)
    await get_room_type(session, tenant_id, payload.room_type_id)
    plan = RatePlan(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        room_type_id=payload.room_type_id,
        nightly_amount=payload.nightly_amount,
        currency_code=payload.currency_code.upper(),
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    session.add(plan)
    await session.flush()
    return plan


async def update_rate_plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rate_plan_id: uuid.UUID,
    payload: RatePlanUpdate,
) -> RatePlan:
    """Re-price or re-window. The window is re-checked against whichever half is NOT being sent,
    so shortening a plan cannot leave it backwards."""
    plan = await get_rate_plan(session, tenant_id, rate_plan_id)
    data = payload.model_dump(exclude_unset=True)
    _require_window(
        data.get("valid_from", plan.valid_from), data.get("valid_to", plan.valid_to)
    )
    for field, value in data.items():
        setattr(plan, field, value)
    await session.flush()
    return plan


async def list_rate_plans(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    room_type_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[RatePlan]:
    """The property's rates in code order, optionally for one room type."""
    stmt = select(RatePlan).where(RatePlan.tenant_id == tenant_id)
    if room_type_id is not None:
        stmt = stmt.where(RatePlan.room_type_id == room_type_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(RatePlan.code, SortDirection.ASC)],
        pk=RatePlan.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(room_type_id),
    )

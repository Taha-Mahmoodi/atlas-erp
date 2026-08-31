"""The room type, the physical room, and the one state machine among them (PLAN 20.1).

The RATE PLAN moved to ``rate_plans.py`` when PLAN 20.2 added the allotment hook below and this
file reached the STRUCTURE §8.4 cap — its own aggregate (STRUCTURE §3), and the only one of the
three masters that carries money. It imports :func:`require_code_free`, :func:`sent_fields` and
:func:`get_room_type` from here, which is why those two are public rather than underscored: they
are the master-CRUD plumbing the hotel side shares, and one copy each is the point of them.

Ordinary tenant-scoped master CRUD in the ``inventory/service/items.py`` anatomy — a friendly
``*_conflict`` before the DB UNIQUE would raise, a tenant-scoped getter that 404s rather than
leaking, keyset-paginated reads (D-014) — for two masters, plus ``set_housekeeping_status``,
which is not CRUD.

**Why the reads live here and not in ``queries.py``.** STRUCTURE §5 reserves ``queries.py`` for the
reads OTHER modules import, nothing imports hospitality, and that file is at 362 lines against the
§8.4 cap. The Phase 19 note in its own docstring already says reads land wherever there is room;
each sits next to the writes it pages over.

**``set_housekeeping_status`` is the file's whole point.** Phase 20 Task 4 hangs the per-date
allotment counter off OUT_OF_ORDER — a room taken out of service must lower ``rooms_sellable`` on
the future dates it covers, and coming back must raise it. That is a set-based counter touch, and
it only works if the column has ONE writer. So: the update schema cannot carry the column, the
housekeeping board calls this function rather than writing the room itself, and PLAN 20.2 added
its ``allotment`` call inside that function without touching a single caller (D-085).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import ApiModel, Page
from app.modules.hospitality.constants import (
    HOUSEKEEPING_FLOW,
    HOUSEKEEPING_UNSELLABLE,
    HousekeepingStatus,
)
from app.modules.hospitality.models import RatePlan, Room, RoomType
from app.modules.hospitality.rooms_schemas import (
    RoomCreate,
    RoomTypeCreate,
    RoomTypeUpdate,
    RoomUpdate,
)
from app.modules.hospitality.service import allotment


async def require_code_free(
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


async def _require_room_number_free(
    session: AsyncSession, tenant_id: uuid.UUID, room_number: str
) -> None:
    """The same friendly 409 for the room's own unique column, which is not called ``code``.

    Called by BOTH ``create_room`` and ``update_room``: ``room_number`` is the one code-like column
    in this file that stays MUTABLE (a refit renumbers a floor; a room type's code and a rate
    plan's code do not move, because they are quoted on rate sheets), so a renumber onto a number
    already on a door is the same collision as creating a second one. Without this on the update
    path ``uq_hsp_rooms_tenant_id_room_number`` is reached as an unhandled IntegrityError — a 500
    on a value the caller supplied.
    """
    taken = (
        await session.execute(
            select(Room.id).where(Room.tenant_id == tenant_id, Room.room_number == room_number)
        )
    ).first()
    if taken is not None:
        raise ConflictError(
            message=f"Room {room_number} already exists",
            code="hospitality.room_number_conflict",
            details={"room_number": room_number},
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
    await require_code_free(
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


def sent_fields(payload: ApiModel, *, nullable: frozenset[str] = frozenset()) -> dict[str, object]:
    """The fields a PATCH actually sent, with explicit ``null`` dropped unless the column means
    something by it.

    ``exclude_unset`` distinguishes "not sent" from "sent as null", but every updatable column in
    the hotel masters except ``RatePlanUpdate.valid_to`` is NOT NULL — so a client sending
    ``{"name": null}`` would otherwise reach the flush and surface as a 500 IntegrityError, or
    (for ``valid_from``) crash in ``rate_plans._require_window`` comparing a date against None.
    Dropping the null makes it a no-op field, which is what a partial update of a required column
    can honestly mean.

    One helper rather than the same comprehension in three updaters: this bug was fixed in
    ``update_room`` alone and stayed live in the two siblings. Public so ``rate_plans`` shares it.
    """
    return {
        field: value
        for field, value in payload.model_dump(exclude_unset=True).items()
        if value is not None or field in nullable
    }


async def update_room_type(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    room_type_id: uuid.UUID,
    payload: RoomTypeUpdate,
) -> RoomType:
    """Partial update (D-010: mutate the loaded object so the audit listener sees a diff)."""
    room_type = await get_room_type(session, tenant_id, room_type_id)
    for field, value in sent_fields(payload).items():
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
    await _require_room_number_free(session, tenant_id, payload.room_number)
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
    schema has no such field, so the attempt is a 422 rather than a silent no-op.

    Both columns are NOT NULL, so an explicitly-sent ``null`` is dropped rather than flushed into an
    IntegrityError; ``exclude_unset`` is what distinguishes "not sent" from "sent as null", and
    neither field has a meaning for null the way ``RatePlanUpdate.valid_to`` does.
    """
    room = await get_room(session, tenant_id, room_id)
    data = sent_fields(payload)
    if "room_type_id" in data:
        await get_room_type(session, tenant_id, data["room_type_id"])
    if "room_number" in data and data["room_number"] != room.room_number:
        await _require_room_number_free(session, tenant_id, data["room_number"])
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

    **The allotment hook is here (D-085, PLAN 20.2).** Crossing into or out of
    ``HOUSEKEEPING_UNSELLABLE`` is the moment the property's sellable-room count changes, so the
    counter move is written once, in the branch below, against the SAME set ``allotment`` seeds a
    new night's ``rooms_sellable`` from. Only the crossing counts: DIRTY -> IN_PROGRESS -> CLEAN
    is the whole of an ordinary day and moves nothing on sale.

    Taking the last room off sale on a night already fully sold is REFUSED
    (``hospitality.room_type_sold_out``), not silently oversold — ``allotment.adjust_sellable``
    is where that is argued. The refusal is raised before the column moves, so it leaves the room
    exactly as it was.
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
    was_unsellable = current in HOUSEKEEPING_UNSELLABLE
    if was_unsellable != (to_status in HOUSEKEEPING_UNSELLABLE):
        await allotment.adjust_sellable(
            session,
            tenant_id,
            room.room_type_id,
            1 if was_unsellable else -1,
            on_or_after=date.today(),
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

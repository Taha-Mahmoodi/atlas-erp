"""The housekeeping task document and its lifecycle (PLAN 20.1).

Its own service file rather than more of ``rooms.py``: STRUCTURE §3 splits ``service/`` one file
per AGGREGATE, and a task is a D-012 document with a registry row, a gapless number and a doc-flow
edge — a different aggregate from the three masters next door, and together they would be over the
§8.4 cap.

**The task never writes ``Room.housekeeping_status`` itself.** Starting the work moves the room to
IN_PROGRESS and finishing it moves the room to CLEAN, but both go through
``rooms.set_housekeeping_status``, so the room's transition table decides — which is why starting
work on a room the property has taken OUT_OF_ORDER is refused with the ROOM's error code, and why
Phase 20 Task 4's allotment hook cannot be bypassed by driving the board instead of the room.

Cancelling never makes a room clean — a room nobody cleaned is still dirty, and pretending
otherwise would put an unserviced room back on sale. It does put a room the cancelled task had
STARTED back to DIRTY, because the alternative strands it in IN_PROGRESS with no open task and no
transition left that reaches it.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError
from app.core.numbering import claim_number, ensure_sequence
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.hospitality.constants import (
    HOUSEKEEPING_TASK_DOC_TYPE,
    HOUSEKEEPING_TASK_FLOW,
    HOUSEKEEPING_TASK_NUMBER_PADDING,
    HOUSEKEEPING_TASK_NUMBER_PREFIX,
    HOUSEKEEPING_TASK_SEQUENCE_NAME,
    HOUSEKEEPING_TRIGGERED_BY_LINK,
    HousekeepingStatus,
    HousekeepingTaskStatus,
    HousekeepingTrigger,
)
from app.modules.hospitality.models import HousekeepingTask
from app.modules.hospitality.rooms_schemas import (
    HousekeepingTaskCreate,
    HousekeepingTaskUpdate,
)
from app.modules.hospitality.service import rooms

# What the ROOM does when the WORK reaches a state. Declared once rather than branched at each
# transition, so "finishing a clean makes the room clean" is a single fact.
#
# CANCELLED is deliberately absent and handled separately below: its effect is CONDITIONAL, because
# the room's condition depends on whether this task had started. A mapping cannot express that, and
# an unconditional CANCELLED -> DIRTY would refuse (DIRTY -> DIRTY is not a legal move) every time a
# supervisor cancelled a task nobody had picked up yet.
_ROOM_EFFECT: dict[HousekeepingTaskStatus, HousekeepingStatus] = {
    HousekeepingTaskStatus.IN_PROGRESS: HousekeepingStatus.IN_PROGRESS,
    HousekeepingTaskStatus.DONE: HousekeepingStatus.CLEAN,
}


async def get_task(
    session: AsyncSession, tenant_id: uuid.UUID, task_id: uuid.UUID
) -> HousekeepingTask:
    """The task, or 404 ``hospitality.housekeeping_task_not_found``."""
    task = await session.get(HousekeepingTask, task_id)
    if task is None or task.tenant_id != tenant_id:
        raise NotFoundError(
            message="Housekeeping task not found",
            code="hospitality.housekeeping_task_not_found",
        )
    return task


async def create_task(
    session: AsyncSession, tenant_id: uuid.UUID, payload: HousekeepingTaskCreate
) -> HousekeepingTask:
    """Raise work on a room: validate, register the document, claim its number, link the cause.

    ORDER MATTERS, the ``create_reservation`` reason: the room is resolved BEFORE ``claim_number``,
    because the number claim holds the tenant's sequence row lock until commit by construction
    (D-012 gaplessness) and a refused request must never have taken it.

    ``predecessor_document_id`` is the doc-flow hook. Task 4's check-out passes the departing
    reservation's registry id and the chain then reads reservation -> housekeeping task; a task a
    supervisor raises by hand simply has no predecessor, which is an ordinary root document.
    """
    await rooms.get_room(session, tenant_id, payload.room_id)
    if payload.predecessor_document_id is not None:
        # Validated here rather than left to the composite tenant FK on the edge: an unknown or
        # foreign registry id would otherwise surface as an IntegrityError (a 500) on a value the
        # caller supplied, which is a 404 in every other tenant-scoped lookup in this module.
        predecessor = await session.get(docflow.Document, payload.predecessor_document_id)
        if predecessor is None or predecessor.tenant_id != tenant_id:
            raise NotFoundError(
                message="Predecessor document not found", code="core.document_not_found"
            )

    task_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        HOUSEKEEPING_TASK_DOC_TYPE,
        task_id,
        doc_number=None,
        status=HousekeepingTaskStatus.OPEN.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        HOUSEKEEPING_TASK_SEQUENCE_NAME,
        HOUSEKEEPING_TASK_NUMBER_PREFIX,
        HOUSEKEEPING_TASK_NUMBER_PADDING,
        year_reset=True,
    )
    # Numbered on TODAY's date, not a business date: Task 6 introduces the business date and the
    # night audit that rolls it, and until it exists the calendar day the work was raised on is the
    # only honest answer (``create_ticket``'s default, same call).
    number = await claim_number(
        session, tenant_id, HOUSEKEEPING_TASK_SEQUENCE_NAME, on_date=date.today()
    )
    task = HousekeepingTask(
        id=task_id,
        tenant_id=tenant_id,
        document_id=document.id,
        task_number=number,
        room_id=payload.room_id,
        trigger=HousekeepingTrigger(payload.trigger).value,
        status=HousekeepingTaskStatus.OPEN.value,
        assigned_user_id=payload.assigned_user_id,
        notes=payload.notes,
    )
    session.add(task)
    await session.flush()
    await docflow.set_document_status(
        session,
        tenant_id,
        document.id,
        doc_number=number,
        status=HousekeepingTaskStatus.OPEN.value,
    )
    if payload.predecessor_document_id is not None:
        await docflow.link_documents(
            session,
            tenant_id,
            payload.predecessor_document_id,
            document.id,
            HOUSEKEEPING_TRIGGERED_BY_LINK,
        )
    return task


async def update_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: HousekeepingTaskUpdate,
) -> HousekeepingTask:
    """Move the work on, hand it to somebody else, or both — one call (the ``amend_reservation``
    shape), because a supervisor reassigning a room mid-shift is doing one thing.

    The ROOM moves FIRST when the status moves. That ordering is the point: if the room refuses the
    move (it is OUT_OF_ORDER, and OUT_OF_ORDER leaves only to DIRTY), the whole request fails and
    the task stays exactly where it was, rather than recording work on a room that is not in
    service. ``HOUSEKEEPING_TASK_FLOW`` guards the task's own move, so DONE stays terminal.
    """
    task = await get_task(session, tenant_id, task_id)
    data = payload.model_dump(exclude_unset=True)

    if payload.status is not None:
        # ``ApiModel`` sets ``use_enum_values``, so the schema hands over the STRING; coerced back
        # here so the transition table is keyed by the enum it is declared with.
        to_status = HousekeepingTaskStatus(payload.status)
        current = HousekeepingTaskStatus(task.status)
        if to_status not in HOUSEKEEPING_TASK_FLOW[current]:
            raise ConflictError(
                message=f"A task cannot move from {current.value} to {to_status.value}",
                code="hospitality.housekeeping_task_not_transitionable",
                details={
                    "task_id": str(task_id),
                    "status": current.value,
                    "requested_status": to_status.value,
                },
            )
        room_status = _ROOM_EFFECT.get(to_status)
        if to_status is HousekeepingTaskStatus.CANCELLED:
            # An attendant pulled off a room MID-CLEAN leaves it dirty, not half-clean: without
            # this the room stays IN_PROGRESS forever, invisible to the board and unsellable.
            # A task cancelled before anybody started it changes nothing.
            room = await rooms.get_room(session, tenant_id, task.room_id)
            if room.housekeeping_status == HousekeepingStatus.IN_PROGRESS.value:
                room_status = HousekeepingStatus.DIRTY
        if room_status is not None:
            await rooms.set_housekeeping_status(session, tenant_id, task.room_id, room_status)
        task.status = to_status.value
        await docflow.set_document_status(
            session, tenant_id, task.document_id, status=to_status.value
        )
    if "assigned_user_id" in data:
        task.assigned_user_id = data["assigned_user_id"]
    await session.flush()
    return task


async def list_tasks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    room_id: uuid.UUID | None = None,
    status: HousekeepingTaskStatus | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[HousekeepingTask]:
    """THE BOARD: the day's work, newest first — a supervisor reads what has just come in.

    ONE statement whatever the board's size (PERFORMANCE §2): both filters are served by the
    tenant-leading indexes on the model, and nothing is loaded per row.
    """
    stmt = select(HousekeepingTask).where(HousekeepingTask.tenant_id == tenant_id)
    if room_id is not None:
        stmt = stmt.where(HousekeepingTask.room_id == room_id)
    if status is not None:
        stmt = stmt.where(HousekeepingTask.status == status.value)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(HousekeepingTask.created_at, SortDirection.DESC)],
        pk=HousekeepingTask.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(room_id, status),
    )

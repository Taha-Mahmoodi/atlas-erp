"""The STAFF reservation book (Phase 21): take a booking, move it, seat it, close it out — plus the
pacing configuration and the manager's per-slot capacity override.

A sibling router file rather than more of ``router.py``, the ``finance/ap_router.py`` precedent
(D-030/D-031), and split from ``reservation_website_router.py`` by PRINCIPAL exactly as
``router.py`` is split from ``website_router.py``. Thin by construction: every route is a guard, a
uow and a schema — which transitions are legal, and which of them move the pacing counter, live in
``service/reservations.py`` and ``service/pacing.py`` so the website and the book cannot drift.

**Two permissions, and the split is the same one the ticket surface makes.**
``hospitality.reservation.read`` is the book: every guest's name and contact detail for the night,
which is why the website's credential does not hold it. ``.manage`` is everything that changes a
booking or the room's capacity. A host needs both; a screen on the pass needs only the first.

**Staff book through the SAME gate as the website** (``create_reservation``), which is the
availability module's lesson made structural: one counter, one place that decrements it. A phone
booking that skipped the gate would be exactly the oversell the gate exists to prevent, arriving
from the one direction nobody tests.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.hospitality import queries
from app.modules.hospitality.constants import (
    HOSPITALITY_RESERVATION_MANAGE,
    HOSPITALITY_RESERVATION_READ,
    SLOT_MINUTES,
    ReservationStatus,
)
from app.modules.hospitality.models import TableReservation
from app.modules.hospitality.reservation_schemas import (
    ReservationSettingsRead,
    ReservationSettingsWrite,
    ServiceSlotCapacityWrite,
    ServiceSlotRead,
    TableReservationAmend,
    TableReservationCreate,
    TableReservationRead,
    TableReservationSeat,
)
from app.modules.hospitality.service import pacing, reservations

router = APIRouter(prefix="/api/v1/hospitality", tags=["hospitality"])

CursorParamsDep = Depends(cursor_params)
_ReadGuard = Depends(require_permission(HOSPITALITY_RESERVATION_READ))
_ManageGuard = Depends(require_permission(HOSPITALITY_RESERVATION_MANAGE))
# A namespace of its own, distinct from the website's booking route: D-013 reservations are scoped
# per endpoint, so a host's retry and a website's can never collide on the same client-chosen key.
_CreateIdempotentDep = Depends(Idempotent("hospitality.table_reservation.create"))


def _settings_read(settings: pacing.ResolvedSettings) -> ReservationSettingsRead:
    """Render the resolved configuration, defaults included, plus the constant grid step so a client
    never hard-codes the quarter-hour it renders against."""
    return ReservationSettingsRead(
        service_open=settings.service_open,
        service_close=settings.service_close,
        default_covers_max=settings.default_covers_max,
        default_parties_max=settings.default_parties_max,
        min_party=settings.min_party,
        max_party=settings.max_party,
        booking_horizon_days=settings.booking_horizon_days,
        slot_minutes=SLOT_MINUTES,
    )


# --- The book -----------------------------------------------------------------


@router.get(
    "/reservations", response_model=Page[TableReservationRead], dependencies=[_ReadGuard]
)
async def list_reservations(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    service_date: date | None = None,
    status: ReservationStatus | None = None,
) -> Page[TableReservationRead]:
    """THE BOOK: a service's bookings in slot order (D-014 keyset, never OFFSET).

    Ascending, unlike the ticket list's newest-first — a host reads the book FORWARD through the
    evening, so the natural first page is the start of service. No ETag: the book changes
    continuously through a shift (the journal-entry precedent).
    """
    page = await queries.list_reservations(
        session,
        current.tenant_id,
        service_date=service_date,
        status=status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, TableReservationRead)


@router.get(
    "/reservations/{reservation_id}",
    response_model=TableReservationRead,
    dependencies=[_ReadGuard],
)
async def get_reservation(
    reservation_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> TableReservationRead:
    reservation = await reservations.get_reservation(session, current.tenant_id, reservation_id)
    return TableReservationRead.model_validate(reservation)


@router.post(
    "/reservations",
    response_model=TableReservationRead,
    status_code=201,
    dependencies=[_ManageGuard],
)
async def take_reservation(
    payload: TableReservationCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdempotentDep,
) -> TableReservationRead:
    """A host takes a phone booking — through the SAME pacing gate the website goes through.

    IDEMPOTENT (D-013): a booking registers a document and burns a gapless RSV- number, so a
    retried request must return the first booking rather than hold the table twice.
    """
    holder: dict[str, TableReservationRead] = {}

    async def work() -> None:
        reservation = await reservations.create_reservation(session, current.tenant_id, payload)
        await session.refresh(reservation)
        holder["read"] = await idem.capture(
            TableReservationRead.model_validate(reservation), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]


@router.patch(
    "/reservations/{reservation_id}",
    response_model=TableReservationRead,
    dependencies=[_ManageGuard],
)
async def amend_reservation(
    reservation_id: uuid.UUID,
    payload: TableReservationAmend,
    current: CurrentUserDep,
    session: SessionDep,
) -> TableReservationRead:
    """"They're six now, and can they come at eight instead?" — the commonest thing a host does
    after taking a booking, and the one that has to touch the counter correctly: a size change takes
    the delta on the same locked row, a time change releases the old slot and books the new one in
    ONE transaction. Refused once the slot has started (409) or the booking has left CONFIRMED."""
    holder: dict[str, TableReservationRead] = {}

    async def work() -> None:
        reservation = await reservations.amend_reservation(
            session,
            current.tenant_id,
            reservation_id,
            party_size=payload.party_size,
            service_date=payload.service_date,
            slot_start=payload.slot_start,
        )
        await session.refresh(reservation)
        holder["read"] = TableReservationRead.model_validate(reservation)

    await run_in_uow(session, work)
    return holder["read"]


@router.post(
    "/reservations/{reservation_id}/seat",
    response_model=TableReservationRead,
    dependencies=[_ManageGuard],
)
async def seat_reservation(
    reservation_id: uuid.UUID,
    payload: TableReservationSeat,
    current: CurrentUserDep,
    session: SessionDep,
) -> TableReservationRead:
    """Sit the party down: marks SEATED and opens the check they will order onto, doc-flow-linked so
    reservation → ticket → (Phase 20 folio) renders as one chain. No counter effect — the covers
    were taken when the booking was confirmed."""
    holder: dict[str, TableReservationRead] = {}

    async def work() -> None:
        reservation = await reservations.seat_reservation(
            session, current.tenant_id, reservation_id, table_code=payload.table_code
        )
        await session.refresh(reservation)
        holder["read"] = TableReservationRead.model_validate(reservation)

    await run_in_uow(session, work)
    return holder["read"]


async def _run_transition(
    session: SessionDep,
    tenant_id: uuid.UUID,
    reservation_id: uuid.UUID,
    action: Callable[[SessionDep, uuid.UUID, uuid.UUID], Awaitable[TableReservation]],
) -> TableReservationRead:
    """One lifecycle move in its own uow. The three routes below differ only in which service
    function they name, and each of those owns its own counter rule (finding 4) — so there is
    nothing left here to get wrong except forgetting the uow."""
    holder: dict[str, TableReservationRead] = {}

    async def work() -> None:
        reservation = await action(session, tenant_id, reservation_id)
        await session.refresh(reservation)
        holder["read"] = TableReservationRead.model_validate(reservation)

    await run_in_uow(session, work)
    return holder["read"]


@router.post(
    "/reservations/{reservation_id}/no-show",
    response_model=TableReservationRead,
    dependencies=[_ManageGuard],
)
async def mark_no_show(
    reservation_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> TableReservationRead:
    """They never came. Terminal, and it releases NOTHING: it is recorded at or after the slot, when
    there is nobody left to resell the covers to."""
    return await _run_transition(
        session, current.tenant_id, reservation_id, reservations.mark_no_show
    )


@router.post(
    "/reservations/{reservation_id}/cancel",
    response_model=TableReservationRead,
    dependencies=[_ManageGuard],
)
async def cancel_reservation(
    reservation_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> TableReservationRead:
    """Called off. Gives the capacity back IF the slot has not started yet; refused once the party
    is SEATED, when the correction wanted is on their check instead."""
    return await _run_transition(
        session, current.tenant_id, reservation_id, reservations.cancel_reservation
    )


@router.post(
    "/reservations/{reservation_id}/complete",
    response_model=TableReservationRead,
    dependencies=[_ManageGuard],
)
async def complete_reservation(
    reservation_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> TableReservationRead:
    """They ate and left. Terminal, bookkeeping only — this is what clears the party off tonight's
    book without pretending they never came."""
    return await _run_transition(
        session, current.tenant_id, reservation_id, reservations.complete_reservation
    )


# --- Capacity -----------------------------------------------------------------


@router.get(
    "/reservation-settings", response_model=ReservationSettingsRead, dependencies=[_ReadGuard]
)
async def read_reservation_settings(
    current: CurrentUserDep, session: SessionDep
) -> ReservationSettingsRead:
    """The pacing configuration, defaults applied. A property that has never written one still gets
    a complete answer — absence is the default, not a "not set up yet" state."""
    return _settings_read(await pacing.get_settings(session, current.tenant_id))


@router.put(
    "/reservation-settings", response_model=ReservationSettingsRead, dependencies=[_ManageGuard]
)
async def write_reservation_settings(
    payload: ReservationSettingsWrite, current: CurrentUserDep, session: SessionDep
) -> ReservationSettingsRead:
    """Replace the pacing configuration. PUT because there is at most one row and the seven values
    are one policy; re-sending the same body is the same state, so no idempotency key is needed.

    Changing a default does NOT reach back into nights already being booked: ``covers_max`` is
    snapshot onto a slot row when it is first booked against, so the guests already holding those
    covers keep the room they were promised. The per-slot override below is how a manager reaches
    a night that is already open.
    """
    holder: dict[str, ReservationSettingsRead] = {}

    async def work() -> None:
        holder["read"] = _settings_read(
            await pacing.set_settings(
                session,
                current.tenant_id,
                pacing.ResolvedSettings(
                    service_open=payload.service_open,
                    service_close=payload.service_close,
                    default_covers_max=payload.default_covers_max,
                    default_parties_max=payload.default_parties_max,
                    min_party=payload.min_party,
                    max_party=payload.max_party,
                    booking_horizon_days=payload.booking_horizon_days,
                ),
            )
        )

    await run_in_uow(session, work)
    return holder["read"]


@router.put("/service-slots", response_model=ServiceSlotRead, dependencies=[_ManageGuard])
async def override_slot_capacity(
    payload: ServiceSlotCapacityWrite, current: CurrentUserDep, session: SessionDep
) -> ServiceSlotRead:
    """Set ONE slot's capacity — a private event, a short-staffed shift, a boiler failure.

    ``covers_max = 0`` CLOSES the slot. An override below what the slot has already taken is
    REFUSED (422 ``hospitality.slot_override_below_booked``) rather than clamped, so the manager
    sees the conflict and can decide whom to call instead of discovering it as a constraint
    violation on the next save.

    The slot is identified in the BODY: its identity is the pair ``(service_date, slot_start)``, and
    a two-segment path would read as a hierarchy that does not exist. PUT because the write replaces
    that slot's capacity outright and re-sending it is the same state, so no idempotency key is
    needed either.
    """
    holder: dict[str, ServiceSlotRead] = {}

    async def work() -> None:
        settings = await pacing.get_settings(session, current.tenant_id)
        slot = await pacing.override_slot(
            session,
            current.tenant_id,
            payload.service_date,
            payload.slot_start,
            covers_max=payload.covers_max,
            parties_max=payload.parties_max,
            settings=settings,
        )
        holder["read"] = ServiceSlotRead.model_validate(slot)

    await run_in_uow(session, work)
    return holder["read"]

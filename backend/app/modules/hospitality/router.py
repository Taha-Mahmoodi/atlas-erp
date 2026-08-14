"""Hospitality STAFF HTTP layer (thin): parse -> call service -> return schema (PLAN 19 Task 6).

STAFF-facing routes only. The property's WEBSITE is a separate principal on a separate router
(``website_router.py``, Task 7) because the two surfaces have different cache policies and a
different credential (D-069 API key vs a staff JWT), and mixing them would put a
``Cache-Control: private`` menu read next to an unbounded staff query.

Mounting this router in ``core/bootstrap.py`` is also what IMPORTS the module, which is what runs
``constants.py``'s ``register_permissions`` — so a hospitality key reaches ``rbac.catalog_keys()``,
and can therefore be granted to a tenant, only through that mount (D-009).

Three things here are specific to a restaurant and worth reading before changing them:

* **``/fire`` is the idempotent one, not ``/settle``.** Firing is what commits ingredients (Q4), so
  a terminal retrying a timed-out fire must get the first answer back rather than send the kitchen
  a second copy. Settling creates no document and the strictly-sequential lifecycle already rejects
  a second attempt, so it needs no key.
* **``/fire`` schedules the depletion jobs AFTER its uow commits.** The job rows are submitted by an
  event handler deep inside the transaction and surface through ``depletion.take_depletion_jobs``;
  scheduling before the commit would race the PENDING row's visibility (core/jobs.py). Forgetting
  the drain loses only the SCHEDULING, never the job row — but the row would then sit PENDING
  forever, because core has no stale-PENDING sweeper.
* **The fire response claims nothing about depletion.** It returns the ticket, whose status is
  SENT_TO_KITCHEN; the ingredients have not left the storeroom yet and will not until the job runs.
  The truthful place to watch that is ``/api/v1/jobs`` and the ticket document's D-012 chain.

The 86 endpoints write ``hsp_menu_availability`` directly rather than through ``run_in_uow``'s
event drain, because nothing on that path publishes an event — but they still commit inside the
uow helper, so the D-007 stamping listener and the D-010 audit buffer behave identically to every
other write in Atlas.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response

from app.core.deps import CurrentUserDep, SessionDep, SessionFactoryDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.jobs import schedule_job
from app.core.pagination import MAX_LIMIT, CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.hospitality import queries
from app.modules.hospitality.constants import (
    AT_RISK_DEFAULT_THRESHOLD,
    HOSPITALITY_MENU_MANAGE,
    HOSPITALITY_MENU_READ,
    HOSPITALITY_TICKET_MANAGE,
    HOSPITALITY_TICKET_READ,
    HOSPITALITY_TICKET_SETTLE,
    AvailabilityState,
    OrderTicketStatus,
)
from app.modules.hospitality.schemas import (
    MenuAvailabilityRead,
    MenuAvailabilitySet,
    MenuItemAtRiskRead,
    OrderTicketAdvance,
    OrderTicketCreate,
    OrderTicketLineRead,
    OrderTicketLinesAdd,
    OrderTicketRead,
)
from app.modules.hospitality.service import availability, depletion, tickets

router = APIRouter(prefix="/api/v1/hospitality", tags=["hospitality"])

CursorParamsDep = Depends(cursor_params)
_MenuReadGuard = Depends(require_permission(HOSPITALITY_MENU_READ))
_MenuManageGuard = Depends(require_permission(HOSPITALITY_MENU_MANAGE))
_TicketReadGuard = Depends(require_permission(HOSPITALITY_TICKET_READ))
_TicketManageGuard = Depends(require_permission(HOSPITALITY_TICKET_MANAGE))
_TicketSettleGuard = Depends(require_permission(HOSPITALITY_TICKET_SETTLE))
_CreateTicketIdempotentDep = Depends(Idempotent("hospitality.order_ticket.create"))
_FireTicketIdempotentDep = Depends(Idempotent("hospitality.order_ticket.fire"))


# --- Menu availability (the 86 board) -----------------------------------------


@router.get("/menu/at-risk", response_model=list[MenuItemAtRiskRead], dependencies=[_MenuReadGuard])
async def list_at_risk_menu_items(
    current: CurrentUserDep,
    session: SessionDep,
    threshold: int = Query(default=AT_RISK_DEFAULT_THRESHOLD, ge=0),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
) -> list[MenuItemAtRiskRead]:
    """Dishes the storeroom covers ``threshold`` portions or fewer of, worst first (PLAN 19).

    The ONE place derived recipe math is allowed in this phase, and it is ADVISORY: it reads
    on-hand only (no ``committed``, no ``on_order`` — a kitchen cannot cook an open PO), it
    over-reports on shared ingredients, and it takes no action. A human reads it and 86s, which
    writes the stored row the guest-facing read path actually serves (Q2).

    A plain list, not a ``Page``: the whole point is the worst N dishes, and the row count is
    bounded by ``limit`` (≤ ``MAX_LIMIT``) — the ``/mrp/runs/{id}/capacity`` report precedent.
    """
    rows = await queries.at_risk_menu_items(
        session, current.tenant_id, threshold=threshold, limit=limit
    )
    return [MenuItemAtRiskRead.model_validate(row) for row in rows]


@router.put(
    "/menu/{item_id}/availability",
    response_model=MenuAvailabilityRead,
    dependencies=[_MenuManageGuard],
)
async def set_menu_availability(
    item_id: uuid.UUID,
    payload: MenuAvailabilitySet,
    current: CurrentUserDep,
    session: SessionDep,
) -> MenuAvailabilityRead:
    """86 a dish, start a countdown on it, or time-box either (Q2). PUT because it REPLACES the one
    stored answer for the item — there is at most one row per item and re-sending the same body is
    the same state, so no idempotency key is needed."""
    holder: dict[str, MenuAvailabilityRead] = {}

    async def work() -> None:
        resolved = await availability.set_availability(
            session,
            current.tenant_id,
            item_id,
            state=AvailabilityState(payload.state),
            remaining_qty=payload.remaining_qty,
            available_until=payload.available_until,
            reason=payload.reason,
        )
        holder["read"] = MenuAvailabilityRead(
            item_id=item_id,
            state=resolved.state,
            remaining_qty=resolved.remaining_qty,
            available_until=resolved.available_until,
            reason=resolved.reason,
            source=resolved.source,
        )

    await run_in_uow(session, work)
    return holder["read"]


@router.delete(
    "/menu/{item_id}/availability", status_code=204, dependencies=[_MenuManageGuard]
)
async def clear_menu_availability(
    item_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> Response:
    """Put the dish back on the menu by deleting its override row — absence IS the canonical
    AVAILABLE. A no-op (still 204) if the item was never 86'd."""

    async def work() -> None:
        await availability.clear_86(session, current.tenant_id, item_id)

    await run_in_uow(session, work)
    return Response(status_code=204)


# --- Order tickets ------------------------------------------------------------


@router.post(
    "/tickets", response_model=OrderTicketRead, status_code=201, dependencies=[_TicketManageGuard]
)
async def create_ticket(
    payload: OrderTicketCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateTicketIdempotentDep,
) -> OrderTicketRead:
    """Open a check. IDEMPOTENT (D-013): a ticket registers a document and burns a gapless TKT-
    number, so a retry must not open a second check on the same table."""
    holder: dict[str, OrderTicketRead] = {}

    async def work() -> None:
        ticket = await tickets.create_ticket(session, current.tenant_id, payload)
        await session.refresh(ticket)
        holder["read"] = await idem.capture(
            OrderTicketRead.model_validate(ticket), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]


@router.get("/tickets", response_model=Page[OrderTicketRead], dependencies=[_TicketReadGuard])
async def list_tickets(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: OrderTicketStatus | None = None,
    opened_on: date | None = None,
) -> Page[OrderTicketRead]:
    """The floor's checks (D-014 keyset), newest service date first, filtered by status and service
    date — the two filters a floor plan and a kitchen display actually use. No ETag: a ticket list
    changes continuously through service (the journal-entry precedent)."""
    page = await queries.list_tickets(
        session,
        current.tenant_id,
        status=status,
        opened_on=opened_on,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, OrderTicketRead)


@router.get(
    "/tickets/{ticket_id}", response_model=OrderTicketRead, dependencies=[_TicketReadGuard]
)
async def get_ticket(
    ticket_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> OrderTicketRead:
    ticket = await tickets.get_ticket(session, current.tenant_id, ticket_id)
    return OrderTicketRead.model_validate(ticket)


@router.get(
    "/tickets/{ticket_id}/lines",
    response_model=list[OrderTicketLineRead],
    dependencies=[_TicketReadGuard],
)
async def list_ticket_lines(
    ticket_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[OrderTicketLineRead]:
    """A check's lines in entry order. Unpaginated: a check is a table's order, not a ledger — it
    is bounded by what a party can eat (the BOM-components / routing-operations precedent)."""
    await tickets.get_ticket(session, current.tenant_id, ticket_id)  # 404 on a foreign ticket
    lines = await tickets.get_ticket_lines(session, current.tenant_id, ticket_id)
    return [OrderTicketLineRead.model_validate(line) for line in lines]


@router.post(
    "/tickets/{ticket_id}/lines",
    response_model=OrderTicketRead,
    dependencies=[_TicketManageGuard],
)
async def add_ticket_lines(
    ticket_id: uuid.UUID,
    payload: OrderTicketLinesAdd,
    current: CurrentUserDep,
    session: SessionDep,
) -> OrderTicketRead:
    """Add dishes to an OPEN check. Rejected once fired (409 ``hospitality.ticket_not_open``): a
    fired line is already being cooked and already counted for depletion."""
    holder: dict[str, OrderTicketRead] = {}

    async def work() -> None:
        ticket = await tickets.add_lines(session, current.tenant_id, ticket_id, payload.lines)
        await session.refresh(ticket)
        holder["read"] = OrderTicketRead.model_validate(ticket)

    await run_in_uow(session, work)
    return holder["read"]


@router.post(
    "/tickets/{ticket_id}/fire", response_model=OrderTicketRead, dependencies=[_TicketManageGuard]
)
async def fire_ticket(
    ticket_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    factory: SessionFactoryDep,
    idem: IdempotentDep = _FireTicketIdempotentDep,
) -> OrderTicketRead:
    """Send the check to the kitchen — the commitment moment (Q4): an 86'd dish is refused here, a
    countdown burns here, and the background depletion job is submitted here.

    IDEMPOTENT (D-013): the fire submits the job that will create stock documents, so a retried
    request must return the first answer rather than deplete twice.

    The jobs are SCHEDULED after ``run_in_uow`` commits (module docstring). The response carries the
    ticket, not a job id: the ingredients have not moved yet, and claiming otherwise is exactly the
    dishonesty Q4's concession has to avoid.
    """
    holder: dict[str, OrderTicketRead] = {}

    async def work() -> None:
        ticket = await tickets.fire_ticket(session, current.tenant_id, ticket_id)
        await session.refresh(ticket)
        holder["read"] = await idem.capture(
            OrderTicketRead.model_validate(ticket), status_code=200
        )

    await run_in_uow(session, work)
    for job_id in depletion.take_depletion_jobs(session):
        schedule_job(job_id, factory)
    return holder["read"]


@router.post(
    "/tickets/{ticket_id}/advance",
    response_model=OrderTicketRead,
    dependencies=[_TicketManageGuard],
)
async def advance_ticket(
    ticket_id: uuid.UUID,
    payload: OrderTicketAdvance,
    current: CurrentUserDep,
    session: SessionDep,
) -> OrderTicketRead:
    """Move a fired check through the kitchen's progress: IN_PREP → READY → SERVED. No stock or
    money effect — this is what lets the floor see where a check is."""
    holder: dict[str, OrderTicketRead] = {}

    async def work() -> None:
        ticket = await tickets.advance_ticket(
            session, current.tenant_id, ticket_id, OrderTicketStatus(payload.status)
        )
        await session.refresh(ticket)
        holder["read"] = OrderTicketRead.model_validate(ticket)

    await run_in_uow(session, work)
    return holder["read"]


@router.post(
    "/tickets/{ticket_id}/settle", response_model=OrderTicketRead, dependencies=[_TicketSettleGuard]
)
async def settle_ticket(
    ticket_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> OrderTicketRead:
    """Tender the check (terminal). A distinct permission from ``ticket.manage`` — settlement is the
    money moment, so a server can run the floor without closing out checks.

    No idempotency key: settling creates no document, and the strictly-sequential lifecycle already
    rejects a second attempt with 409 ``hospitality.ticket_transition_invalid``.
    """
    holder: dict[str, OrderTicketRead] = {}

    async def work() -> None:
        ticket = await tickets.settle_ticket(session, current.tenant_id, ticket_id)
        await session.refresh(ticket)
        holder["read"] = OrderTicketRead.model_validate(ticket)

    await run_in_uow(session, work)
    return holder["read"]

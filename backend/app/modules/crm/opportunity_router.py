"""CRM opportunity HTTP sub-router (thin): CRUD + lines + the kanban move-stage + the kanban board +
the convert-to-customer+quote (PLAN 12.1).

Mounted by ``router.py`` so it lives under ``/api/v1/crm`` — the opportunity routes are
``/crm/opportunities[...]``. The KANBAN board GET is declared BEFORE ``/{opportunity_id}`` so the
literal ``/opportunities/kanban`` is matched before the id capture. Every route is
permission-guarded
(D-009): MANAGE for create/edit/move-stage, the distinct CONVERT key for the convert action. The
detail
+ action responses carry the lines (``OpportunityDetail``). Writes commit through ``run_in_uow``
(D-011) so the convert event is dispatched in the same transaction (PERFORMANCE §6 / D-057).
"""

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.crm import service
from app.modules.crm.constants import (
    CRM_OPPORTUNITY_CONVERT,
    CRM_OPPORTUNITY_MANAGE,
    CRM_OPPORTUNITY_READ,
    KANBAN_STAGE_ORDER,
    OpportunityStage,
)
from app.modules.crm.models import Opportunity
from app.modules.crm.schemas import (
    ConvertOpportunity,
    KanbanBoard,
    KanbanColumn,
    MoveStage,
    OpportunityCreate,
    OpportunityDetail,
    OpportunityRead,
    OpportunityUpdate,
)
from app.modules.crm.service.opportunities import DEFAULT_KANBAN_COLUMN_LIMIT

opportunity_router = APIRouter()
_CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


async def _detail(
    session: SessionDep, tenant_id: uuid.UUID, opportunity: Opportunity
) -> OpportunityDetail:
    """Assemble the header + lines detail response for an opportunity."""
    lines = await service.get_opportunity_lines(session, tenant_id, opportunity.id)
    return OpportunityDetail(
        **OpportunityRead.model_validate(opportunity).model_dump(),
        lines=[line for line in lines],  # noqa: C416 - validated by the OpportunityLineRead schema
    )


@opportunity_router.get(
    "/opportunities/kanban",
    response_model=KanbanBoard,
    dependencies=[Depends(require_permission(CRM_OPPORTUNITY_READ))],
)
async def get_kanban_board(
    current: CurrentUserDep,
    session: SessionDep,
    owner_employee_id: uuid.UUID | None = None,
) -> KanbanBoard:
    """The opportunity KANBAN board (PLAN 12.1, D-057): opportunities grouped into a column per
    stage,
    in the declared stage order. ONE bounded query (PERFORMANCE §6). Optionally narrowed to one
    owner.
    Each column carries its count + total estimated value + the (capped) cards."""
    grouped = await service.kanban_board(
        session, current.tenant_id, owner_employee_id=owner_employee_id
    )
    columns = [
        KanbanColumn(
            stage=stage,
            count=len(grouped.get(stage, [])),
            total_estimated_value=sum(
                (Decimal(str(opp.estimated_value)) for opp in grouped.get(stage, [])),
                Decimal(0),
            ),
            opportunities=[OpportunityRead.model_validate(opp) for opp in grouped.get(stage, [])],
        )
        for stage in KANBAN_STAGE_ORDER
    ]
    return KanbanBoard(column_limit=DEFAULT_KANBAN_COLUMN_LIMIT, columns=columns)


@opportunity_router.get(
    "/opportunities",
    response_model=Page[OpportunityRead],
    dependencies=[Depends(require_permission(CRM_OPPORTUNITY_READ))],
)
async def list_opportunities(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    stage: OpportunityStage | None = None,
    owner_employee_id: uuid.UUID | None = None,
) -> Page[OpportunityRead]:
    from app.modules.crm.schemas import OpportunityFilter

    page = await service.list_opportunities(
        session,
        current.tenant_id,
        filters=OpportunityFilter(stage=stage, owner_employee_id=owner_employee_id),
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, OpportunityRead)


@opportunity_router.post(
    "/opportunities",
    response_model=OpportunityDetail,
    status_code=201,
    dependencies=[Depends(require_permission(CRM_OPPORTUNITY_MANAGE))],
)
async def create_opportunity(
    payload: OpportunityCreate, current: CurrentUserDep, session: SessionDep
) -> OpportunityDetail:
    opportunity = await _commit(
        session, lambda: service.create_opportunity(session, current.tenant_id, payload)
    )
    return await _detail(session, current.tenant_id, opportunity)


@opportunity_router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityDetail,
    dependencies=[Depends(require_permission(CRM_OPPORTUNITY_READ))],
)
async def get_opportunity(
    opportunity_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> OpportunityDetail:
    opportunity = await service.get_opportunity(session, current.tenant_id, opportunity_id)
    return await _detail(session, current.tenant_id, opportunity)


@opportunity_router.patch(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityDetail,
    dependencies=[Depends(require_permission(CRM_OPPORTUNITY_MANAGE))],
)
async def update_opportunity(
    opportunity_id: uuid.UUID,
    payload: OpportunityUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> OpportunityDetail:
    opportunity = await _commit(
        session,
        lambda: service.update_opportunity(session, current.tenant_id, opportunity_id, payload),
    )
    return await _detail(session, current.tenant_id, opportunity)


@opportunity_router.post(
    "/opportunities/{opportunity_id}/move-stage",
    response_model=OpportunityDetail,
    dependencies=[Depends(require_permission(CRM_OPPORTUNITY_MANAGE))],
)
async def move_stage(
    opportunity_id: uuid.UUID,
    payload: MoveStage,
    current: CurrentUserDep,
    session: SessionDep,
) -> OpportunityDetail:
    """The KANBAN MOVE (PLAN 12.1): move an opportunity to the requested stage. MANAGE-guarded —
    moving
    a card is ordinary pipeline editing (the higher-privilege convert action has its own key)."""
    opportunity = await _commit(
        session,
        lambda: service.move_stage(session, current.tenant_id, opportunity_id, payload.stage),
    )
    return await _detail(session, current.tenant_id, opportunity)


@opportunity_router.post(
    "/opportunities/{opportunity_id}/convert",
    response_model=OpportunityDetail,
    dependencies=[Depends(require_permission(CRM_OPPORTUNITY_CONVERT))],
)
async def convert_opportunity(
    opportunity_id: uuid.UUID,
    # ConvertOpportunity is a parameterless body in v1 (D-057), reserved for later overrides.
    payload: ConvertOpportunity,  # noqa: ARG001
    current: CurrentUserDep,
    session: SessionDep,
) -> OpportunityDetail:
    """Convert a (non-terminal) opportunity → a sales customer + quote (PLAN 12.1, D-057). Guarded
    by
    the DISTINCT ``crm.opportunity.convert`` key (a higher-privilege action than editing). Publishes
    ``OpportunityConverted``; SALES' handler creates the customer (if new) + quote in the SAME
    transaction (``run_in_uow``); the opportunity is set WON + converted ids. The returned detail
    carries the WON stage + the converted_customer_id / converted_quote_id the convert recorded."""
    opportunity = await _commit(
        session,
        lambda: service.convert_opportunity(session, current.tenant_id, opportunity_id),
    )
    return await _detail(session, current.tenant_id, opportunity)

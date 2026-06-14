"""CRM HTTP layer (thin): parse -> call service -> return schema (PLAN 12.1).

REST under ``/api/v1/crm``: LEADS (CRUD + qualify/disqualify/convert-to-opportunity) here, with the
OPPORTUNITY surface (``opportunity_router`` — CRUD + lines + move-stage + convert + the kanban
board)
and the ACTIVITY surface (``activity_router`` — CRUD + complete) mounted as sibling sub-routers at
the
foot of this file so the whole module is ONE surface at ``/api/v1/crm`` (the projects router
precedent —
no second mount in main.py). Every route is permission-guarded (D-009: manage vs convert); writes
commit through ``run_in_uow`` (D-011) so audit rows + the convert event ride the same transaction.
Lists are keyset-paginated (D-014, ≤3-query budget, PERFORMANCE §6).
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.crm import service
from app.modules.crm.activity_router import activity_router
from app.modules.crm.constants import CRM_LEAD_MANAGE, CRM_LEAD_READ, LeadStatus
from app.modules.crm.opportunity_router import opportunity_router
from app.modules.crm.schemas import (
    ConvertLead,
    LeadCreate,
    LeadFilter,
    LeadRead,
    LeadUpdate,
    OpportunityRead,
)

router = APIRouter(prefix="/api/v1/crm", tags=["crm"])
_CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, refreshing the ORM result in the async context so a
    sync ``model_validate`` never trips MissingGreenlet (the projects _commit twin). Refreshing also
    surfaces a converted opportunity's WON stage + converted ids that the drained convert handler
    set."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


@router.get(
    "/leads",
    response_model=Page[LeadRead],
    dependencies=[Depends(require_permission(CRM_LEAD_READ))],
)
async def list_leads(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    status: LeadStatus | None = None,
) -> Page[LeadRead]:
    page = await service.list_leads(
        session,
        current.tenant_id,
        filters=LeadFilter(status=status),
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, LeadRead)


@router.post(
    "/leads",
    response_model=LeadRead,
    status_code=201,
    dependencies=[Depends(require_permission(CRM_LEAD_MANAGE))],
)
async def create_lead(
    payload: LeadCreate, current: CurrentUserDep, session: SessionDep
) -> LeadRead:
    lead = await _commit(session, lambda: service.create_lead(session, current.tenant_id, payload))
    return LeadRead.model_validate(lead)


@router.get(
    "/leads/{lead_id}",
    response_model=LeadRead,
    dependencies=[Depends(require_permission(CRM_LEAD_READ))],
)
async def get_lead(
    lead_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> LeadRead:
    lead = await service.get_lead(session, current.tenant_id, lead_id)
    return LeadRead.model_validate(lead)


@router.patch(
    "/leads/{lead_id}",
    response_model=LeadRead,
    dependencies=[Depends(require_permission(CRM_LEAD_MANAGE))],
)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> LeadRead:
    lead = await _commit(
        session, lambda: service.update_lead(session, current.tenant_id, lead_id, payload)
    )
    return LeadRead.model_validate(lead)


@router.post(
    "/leads/{lead_id}/qualify",
    response_model=LeadRead,
    dependencies=[Depends(require_permission(CRM_LEAD_MANAGE))],
)
async def qualify_lead(
    lead_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> LeadRead:
    lead = await _commit(session, lambda: service.qualify_lead(session, current.tenant_id, lead_id))
    return LeadRead.model_validate(lead)


@router.post(
    "/leads/{lead_id}/disqualify",
    response_model=LeadRead,
    dependencies=[Depends(require_permission(CRM_LEAD_MANAGE))],
)
async def disqualify_lead(
    lead_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> LeadRead:
    lead = await _commit(
        session, lambda: service.disqualify_lead(session, current.tenant_id, lead_id)
    )
    return LeadRead.model_validate(lead)


@router.post(
    "/leads/{lead_id}/convert",
    response_model=OpportunityRead,
    status_code=201,
    dependencies=[Depends(require_permission(CRM_LEAD_MANAGE))],
)
async def convert_lead(
    lead_id: uuid.UUID,
    payload: ConvertLead,
    current: CurrentUserDep,
    session: SessionDep,
) -> OpportunityRead:
    """Convert a QUALIFIED lead into a DRAFT opportunity (PLAN 12.1). Returns the new opportunity.
    The
    lead → opportunity conversion is wholly CRM-internal (no cross-module event), so LEAD_MANAGE
    covers it — distinct from the opportunity → customer+quote convert, which needs the convert
    key."""
    opportunity = await _commit(
        session,
        lambda: service.convert_lead_to_opportunity(
            session, current.tenant_id, lead_id, payload
        ),
    )
    return OpportunityRead.model_validate(opportunity)


# The opportunity + activity surfaces are sibling sub-routers mounted here, so the whole module is
# ONE
# surface at /api/v1/crm.
router.include_router(opportunity_router)
router.include_router(activity_router)

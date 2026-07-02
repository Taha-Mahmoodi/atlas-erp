"""CRM activity HTTP sub-router (thin): CRUD + complete + cancel (PLAN 12.1).

Mounted by ``router.py`` so it lives under ``/api/v1/crm`` — the activity routes are
``/crm/activities[...]``. Every route is permission-guarded (D-009): ACTIVITY_MANAGE for
create/edit/complete/cancel, ACTIVITY_READ for the reads. The list scopes to a parent (lead or
opportunity) + status via query params (the activity timeline a detail screen reads). Writes commit
through ``run_in_uow`` (D-011) so audit rows ride the same transaction; lists are keyset-paginated
(D-014, ≤3-query budget, PERFORMANCE §6).
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
from app.modules.crm.constants import (
    CRM_ACTIVITY_MANAGE,
    CRM_ACTIVITY_READ,
    ActivityStatus,
)
from app.modules.crm.schemas import (
    ActivityCreate,
    ActivityFilter,
    ActivityRead,
    ActivityUpdate,
    CompleteActivity,
)

activity_router = APIRouter()
_CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


@activity_router.get(
    "/activities",
    response_model=Page[ActivityRead],
    dependencies=[Depends(require_permission(CRM_ACTIVITY_READ))],
)
async def list_activities(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    status: ActivityStatus | None = None,
    lead_id: uuid.UUID | None = None,
    opportunity_id: uuid.UUID | None = None,
) -> Page[ActivityRead]:
    page = await service.list_activities(
        session,
        current.tenant_id,
        filters=ActivityFilter(status=status, lead_id=lead_id, opportunity_id=opportunity_id),
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, ActivityRead)


@activity_router.post(
    "/activities",
    response_model=ActivityRead,
    status_code=201,
    dependencies=[Depends(require_permission(CRM_ACTIVITY_MANAGE))],
)
async def create_activity(
    payload: ActivityCreate, current: CurrentUserDep, session: SessionDep
) -> ActivityRead:
    activity = await _commit(
        session, lambda: service.create_activity(session, current.tenant_id, payload)
    )
    return ActivityRead.model_validate(activity)


@activity_router.get(
    "/activities/{activity_id}",
    response_model=ActivityRead,
    dependencies=[Depends(require_permission(CRM_ACTIVITY_READ))],
)
async def get_activity(
    activity_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ActivityRead:
    activity = await service.get_activity(session, current.tenant_id, activity_id)
    return ActivityRead.model_validate(activity)


@activity_router.patch(
    "/activities/{activity_id}",
    response_model=ActivityRead,
    dependencies=[Depends(require_permission(CRM_ACTIVITY_MANAGE))],
)
async def update_activity(
    activity_id: uuid.UUID,
    payload: ActivityUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> ActivityRead:
    activity = await _commit(
        session,
        lambda: service.update_activity(session, current.tenant_id, activity_id, payload),
    )
    return ActivityRead.model_validate(activity)


@activity_router.post(
    "/activities/{activity_id}/complete",
    response_model=ActivityRead,
    dependencies=[Depends(require_permission(CRM_ACTIVITY_MANAGE))],
)
async def complete_activity(
    activity_id: uuid.UUID,
    payload: CompleteActivity,
    current: CurrentUserDep,
    session: SessionDep,
) -> ActivityRead:
    activity = await _commit(
        session,
        lambda: service.complete_activity(
            session, current.tenant_id, activity_id, completed_date=payload.completed_date
        ),
    )
    return ActivityRead.model_validate(activity)


@activity_router.post(
    "/activities/{activity_id}/cancel",
    response_model=ActivityRead,
    dependencies=[Depends(require_permission(CRM_ACTIVITY_MANAGE))],
)
async def cancel_activity(
    activity_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ActivityRead:
    activity = await _commit(
        session, lambda: service.cancel_activity(session, current.tenant_id, activity_id)
    )
    return ActivityRead.model_validate(activity)

"""Maintenance-plan HTTP layer (PLAN 9.2), included into the maintenance router.

A sibling sub-router under the same ``/api/v1/maintenance`` prefix. REST: maintenance-plan CRUD +
activate/deactivate + the generate-due-orders run (``POST /maintenance-plans/run-preventive``).

RBAC (D-009): read by ``maintenance.plan.read``; create/edit/activate/deactivate by
``maintenance.plan.manage``; the generation run by ``maintenance.plan.run`` (segregation of duties).
Writes commit through ``run_in_uow`` (D-011); the run is IDEMPOTENT (D-013) AND naturally idempotent
(a same-day re-run finds nothing due). The list is reference-ish data, so it carries a
conditional-GET ETag (PERFORMANCE §3 / D-035).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date

from fastapi import APIRouter, Depends, Request, Response

from app.core.conditional import collection_etag, conditional_response, request_fingerprint
from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.maintenance import service
from app.modules.maintenance.constants import (
    MAINTENANCE_PLAN_MANAGE,
    MAINTENANCE_PLAN_READ,
    MAINTENANCE_PLAN_RUN,
    MaintenancePlanStatus,
)
from app.modules.maintenance.models import MaintenancePlan
from app.modules.maintenance.schemas import (
    MaintenanceOrderRead,
    MaintenancePlanCreate,
    MaintenancePlanRead,
    MaintenancePlanUpdate,
    RunPreventiveResult,
)

plan_router = APIRouter(tags=["maintenance-plans"])

_CursorParamsDep = Depends(cursor_params)
_RunIdem = Depends(Idempotent("maintenance.plan.run"))


async def _commit_read[T](
    session: SessionDep, work: Callable[[], Awaitable[object]]
) -> MaintenancePlanRead:
    """Run a service call inside the D-011 uow and return the plan refreshed + validated in the
    async context (the bom_router _commit twin)."""
    holder: dict[str, MaintenancePlanRead] = {}

    async def _work() -> None:
        plan = await work()
        await session.refresh(plan)
        holder["read"] = MaintenancePlanRead.model_validate(plan)

    await run_in_uow(session, _work)
    return holder["read"]


# NOTE: /run-preventive is declared BEFORE /maintenance-plans/{plan_id} so the literal path is
# matched ahead of the {plan_id} catch-all (FastAPI matches routes in declaration order).
@plan_router.post(
    "/maintenance-plans/run-preventive",
    response_model=RunPreventiveResult,
    dependencies=[Depends(require_permission(MAINTENANCE_PLAN_RUN))],
)
async def run_preventive(
    current: CurrentUserDep,
    session: SessionDep,
    as_of: date | None = None,
    idem: IdempotentDep = _RunIdem,
) -> RunPreventiveResult:
    """Generate PREVENTIVE orders for every ACTIVE plan due on/before ``as_of`` (default today): one
    order per due plan, advancing each past the run date (PLAN 9.2, D-051). INLINE at v1 scale (the
    6.4 reorder-scan precedent; a job is the later if plan counts grow). IDEMPOTENT (D-013) and
    naturally idempotent (a same-day re-run finds nothing due)."""
    as_of_date = as_of or date.today()
    holder: dict[str, RunPreventiveResult] = {}

    async def work() -> None:
        orders = await service.run_preventive_maintenance(
            session, current.tenant_id, as_of_date
        )
        for order in orders:
            await session.refresh(order)
        result = RunPreventiveResult(
            as_of_date=as_of_date,
            plans_due=len(orders),
            orders_generated=[MaintenanceOrderRead.model_validate(o) for o in orders],
        )
        holder["read"] = await idem.capture(result)

    await run_in_uow(session, work)
    return holder["read"]


@plan_router.post(
    "/maintenance-plans",
    response_model=MaintenancePlanRead,
    status_code=201,
    dependencies=[Depends(require_permission(MAINTENANCE_PLAN_MANAGE))],
)
async def create_maintenance_plan(
    payload: MaintenancePlanCreate, current: CurrentUserDep, session: SessionDep
) -> MaintenancePlanRead:
    return await _commit_read(
        session, lambda: service.create_plan(session, current.tenant_id, payload)
    )


@plan_router.get(
    "/maintenance-plans",
    response_model=Page[MaintenancePlanRead],
    dependencies=[Depends(require_permission(MAINTENANCE_PLAN_READ))],
)
async def list_maintenance_plans(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    status: MaintenancePlanStatus | None = None,
    equipment_id: uuid.UUID | None = None,
) -> Page[MaintenancePlanRead] | Response:
    """Conditional-GET supported (D-035): the status/equipment filters fold into the fingerprint so
    a filtered 304 is correct."""
    fingerprint = request_fingerprint(params.cursor, params.limit, status, equipment_id)
    etag = await collection_etag(session, MaintenancePlan, request_fingerprint=fingerprint)

    async def builder() -> Page[MaintenancePlanRead]:
        page = await service.list_plans(
            session,
            current.tenant_id,
            status=status,
            equipment_id=equipment_id,
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, MaintenancePlanRead)

    return await conditional_response(request, response, etag, builder)


@plan_router.get(
    "/maintenance-plans/{plan_id}",
    response_model=MaintenancePlanRead,
    dependencies=[Depends(require_permission(MAINTENANCE_PLAN_READ))],
)
async def get_maintenance_plan(
    plan_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> MaintenancePlanRead:
    plan = await service.get_maintenance_plan(session, current.tenant_id, plan_id)
    return MaintenancePlanRead.model_validate(plan)


@plan_router.patch(
    "/maintenance-plans/{plan_id}",
    response_model=MaintenancePlanRead,
    dependencies=[Depends(require_permission(MAINTENANCE_PLAN_MANAGE))],
)
async def update_maintenance_plan(
    plan_id: uuid.UUID,
    payload: MaintenancePlanUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> MaintenancePlanRead:
    return await _commit_read(
        session,
        lambda: service.update_plan(session, current.tenant_id, plan_id, payload),
    )


@plan_router.post(
    "/maintenance-plans/{plan_id}/activate",
    response_model=MaintenancePlanRead,
    dependencies=[Depends(require_permission(MAINTENANCE_PLAN_MANAGE))],
)
async def activate_maintenance_plan(
    plan_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> MaintenancePlanRead:
    """Activate a plan — the generation run considers it (PLAN 9.2)."""
    return await _commit_read(
        session,
        lambda: service.set_plan_status(
            session, current.tenant_id, plan_id, MaintenancePlanStatus.ACTIVE
        ),
    )


@plan_router.post(
    "/maintenance-plans/{plan_id}/deactivate",
    response_model=MaintenancePlanRead,
    dependencies=[Depends(require_permission(MAINTENANCE_PLAN_MANAGE))],
)
async def deactivate_maintenance_plan(
    plan_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> MaintenancePlanRead:
    """Deactivate a plan — the generation run skips it (PLAN 9.2)."""
    return await _commit_read(
        session,
        lambda: service.set_plan_status(
            session, current.tenant_id, plan_id, MaintenancePlanStatus.INACTIVE
        ),
    )

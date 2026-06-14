"""HR HTTP layer (thin): parse -> call service -> return schema (PLAN 10.1).

REST under ``/api/v1/hr``: departments (CRUD + filtered list with a conditional-GET ETag) here, with
the position surface (``position_router``) and the employee surface (``employee_router`` — the
masked
employee CRUD, the compensation endpoint, the org chart) mounted as sibling sub-routers at the foot
of this file so the whole module is ONE surface at ``/api/v1/hr`` (the maintenance order_router /
plan_router include precedent — no second mount in main.py). Every route is guarded by an hr
permission key (D-009); writes commit through ``run_in_uow`` (D-011) so audit rows ride the same
transaction. The department list is reference data, so it carries a conditional-GET ETag
(PERFORMANCE §3 / D-035).
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Request, Response

from app.core.conditional import collection_etag, conditional_response, request_fingerprint
from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.hr import service
from app.modules.hr.constants import HR_DEPARTMENT_MANAGE, HR_DEPARTMENT_READ
from app.modules.hr.employee_router import employee_router
from app.modules.hr.leave_router import leave_router
from app.modules.hr.models import Department
from app.modules.hr.position_router import position_router
from app.modules.hr.schemas import (
    DepartmentCreate,
    DepartmentFilter,
    DepartmentRead,
    DepartmentUpdate,
)

router = APIRouter(prefix="/api/v1/hr", tags=["hr"])
_CursorParamsDep = Depends(cursor_params)


async def _commit_read[T](
    session: SessionDep, work: Callable[[], Awaitable[object]]
) -> DepartmentRead:
    """Run a service call inside the D-011 uow and return the department refreshed + validated in
    the async context so a sync ``model_validate`` never trips MissingGreenlet (the maintenance
    _commit twin)."""
    holder: dict[str, DepartmentRead] = {}

    async def _work() -> None:
        department = await work()
        await session.refresh(department)
        holder["read"] = DepartmentRead.model_validate(department)

    await run_in_uow(session, _work)
    return holder["read"]


@router.post(
    "/departments",
    response_model=DepartmentRead,
    status_code=201,
    dependencies=[Depends(require_permission(HR_DEPARTMENT_MANAGE))],
)
async def create_department(
    payload: DepartmentCreate, current: CurrentUserDep, session: SessionDep
) -> DepartmentRead:
    return await _commit_read(
        session, lambda: service.create_department(session, current.tenant_id, payload)
    )


@router.get(
    "/departments",
    response_model=Page[DepartmentRead],
    dependencies=[Depends(require_permission(HR_DEPARTMENT_READ))],
)
async def list_departments(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    is_active: bool | None = None,
    parent_id: uuid.UUID | None = None,
) -> Page[DepartmentRead] | Response:
    """Conditional-GET supported (D-035): the is_active / parent filters fold into the fingerprint
    so a filtered 304 is correct."""
    fingerprint = request_fingerprint(params.cursor, params.limit, is_active, parent_id)
    etag = await collection_etag(session, Department, request_fingerprint=fingerprint)

    async def builder() -> Page[DepartmentRead]:
        page = await service.list_departments(
            session,
            current.tenant_id,
            filters=DepartmentFilter(is_active=is_active, parent_id=parent_id),
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, DepartmentRead)

    return await conditional_response(request, response, etag, builder)


@router.get(
    "/departments/{department_id}",
    response_model=DepartmentRead,
    dependencies=[Depends(require_permission(HR_DEPARTMENT_READ))],
)
async def get_department(
    department_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> DepartmentRead:
    department = await service.get_department(session, current.tenant_id, department_id)
    return DepartmentRead.model_validate(department)


@router.patch(
    "/departments/{department_id}",
    response_model=DepartmentRead,
    dependencies=[Depends(require_permission(HR_DEPARTMENT_MANAGE))],
)
async def update_department(
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> DepartmentRead:
    return await _commit_read(
        session,
        lambda: service.update_department(session, current.tenant_id, department_id, payload),
    )


# The position surface (positions + ETag list), the employee surface (masked employee CRUD, the
# compensation endpoint, the org chart) and the leave surface (leave types + balances +
# accrual run +
# leave requests with the approval flow, PLAN 10.2) are sibling sub-routers mounted here, so
# the whole
# module is ONE surface at /api/v1/hr.
router.include_router(position_router)
router.include_router(employee_router)
router.include_router(leave_router)

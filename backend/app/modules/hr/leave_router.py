"""Leave HTTP layer (PLAN 10.2, D-053), included into the hr router.

A sibling sub-router under the same ``/api/v1/hr`` prefix, mounted by ``router.include_router`` in
router.py (the maintenance/HR precedent — ONE module surface, no second mount in main.py). REST:

- leave-types: CRUD + a filtered, paginated list with a conditional-GET ETag (config = reference
  data, PERFORMANCE §3 / D-035).
- leave-balances: ``GET /employees/{id}/leave-balances`` (an employee's balances) and
  ``POST /leave-balances/accrue?as_of=&frequency=`` (the accrual run).
- leave-requests: CRUD + submit / approve / reject / cancel; a filtered, paginated list.

RBAC (D-009; distinct authorities, D-040 precedent): leave types read by ``hr.leave_type.read``,
manage + the accrual run by ``hr.leave_type.manage``; leave requests + balances read by
``hr.leave.read``; file / submit / cancel by ``hr.leave.request``; approve / reject by the distinct
``hr.leave.approve`` key. Writes commit through ``run_in_uow`` (D-011) so audit rows ride the
transaction; the create / submit / approve / reject / accrue endpoints are IDEMPOTENT (D-013).
PERFORMANCE §6: lists are O(1) queries + paginated.
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
from app.modules.hr import service
from app.modules.hr.constants import (
    HR_LEAVE_APPROVE,
    HR_LEAVE_READ,
    HR_LEAVE_REQUEST,
    HR_LEAVE_TYPE_MANAGE,
    HR_LEAVE_TYPE_READ,
    AccrualFrequency,
    LeaveRequestStatus,
)
from app.modules.hr.models import LeaveType
from app.modules.hr.schemas import (
    AccrualResult,
    LeaveBalanceRead,
    LeaveDecision,
    LeaveRequestCreate,
    LeaveRequestFilter,
    LeaveRequestRead,
    LeaveRequestUpdate,
    LeaveTypeCreate,
    LeaveTypeFilter,
    LeaveTypeRead,
    LeaveTypeUpdate,
)

leave_router = APIRouter(tags=["hr-leave"])
_CursorParamsDep = Depends(cursor_params)
_CreateRequestIdem = Depends(Idempotent("hr.leave_request.create"))
_SubmitIdem = Depends(Idempotent("hr.leave_request.submit"))
_ApproveIdem = Depends(Idempotent("hr.leave_request.approve"))
_RejectIdem = Depends(Idempotent("hr.leave_request.reject"))
_AccrueIdem = Depends(Idempotent("hr.leave.accrue"))


async def _commit_type[T](
    session: SessionDep, work: Callable[[], Awaitable[object]]
) -> LeaveTypeRead:
    """Run a leave-type service call inside the D-011 uow and return the type refreshed + validated
    in the async context (the hr _commit twin)."""
    holder: dict[str, LeaveTypeRead] = {}

    async def _work() -> None:
        leave_type = await work()
        await session.refresh(leave_type)
        holder["read"] = LeaveTypeRead.model_validate(leave_type)

    await run_in_uow(session, _work)
    return holder["read"]


# --- Leave types --------------------------------------------------------------


@leave_router.post(
    "/leave-types",
    response_model=LeaveTypeRead,
    status_code=201,
    dependencies=[Depends(require_permission(HR_LEAVE_TYPE_MANAGE))],
)
async def create_leave_type(
    payload: LeaveTypeCreate, current: CurrentUserDep, session: SessionDep
) -> LeaveTypeRead:
    return await _commit_type(
        session, lambda: service.create_leave_type(session, current.tenant_id, payload)
    )


@leave_router.get(
    "/leave-types",
    response_model=Page[LeaveTypeRead],
    dependencies=[Depends(require_permission(HR_LEAVE_TYPE_READ))],
)
async def list_leave_types(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    is_active: bool | None = None,
    accrual_frequency: AccrualFrequency | None = None,
) -> Page[LeaveTypeRead] | Response:
    """Conditional-GET supported (D-035): the is_active / frequency filters fold into the
    fingerprint so a filtered 304 is correct."""
    fingerprint = request_fingerprint(params.cursor, params.limit, is_active, accrual_frequency)
    etag = await collection_etag(session, LeaveType, request_fingerprint=fingerprint)

    async def builder() -> Page[LeaveTypeRead]:
        page = await service.list_leave_types(
            session,
            current.tenant_id,
            filters=LeaveTypeFilter(is_active=is_active, accrual_frequency=accrual_frequency),
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, LeaveTypeRead)

    return await conditional_response(request, response, etag, builder)


@leave_router.get(
    "/leave-types/{leave_type_id}",
    response_model=LeaveTypeRead,
    dependencies=[Depends(require_permission(HR_LEAVE_TYPE_READ))],
)
async def get_leave_type(
    leave_type_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> LeaveTypeRead:
    leave_type = await service.get_leave_type(session, current.tenant_id, leave_type_id)
    return LeaveTypeRead.model_validate(leave_type)


@leave_router.patch(
    "/leave-types/{leave_type_id}",
    response_model=LeaveTypeRead,
    dependencies=[Depends(require_permission(HR_LEAVE_TYPE_MANAGE))],
)
async def update_leave_type(
    leave_type_id: uuid.UUID,
    payload: LeaveTypeUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> LeaveTypeRead:
    return await _commit_type(
        session,
        lambda: service.update_leave_type(session, current.tenant_id, leave_type_id, payload),
    )


# --- Leave balances + the accrual run -----------------------------------------


@leave_router.get(
    "/employees/{employee_id}/leave-balances",
    response_model=list[LeaveBalanceRead],
    dependencies=[Depends(require_permission(HR_LEAVE_READ))],
)
async def list_employee_leave_balances(
    employee_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[LeaveBalanceRead]:
    """One employee's running leave balances (PLAN 10.2). 404 if the employee does not exist."""
    balances = await service.list_leave_balances(session, current.tenant_id, employee_id)
    return [LeaveBalanceRead.model_validate(b) for b in balances]


@leave_router.post(
    "/leave-balances/accrue",
    response_model=AccrualResult,
    dependencies=[Depends(require_permission(HR_LEAVE_TYPE_MANAGE))],
)
async def run_accrual(
    current: CurrentUserDep,
    session: SessionDep,
    frequency: AccrualFrequency,
    as_of: date | None = None,
    idem: IdempotentDep = _AccrueIdem,
) -> AccrualResult:
    """Run leave accrual for ``frequency`` as of ``as_of`` (default today): grant each ACTIVE
    employee the per-period amount of each ACTIVE leave type of that frequency, capped (PLAN 10.2,
    D-053). IDEMPOTENT (D-013) and naturally idempotent (a same-period re-run grants nothing)."""
    as_of_date = as_of or date.today()
    holder: dict[str, AccrualResult] = {}

    async def work() -> None:
        period, accrued = await service.accrue_leave(
            session, current.tenant_id, as_of=as_of_date, frequency=frequency
        )
        result = AccrualResult(frequency=frequency, period=period, balances_accrued=accrued)
        holder["read"] = await idem.capture(result)

    await run_in_uow(session, work)
    return holder["read"]


# --- Leave requests -----------------------------------------------------------


@leave_router.post(
    "/leave-requests",
    response_model=LeaveRequestRead,
    status_code=201,
    dependencies=[Depends(require_permission(HR_LEAVE_REQUEST))],
)
async def create_leave_request(
    payload: LeaveRequestCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateRequestIdem,
) -> LeaveRequestRead:
    """File a DRAFT leave request (PLAN 10.2). IDEMPOTENT (D-013)."""
    holder: dict[str, LeaveRequestRead] = {}

    async def work() -> None:
        request = await service.create_leave_request(session, current.tenant_id, payload)
        await session.refresh(request)
        holder["read"] = await idem.capture(LeaveRequestRead.model_validate(request))

    await run_in_uow(session, work)
    return holder["read"]


@leave_router.get(
    "/leave-requests",
    response_model=Page[LeaveRequestRead],
    dependencies=[Depends(require_permission(HR_LEAVE_READ))],
)
async def list_leave_requests(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    employee_id: uuid.UUID | None = None,
    status: LeaveRequestStatus | None = None,
    leave_type_id: uuid.UUID | None = None,
) -> Page[LeaveRequestRead]:
    """Paginated leave requests, newest first (PLAN 10.2). Filters: employee / status /
    leave type."""
    filters = LeaveRequestFilter(
        employee_id=employee_id, status=status, leave_type_id=leave_type_id
    )
    page = await service.list_leave_requests(
        session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, LeaveRequestRead)


@leave_router.get(
    "/leave-requests/{request_id}",
    response_model=LeaveRequestRead,
    dependencies=[Depends(require_permission(HR_LEAVE_READ))],
)
async def get_leave_request(
    request_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> LeaveRequestRead:
    request = await service.get_leave_request(session, current.tenant_id, request_id)
    return LeaveRequestRead.model_validate(request)


@leave_router.patch(
    "/leave-requests/{request_id}",
    response_model=LeaveRequestRead,
    dependencies=[Depends(require_permission(HR_LEAVE_REQUEST))],
)
async def update_leave_request(
    request_id: uuid.UUID,
    payload: LeaveRequestUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> LeaveRequestRead:
    holder: dict[str, LeaveRequestRead] = {}

    async def work() -> None:
        request = await service.update_leave_request(
            session, current.tenant_id, request_id, payload
        )
        await session.refresh(request)
        holder["read"] = LeaveRequestRead.model_validate(request)

    await run_in_uow(session, work)
    return holder["read"]


@leave_router.post(
    "/leave-requests/{request_id}/submit",
    response_model=LeaveRequestRead,
    dependencies=[Depends(require_permission(HR_LEAVE_REQUEST))],
)
async def submit_leave_request(
    request_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _SubmitIdem,
) -> LeaveRequestRead:
    """Submit a DRAFT leave request for approval (PLAN 10.2). IDEMPOTENT (D-013)."""
    holder: dict[str, LeaveRequestRead] = {}

    async def work() -> None:
        request = await service.submit_leave_request(session, current.tenant_id, request_id)
        await session.refresh(request)
        holder["read"] = await idem.capture(LeaveRequestRead.model_validate(request))

    await run_in_uow(session, work)
    return holder["read"]


@leave_router.post(
    "/leave-requests/{request_id}/approve",
    response_model=LeaveRequestRead,
    dependencies=[Depends(require_permission(HR_LEAVE_APPROVE))],
)
async def approve_leave_request(
    request_id: uuid.UUID,
    payload: LeaveDecision,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ApproveIdem,
) -> LeaveRequestRead:
    """Approve a SUBMITTED leave request (PLAN 10.2, the ``hr.leave.approve`` action): DECREMENTS
    the employee's balance by the request days (422 ``hr.insufficient_leave_balance`` if short).
    IDEMPOTENT (D-013)."""
    holder: dict[str, LeaveRequestRead] = {}

    async def work() -> None:
        request = await service.approve_leave_request(
            session,
            current.tenant_id,
            request_id,
            approved_by=current.user_id,
            notes=payload.notes,
        )
        await session.refresh(request)
        holder["read"] = await idem.capture(LeaveRequestRead.model_validate(request))

    await run_in_uow(session, work)
    return holder["read"]


@leave_router.post(
    "/leave-requests/{request_id}/reject",
    response_model=LeaveRequestRead,
    dependencies=[Depends(require_permission(HR_LEAVE_APPROVE))],
)
async def reject_leave_request(
    request_id: uuid.UUID,
    payload: LeaveDecision,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _RejectIdem,
) -> LeaveRequestRead:
    """Reject a SUBMITTED leave request (PLAN 10.2). No balance effect. IDEMPOTENT (D-013)."""
    holder: dict[str, LeaveRequestRead] = {}

    async def work() -> None:
        request = await service.reject_leave_request(
            session,
            current.tenant_id,
            request_id,
            approved_by=current.user_id,
            notes=payload.notes,
        )
        await session.refresh(request)
        holder["read"] = await idem.capture(LeaveRequestRead.model_validate(request))

    await run_in_uow(session, work)
    return holder["read"]


@leave_router.post(
    "/leave-requests/{request_id}/cancel",
    response_model=LeaveRequestRead,
    dependencies=[Depends(require_permission(HR_LEAVE_REQUEST))],
)
async def cancel_leave_request(
    request_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> LeaveRequestRead:
    """Cancel a leave request (PLAN 10.2): from DRAFT/SUBMITTED (no balance effect) or APPROVED
    (RESTORES the balance, D-053)."""
    holder: dict[str, LeaveRequestRead] = {}

    async def work() -> None:
        request = await service.cancel_leave_request(session, current.tenant_id, request_id)
        await session.refresh(request)
        holder["read"] = LeaveRequestRead.model_validate(request)

    await run_in_uow(session, work)
    return holder["read"]

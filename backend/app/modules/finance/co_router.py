"""Controlling HTTP layer (PLAN 4.7), included into the finance router.

The fx_router/tax_router/ap_router/ar_router mirror. Split out of router.py (at the STRUCTURE §3
400-line cap) and mounted via ``router.include_router(co_router)`` so the module stays ONE surface
at ``/api/v1/finance`` — no second mount in main.py. Cost/profit-centre + allocation-rule reads are
guarded by the respective ``.read`` keys, creates/edits by ``.manage``; running an allocation posts
a journal, so it is guarded by ``finance.allocation.run`` and is IDEMPOTENT (D-013). Writes commit
through ``run_in_uow`` (D-011) so audit + events ride the transaction.
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_ALLOCATION_MANAGE,
    FINANCE_ALLOCATION_RUN,
    FINANCE_COST_CENTER_MANAGE,
    FINANCE_COST_CENTER_READ,
    FINANCE_PROFIT_CENTER_MANAGE,
    FINANCE_PROFIT_CENTER_READ,
)
from app.modules.finance.controlling_schemas import (
    AllocationRuleCreate,
    AllocationRuleDetail,
    AllocationRuleRead,
    AllocationRuleUpdate,
    AllocationRunRead,
    AllocationRunRequest,
    AllocationTargetRead,
    CostCenterCreate,
    CostCenterRead,
    CostCenterUpdate,
    ProfitCenterCreate,
    ProfitCenterRead,
    ProfitCenterUpdate,
)

co_router = APIRouter(tags=["finance-controlling"])

CursorParamsDep = Depends(cursor_params)
_RunIdempotentDep = Depends(Idempotent("finance.allocation.run"))


async def _commit_model[T, M](
    session: SessionDep, work, schema: type[M]
) -> M:
    """Run a service call inside the D-011 uow and validate its ORM result into ``schema`` after the
    refresh lands in the async context (avoids a sync MissingGreenlet on serialization)."""
    holder: dict[str, M] = {}

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder["read"] = schema.model_validate(result)

    await run_in_uow(session, _work)
    return holder["read"]


# --- Cost centres -------------------------------------------------------------


@co_router.post(
    "/cost-centers",
    response_model=CostCenterRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_COST_CENTER_MANAGE))],
)
async def create_cost_center(
    payload: CostCenterCreate, current: CurrentUserDep, session: SessionDep
) -> CostCenterRead:
    return await _commit_model(
        session,
        lambda: service.create_cost_center(session, current.tenant_id, payload),
        CostCenterRead,
    )


@co_router.patch(
    "/cost-centers/{cost_center_id}",
    response_model=CostCenterRead,
    dependencies=[Depends(require_permission(FINANCE_COST_CENTER_MANAGE))],
)
async def update_cost_center(
    cost_center_id: uuid.UUID,
    payload: CostCenterUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> CostCenterRead:
    return await _commit_model(
        session,
        lambda: service.update_cost_center(session, current.tenant_id, cost_center_id, payload),
        CostCenterRead,
    )


@co_router.get(
    "/cost-centers",
    response_model=Page[CostCenterRead],
    dependencies=[Depends(require_permission(FINANCE_COST_CENTER_READ))],
)
async def list_cost_centers(
    current: CurrentUserDep, session: SessionDep, params: CursorParams = CursorParamsDep
) -> Page[CostCenterRead]:
    page = await service.list_cost_centers(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return Page(
        items=[CostCenterRead.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


@co_router.get(
    "/cost-centers/{cost_center_id}",
    response_model=CostCenterRead,
    dependencies=[Depends(require_permission(FINANCE_COST_CENTER_READ))],
)
async def get_cost_center(
    cost_center_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> CostCenterRead:
    center = await service.get_cost_center(session, current.tenant_id, cost_center_id)
    return CostCenterRead.model_validate(center)


# --- Profit centres -----------------------------------------------------------


@co_router.post(
    "/profit-centers",
    response_model=ProfitCenterRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_PROFIT_CENTER_MANAGE))],
)
async def create_profit_center(
    payload: ProfitCenterCreate, current: CurrentUserDep, session: SessionDep
) -> ProfitCenterRead:
    return await _commit_model(
        session,
        lambda: service.create_profit_center(session, current.tenant_id, payload),
        ProfitCenterRead,
    )


@co_router.patch(
    "/profit-centers/{profit_center_id}",
    response_model=ProfitCenterRead,
    dependencies=[Depends(require_permission(FINANCE_PROFIT_CENTER_MANAGE))],
)
async def update_profit_center(
    profit_center_id: uuid.UUID,
    payload: ProfitCenterUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> ProfitCenterRead:
    return await _commit_model(
        session,
        lambda: service.update_profit_center(
            session, current.tenant_id, profit_center_id, payload
        ),
        ProfitCenterRead,
    )


@co_router.get(
    "/profit-centers",
    response_model=Page[ProfitCenterRead],
    dependencies=[Depends(require_permission(FINANCE_PROFIT_CENTER_READ))],
)
async def list_profit_centers(
    current: CurrentUserDep, session: SessionDep, params: CursorParams = CursorParamsDep
) -> Page[ProfitCenterRead]:
    page = await service.list_profit_centers(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return Page(
        items=[ProfitCenterRead.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


@co_router.get(
    "/profit-centers/{profit_center_id}",
    response_model=ProfitCenterRead,
    dependencies=[Depends(require_permission(FINANCE_PROFIT_CENTER_READ))],
)
async def get_profit_center(
    profit_center_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ProfitCenterRead:
    center = await service.get_profit_center(session, current.tenant_id, profit_center_id)
    return ProfitCenterRead.model_validate(center)


# --- Allocation rules ---------------------------------------------------------


async def _rule_detail(
    session: SessionDep, tenant_id: uuid.UUID, rule_id: uuid.UUID
) -> AllocationRuleDetail:
    rule = await service.get_allocation_rule(session, tenant_id, rule_id)
    await session.refresh(rule)
    targets = await service.get_rule_targets(session, tenant_id, rule_id)
    header = AllocationRuleRead.model_validate(rule)
    return AllocationRuleDetail(
        **header.model_dump(),
        targets=[AllocationTargetRead.model_validate(t) for t in targets],
    )


@co_router.post(
    "/allocation-rules",
    response_model=AllocationRuleDetail,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_ALLOCATION_MANAGE))],
)
async def create_allocation_rule(
    payload: AllocationRuleCreate, current: CurrentUserDep, session: SessionDep
) -> AllocationRuleDetail:
    holder: dict[str, AllocationRuleDetail] = {}

    async def work() -> None:
        rule = await service.create_allocation_rule(session, current.tenant_id, payload)
        holder["read"] = await _rule_detail(session, current.tenant_id, rule.id)

    await run_in_uow(session, work)
    return holder["read"]


@co_router.patch(
    "/allocation-rules/{rule_id}",
    response_model=AllocationRuleDetail,
    dependencies=[Depends(require_permission(FINANCE_ALLOCATION_MANAGE))],
)
async def update_allocation_rule(
    rule_id: uuid.UUID,
    payload: AllocationRuleUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> AllocationRuleDetail:
    holder: dict[str, AllocationRuleDetail] = {}

    async def work() -> None:
        await service.update_allocation_rule(session, current.tenant_id, rule_id, payload)
        holder["read"] = await _rule_detail(session, current.tenant_id, rule_id)

    await run_in_uow(session, work)
    return holder["read"]


@co_router.get(
    "/allocation-rules",
    response_model=Page[AllocationRuleRead],
    dependencies=[Depends(require_permission(FINANCE_ALLOCATION_MANAGE))],
)
async def list_allocation_rules(
    current: CurrentUserDep, session: SessionDep, params: CursorParams = CursorParamsDep
) -> Page[AllocationRuleRead]:
    page = await service.list_allocation_rules(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return Page(
        items=[AllocationRuleRead.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


@co_router.get(
    "/allocation-rules/{rule_id}",
    response_model=AllocationRuleDetail,
    dependencies=[Depends(require_permission(FINANCE_ALLOCATION_MANAGE))],
)
async def get_allocation_rule(
    rule_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> AllocationRuleDetail:
    return await _rule_detail(session, current.tenant_id, rule_id)


# --- Allocation runs ----------------------------------------------------------


@co_router.post(
    "/allocation-runs",
    response_model=AllocationRunRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_ALLOCATION_RUN))],
)
async def run_allocation(
    payload: AllocationRunRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _RunIdempotentDep,
) -> AllocationRunRead:
    """Run an allocation rule for a period (PLAN 4.7). Posts ONE balanced entry redistributing the
    source cost centre's net period cost to its targets. IDEMPOTENT (D-013): a retried request
    replays; a second run for the same (rule, period) returns the existing run."""
    holder: dict[str, AllocationRunRead] = {}

    async def work() -> None:
        run = await service.run_allocation(
            session,
            current.tenant_id,
            payload.allocation_rule_id,
            payload.fiscal_period_id,
            payload.run_date,
        )
        await session.refresh(run)
        result = AllocationRunRead.model_validate(run)
        holder["read"] = await idem.capture(result, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]

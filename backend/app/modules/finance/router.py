"""Finance HTTP layer (thin): parse -> call service -> return schema (PLAN 4.1).

Routes are guarded by the finance permission keys (D-009): reads need ``finance.account.read``
/ ``finance.period.read``, writes need ``finance.account.manage`` / ``finance.period.manage``.
Writes commit through ``run_in_uow`` (D-011) — the one sanctioned unit-of-work path — so audit
rows ride the same transaction and the (future) event semantics are identical to seed/CLI.
Tenant scoping rides the D-007 filter: ``get_current_user`` set the tenant context, and the
service also passes ``current.tenant_id`` explicitly, so a request can only ever touch its own
tenant's accounts and periods.

The ORM object a write produces is validated into its Read schema AFTER ``run_in_uow`` commits
(``expire_on_commit=False`` keeps the attributes loaded), not inside the uow work — validating a
just-flushed object whose ``updated_at`` is expired would trigger an async lazy-load in a sync
serialization context.

Action sub-resources (``/close``, ``/open``) follow STRUCTURE §7 (actions as sub-resources,
never verbs in resource names).
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_ACCOUNT_MANAGE,
    FINANCE_ACCOUNT_READ,
    FINANCE_PERIOD_MANAGE,
    FINANCE_PERIOD_READ,
)
from app.modules.finance.schemas import (
    AccountCreate,
    AccountFilter,
    AccountGroupCreate,
    AccountGroupRead,
    AccountRead,
    AccountUpdate,
    FiscalPeriodRead,
    FiscalYearCreate,
    FiscalYearRead,
)

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])

CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 unit of work and return its ORM result. The
    result is captured in a one-slot holder because ``run_in_uow`` returns None. The object
    is refreshed inside the awaited work so server-side defaults / ``onupdate`` columns
    (``created_at``, ``updated_at``) are materialized in the async context — otherwise the
    caller's synchronous ``model_validate`` would trigger an async lazy-load on an expired
    attribute and raise MissingGreenlet."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


# --- Accounts -----------------------------------------------------------------


@router.get(
    "/accounts",
    response_model=Page[AccountRead],
    dependencies=[Depends(require_permission(FINANCE_ACCOUNT_READ))],
)
async def list_accounts(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    account_type: str | None = None,
    is_postable: bool | None = None,
    is_active: bool | None = None,
    account_group_id: uuid.UUID | None = None,
) -> Page[AccountRead]:
    filters = AccountFilter(
        account_type=account_type,
        is_postable=is_postable,
        is_active=is_active,
        account_group_id=account_group_id,
    )
    page = await service.list_accounts(
        session,
        current.tenant_id,
        filters=filters,
        cursor=params.cursor,
        limit=params.limit,
    )
    return Page(
        items=[AccountRead.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


@router.post(
    "/accounts",
    response_model=AccountRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_ACCOUNT_MANAGE))],
)
async def create_account(
    payload: AccountCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> AccountRead:
    account = await _commit(
        session, lambda: service.create_account(session, current.tenant_id, payload)
    )
    return AccountRead.model_validate(account)


@router.get(
    "/accounts/{account_id}",
    response_model=AccountRead,
    dependencies=[Depends(require_permission(FINANCE_ACCOUNT_READ))],
)
async def get_account(
    account_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> AccountRead:
    account = await service.get_account(session, current.tenant_id, account_id)
    return AccountRead.model_validate(account)


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountRead,
    dependencies=[Depends(require_permission(FINANCE_ACCOUNT_MANAGE))],
)
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> AccountRead:
    account = await _commit(
        session,
        lambda: service.update_account(session, current.tenant_id, account_id, payload),
    )
    return AccountRead.model_validate(account)


# --- Account groups -----------------------------------------------------------


@router.get(
    "/account-groups",
    response_model=list[AccountGroupRead],
    dependencies=[Depends(require_permission(FINANCE_ACCOUNT_READ))],
)
async def list_account_groups(
    current: CurrentUserDep,
    session: SessionDep,
) -> list[AccountGroupRead]:
    groups = await service.list_account_groups(session, current.tenant_id)
    return [AccountGroupRead.model_validate(group) for group in groups]


@router.post(
    "/account-groups",
    response_model=AccountGroupRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_ACCOUNT_MANAGE))],
)
async def create_account_group(
    payload: AccountGroupCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> AccountGroupRead:
    group = await _commit(
        session, lambda: service.create_account_group(session, current.tenant_id, payload)
    )
    return AccountGroupRead.model_validate(group)


# --- Fiscal years / periods ---------------------------------------------------


@router.get(
    "/fiscal-years",
    response_model=list[FiscalYearRead],
    dependencies=[Depends(require_permission(FINANCE_PERIOD_READ))],
)
async def list_fiscal_years(
    current: CurrentUserDep,
    session: SessionDep,
) -> list[FiscalYearRead]:
    years = await service.list_fiscal_years(session, current.tenant_id)
    return [FiscalYearRead.model_validate(year) for year in years]


@router.post(
    "/fiscal-years",
    response_model=FiscalYearRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_PERIOD_MANAGE))],
)
async def create_fiscal_year(
    payload: FiscalYearCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> FiscalYearRead:
    year = await _commit(
        session, lambda: service.create_fiscal_year(session, current.tenant_id, payload)
    )
    return FiscalYearRead.model_validate(year)


@router.get(
    "/fiscal-periods",
    response_model=list[FiscalPeriodRead],
    dependencies=[Depends(require_permission(FINANCE_PERIOD_READ))],
)
async def list_fiscal_periods(
    current: CurrentUserDep,
    session: SessionDep,
    fiscal_year_id: uuid.UUID | None = None,
) -> list[FiscalPeriodRead]:
    periods = await service.list_fiscal_periods(
        session, current.tenant_id, fiscal_year_id
    )
    return [FiscalPeriodRead.model_validate(period) for period in periods]


@router.post(
    "/fiscal-periods/{period_id}/close",
    response_model=FiscalPeriodRead,
    dependencies=[Depends(require_permission(FINANCE_PERIOD_MANAGE))],
)
async def close_fiscal_period(
    period_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> FiscalPeriodRead:
    period = await _commit(
        session, lambda: service.close_period(session, current.tenant_id, period_id)
    )
    return FiscalPeriodRead.model_validate(period)


@router.post(
    "/fiscal-periods/{period_id}/open",
    response_model=FiscalPeriodRead,
    dependencies=[Depends(require_permission(FINANCE_PERIOD_MANAGE))],
)
async def open_fiscal_period(
    period_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> FiscalPeriodRead:
    period = await _commit(
        session, lambda: service.open_period(session, current.tenant_id, period_id)
    )
    return FiscalPeriodRead.model_validate(period)

"""Finance HTTP layer (thin): parse -> call service -> return schema (PLAN 4.1-4.5; sub-routers).

This file owns the chart-of-accounts and fiscal-calendar REFERENCE endpoints; journal entries
(transactional) live in journal_router.py, FX (D-019) in fx_router.py, tax (4.4) in tax_router.py,
AP/AR/CO/bank/assets in their own sub-routers — all mounted here so the module is ONE surface at
``/api/v1/finance``. Routes are guarded by the finance permission keys (D-009). Writes commit
through ``run_in_uow`` (D-011) so audit rows ride the same transaction; write results are validated
into their Read schema AFTER the uow commits. Actions are sub-resources (STRUCTURE §7).

The slow-changing reference lists (accounts, account-groups, fiscal-years, fiscal-periods) support
conditional GETs via a tenant-scoped collection ETag (PERFORMANCE §3 / D-035): an If-None-Match hit
returns 304 without running the page query.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Request, Response

from app.core.conditional import (
    collection_etag,
    conditional_response,
    request_fingerprint,
)
from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.finance import service
from app.modules.finance.ap_router import ap_router
from app.modules.finance.ar_router import ar_router
from app.modules.finance.assets_router import assets_router
from app.modules.finance.bank_router import bank_router
from app.modules.finance.co_router import co_router
from app.modules.finance.constants import (
    FINANCE_ACCOUNT_MANAGE,
    FINANCE_ACCOUNT_READ,
    FINANCE_PERIOD_MANAGE,
    FINANCE_PERIOD_READ,
)
from app.modules.finance.fx_router import fx_router
from app.modules.finance.journal_router import journal_router
from app.modules.finance.models import (
    Account,
    AccountGroup,
    FiscalPeriod,
    FiscalYear,
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
from app.modules.finance.statements_router import statements_router
from app.modules.finance.tax_router import tax_router

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])
# Journal/FX/tax/AP/AR/CO/statements/bank/assets (4.2-4.10) sub-routers mount here (one surface).
for _sub in (journal_router, fx_router, tax_router, ap_router, ar_router, co_router,
             statements_router, bank_router, assets_router):
    router.include_router(_sub)
CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, returning its ORM result refreshed in the async
    context so a sync ``model_validate`` never trips MissingGreenlet (twin of fx_router._commit)."""
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
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    account_type: str | None = None,
    is_postable: bool | None = None,
    is_active: bool | None = None,
    account_group_id: uuid.UUID | None = None,
) -> Page[AccountRead] | Response:
    """Conditional-GET supported (PERFORMANCE §3 / D-035): the collection ETag covers the whole
    chart of accounts (tenant-scoped) plus this exact page request, so an If-None-Match hit
    returns 304 without running the page query."""
    filters = AccountFilter(
        account_type=account_type,
        is_postable=is_postable,
        is_active=is_active,
        account_group_id=account_group_id,
    )
    fingerprint = request_fingerprint(
        params.cursor, params.limit, account_type, is_postable, is_active, account_group_id
    )
    etag = await collection_etag(session, Account, request_fingerprint=fingerprint)

    async def builder() -> Page[AccountRead]:
        page = await service.list_accounts(
            session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, AccountRead)

    return await conditional_response(request, response, etag, builder)


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
        session, lambda: service.update_account(session, current.tenant_id, account_id, payload)
    )
    return AccountRead.model_validate(account)


# --- Account groups -----------------------------------------------------------


@router.get(
    "/account-groups",
    response_model=Page[AccountGroupRead],
    dependencies=[Depends(require_permission(FINANCE_ACCOUNT_READ))],
)
async def list_account_groups(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[AccountGroupRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the account-group tree."""
    fingerprint = request_fingerprint(params.cursor, params.limit)
    etag = await collection_etag(session, AccountGroup, request_fingerprint=fingerprint)

    async def builder() -> Page[AccountGroupRead]:
        page = await service.list_account_groups(
            session, current.tenant_id, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, AccountGroupRead)

    return await conditional_response(request, response, etag, builder)


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
    response_model=Page[FiscalYearRead],
    dependencies=[Depends(require_permission(FINANCE_PERIOD_READ))],
)
async def list_fiscal_years(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[FiscalYearRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the fiscal-year calendar."""
    fingerprint = request_fingerprint(params.cursor, params.limit)
    etag = await collection_etag(session, FiscalYear, request_fingerprint=fingerprint)

    async def builder() -> Page[FiscalYearRead]:
        page = await service.list_fiscal_years(
            session, current.tenant_id, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, FiscalYearRead)

    return await conditional_response(request, response, etag, builder)


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
    response_model=Page[FiscalPeriodRead],
    dependencies=[Depends(require_permission(FINANCE_PERIOD_READ))],
)
async def list_fiscal_periods(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    fiscal_year_id: uuid.UUID | None = None,
) -> Page[FiscalPeriodRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the fiscal-period calendar; the
    fiscal_year_id filter is folded into the request fingerprint so a filtered 304 is correct."""
    fingerprint = request_fingerprint(params.cursor, params.limit, fiscal_year_id)
    etag = await collection_etag(session, FiscalPeriod, request_fingerprint=fingerprint)

    async def builder() -> Page[FiscalPeriodRead]:
        page = await service.list_fiscal_periods(
            session, current.tenant_id, fiscal_year_id, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, FiscalPeriodRead)

    return await conditional_response(request, response, etag, builder)


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

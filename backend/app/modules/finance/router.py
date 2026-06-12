"""Finance HTTP layer (thin): parse -> call service -> return schema (PLAN 4.1-4.5; sub-routers).

Routes are guarded by the finance permission keys (D-009). Writes commit through ``run_in_uow``
(D-011) so audit rows ride the same transaction; the journal post/reverse actions are IDEMPOTENT
(D-013). Tenant scoping rides the D-007 filter plus the explicit ``current.tenant_id``. Write
results are validated into their Read schema AFTER the uow commits. Actions are sub-resources
(STRUCTURE §7); FX (D-019), tax (4.4) and AP (4.5) endpoints live in their own sub-routers.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.finance import service
from app.modules.finance.ap_router import ap_router
from app.modules.finance.ar_router import ar_router
from app.modules.finance.co_router import co_router
from app.modules.finance.constants import (
    FINANCE_ACCOUNT_MANAGE,
    FINANCE_ACCOUNT_READ,
    FINANCE_JOURNAL_POST,
    FINANCE_JOURNAL_READ,
    FINANCE_JOURNAL_REVERSE,
    FINANCE_PERIOD_MANAGE,
    FINANCE_PERIOD_READ,
)
from app.modules.finance.fx_router import fx_router
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
    JournalEntryCreate,
    JournalEntryDetail,
    JournalEntryRead,
    JournalEntryReverseRequest,
    JournalLineRead,
)
from app.modules.finance.statements_router import statements_router
from app.modules.finance.tax_router import tax_router

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])
# FX/tax/AP/AR/controlling/statements (4.3-4.8) sub-routers mount here (one surface).
for _sub in (fx_router, tax_router, ap_router, ar_router, co_router, statements_router):
    router.include_router(_sub)
CursorParamsDep = Depends(cursor_params)
# Module-level Depends singletons (ruff B008): each is the D-013 reservation guard for its endpoint.
_PostIdempotentDep = Depends(Idempotent("finance.journal.post"))
_ReverseIdempotentDep = Depends(Idempotent("finance.journal.reverse"))


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
        session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, AccountRead)


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
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[AccountGroupRead]:
    page = await service.list_account_groups(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, AccountGroupRead)


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
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[FiscalYearRead]:
    page = await service.list_fiscal_years(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, FiscalYearRead)


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
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    fiscal_year_id: uuid.UUID | None = None,
) -> Page[FiscalPeriodRead]:
    page = await service.list_fiscal_periods(
        session, current.tenant_id, fiscal_year_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, FiscalPeriodRead)


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


# --- Journal entries (D-017) --------------------------------------------------


async def _entry_detail(
    session: SessionDep, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> JournalEntryDetail:
    """Load an entry + its lines into the detail schema. ``refresh`` materializes the server-side
    ``updated_at`` in the async context before the sync ``model_validate`` (else an expired
    attribute triggers an async lazy-load in sync serialization — MissingGreenlet)."""
    entry, lines = await service.get_entry_with_lines(session, tenant_id, entry_id)
    await session.refresh(entry)
    header = JournalEntryRead.model_validate(entry)
    return JournalEntryDetail(
        **header.model_dump(),
        lines=[JournalLineRead.model_validate(line) for line in lines],
    )


@router.post(
    "/journal-entries",
    response_model=JournalEntryRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_JOURNAL_POST))],
)
async def create_journal_entry(
    payload: JournalEntryCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> JournalEntryRead:
    """Create a DRAFT entry (no number claimed). journal.post covers create + post."""
    entry = await _commit(
        session, lambda: service.create_draft_entry(session, current.tenant_id, payload)
    )
    return JournalEntryRead.model_validate(entry)


@router.post(
    "/journal-entries/{entry_id}/post",
    response_model=JournalEntryDetail,
    dependencies=[Depends(require_permission(FINANCE_JOURNAL_POST))],
)
async def post_journal_entry(
    entry_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PostIdempotentDep,
) -> JournalEntryDetail:
    """Post a draft entry (D-017). IDEMPOTENT (D-013): capture() lands in the posting uow, so the
    document and the replay record commit atomically."""
    holder: dict[str, JournalEntryDetail] = {}

    async def work() -> None:
        await service.post_entry(session, current.tenant_id, entry_id)
        detail = await _entry_detail(session, current.tenant_id, entry_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@router.post(
    "/journal-entries/{entry_id}/reverse",
    response_model=JournalEntryDetail,
    dependencies=[Depends(require_permission(FINANCE_JOURNAL_REVERSE))],
)
async def reverse_journal_entry(
    entry_id: uuid.UUID,
    payload: JournalEntryReverseRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ReverseIdempotentDep,
) -> JournalEntryDetail:
    """Reverse a posted entry (D-017); returns the NEW reversing entry with lines. IDEMPOTENT."""
    holder: dict[str, JournalEntryDetail] = {}

    async def work() -> None:
        reversal = await service.reverse_entry(
            session,
            current.tenant_id,
            entry_id,
            payload.reversal_date,
            payload.description,
        )
        detail = await _entry_detail(session, current.tenant_id, reversal.id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@router.get(
    "/journal-entries",
    response_model=Page[JournalEntryRead],
    dependencies=[Depends(require_permission(FINANCE_JOURNAL_READ))],
)
async def list_journal_entries(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
) -> Page[JournalEntryRead]:
    page = await service.list_entries(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        status=status,
    )
    return map_page(page, JournalEntryRead)


@router.get(
    "/journal-entries/{entry_id}",
    response_model=JournalEntryDetail,
    dependencies=[Depends(require_permission(FINANCE_JOURNAL_READ))],
)
async def get_journal_entry(
    entry_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> JournalEntryDetail:
    return await _entry_detail(session, current.tenant_id, entry_id)

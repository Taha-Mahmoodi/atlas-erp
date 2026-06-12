"""Tax-code HTTP layer (PLAN 4.4), included into the finance router.

Split out of router.py (which is at the STRUCTURE §3 400-line cap) the same way fx_router.py is:
mounted via ``router.include_router(tax_router)`` so the module stays ONE surface at
``/api/v1/finance`` — there is no second mount in main.py. Reads are guarded by
``finance.tax.read``, writes by ``finance.tax.manage`` (D-009). Writes commit through
``run_in_uow`` (D-011) so audit rides the transaction; the list is cursor-paginated (D-014).
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
from app.modules.finance.constants import FINANCE_TAX_MANAGE, FINANCE_TAX_READ
from app.modules.finance.schemas import TaxCodeCreate, TaxCodeRead, TaxCodeUpdate

tax_router = APIRouter(tags=["finance-tax"])

CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow and return its ORM result, refreshing it inside the
    work so server defaults materialize in the async context (same pattern as the finance and FX
    routers; duplicated here rather than cross-imported to keep the sub-router self-contained)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


@tax_router.get(
    "/tax-codes",
    response_model=Page[TaxCodeRead],
    dependencies=[Depends(require_permission(FINANCE_TAX_READ))],
)
async def list_tax_codes(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    is_active: bool | None = None,
) -> Page[TaxCodeRead]:
    page = await service.list_tax_codes(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        is_active=is_active,
    )
    return Page(
        items=[TaxCodeRead.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


@tax_router.post(
    "/tax-codes",
    response_model=TaxCodeRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_TAX_MANAGE))],
)
async def create_tax_code(
    payload: TaxCodeCreate, current: CurrentUserDep, session: SessionDep
) -> TaxCodeRead:
    tax_code = await _commit(
        session, lambda: service.create_tax_code(session, current.tenant_id, payload)
    )
    return TaxCodeRead.model_validate(tax_code)


@tax_router.get(
    "/tax-codes/{tax_code_id}",
    response_model=TaxCodeRead,
    dependencies=[Depends(require_permission(FINANCE_TAX_READ))],
)
async def get_tax_code(
    tax_code_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> TaxCodeRead:
    tax_code = await service.get_tax_code(session, current.tenant_id, tax_code_id)
    return TaxCodeRead.model_validate(tax_code)


@tax_router.patch(
    "/tax-codes/{tax_code_id}",
    response_model=TaxCodeRead,
    dependencies=[Depends(require_permission(FINANCE_TAX_MANAGE))],
)
async def update_tax_code(
    tax_code_id: uuid.UUID,
    payload: TaxCodeUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> TaxCodeRead:
    tax_code = await _commit(
        session,
        lambda: service.update_tax_code(session, current.tenant_id, tax_code_id, payload),
    )
    return TaxCodeRead.model_validate(tax_code)

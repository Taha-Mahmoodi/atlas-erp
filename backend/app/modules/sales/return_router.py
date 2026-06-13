"""Sales-return (RMA) HTTP layer (PLAN 7.4), included into the sales router.

A sibling router under the same ``/api/v1/sales`` prefix, mounted by ``router.include_router`` in
router.py (the delivery_router precedent — ONE module surface, no second mount in main.py).

RBAC (D-009; distinct authorities):
  - read by ``sales.return.read``;
  - create/cancel the DRAFT by ``sales.return.manage``;
  - the POST action (receive stock reversing COGS + post the credit note reversing revenue) by the
    distinct ``sales.return.post`` (the journal.post / delivery.post precedent).

Writes commit through ``run_in_uow`` (D-011) so the return + its stock receipt + the credit note it
triggers commit (or roll back) atomically; the create + post endpoints are IDEMPOTENT (D-013). The
list is O(1) queries + paginated (PERFORMANCE §6).
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.sales import service
from app.modules.sales.constants import (
    SALES_RETURN_MANAGE,
    SALES_RETURN_POST,
    SALES_RETURN_READ,
)
from app.modules.sales.schemas import (
    ReturnCreate,
    ReturnDetail,
    ReturnLineRead,
    ReturnRead,
)

return_router = APIRouter(tags=["sales-returns"])

CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("sales.return.create"))
_PostIdem = Depends(Idempotent("sales.return.post"))


async def return_detail(
    session: SessionDep, tenant_id: uuid.UUID, return_id: uuid.UUID
) -> ReturnDetail:
    sales_return = await service.get_return(session, tenant_id, return_id)
    await session.refresh(sales_return)
    lines = await service.get_return_lines(session, tenant_id, return_id)
    header = ReturnRead.model_validate(sales_return)
    return ReturnDetail(
        **header.model_dump(),
        lines=[ReturnLineRead.model_validate(line) for line in lines],
    )


@return_router.post(
    "/returns",
    response_model=ReturnDetail,
    status_code=201,
    dependencies=[Depends(require_permission(SALES_RETURN_MANAGE))],
)
async def create_return(
    payload: ReturnCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> ReturnDetail:
    """Create a DRAFT return against a sales order (PLAN 7.4): each line within the
    invoiced-not-returned quantity (over-return → 422), the receiving bin exists. IDEMPOTENT
    (D-013)."""
    holder: dict[str, ReturnDetail] = {}

    async def work() -> None:
        sales_return = await service.create_return(session, current.tenant_id, payload)
        detail = await return_detail(session, current.tenant_id, sales_return.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@return_router.get(
    "/returns",
    response_model=Page[ReturnRead],
    dependencies=[Depends(require_permission(SALES_RETURN_READ))],
)
async def list_returns(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    sales_order_id: uuid.UUID | None = None,
    status: str | None = None,
) -> Page[ReturnRead]:
    page = await service.list_returns(
        session,
        current.tenant_id,
        sales_order_id=sales_order_id,
        status=status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, ReturnRead)


@return_router.get(
    "/returns/{return_id}",
    response_model=ReturnDetail,
    dependencies=[Depends(require_permission(SALES_RETURN_READ))],
)
async def get_return(
    return_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ReturnDetail:
    return await return_detail(session, current.tenant_id, return_id)


@return_router.post(
    "/returns/{return_id}/post",
    response_model=ReturnDetail,
    dependencies=[Depends(require_permission(SALES_RETURN_POST))],
)
async def post_return(
    return_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PostIdem,
) -> ReturnDetail:
    """Post a DRAFT return (PLAN 7.4, D-046): receives stock back (Dr Inventory / Cr COGS, reversing
    the issue) AND posts an AR credit note (Dr revenue / Cr AR, reversing the billing) via the event
    bus, raises the order line returned_quantity — all one transaction. A closed return period rolls
    the whole post back. IDEMPOTENT (D-013)."""
    holder: dict[str, ReturnDetail] = {}

    async def work() -> None:
        await service.post_return(session, current.tenant_id, return_id)
        detail = await return_detail(session, current.tenant_id, return_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@return_router.post(
    "/returns/{return_id}/cancel",
    response_model=ReturnDetail,
    dependencies=[Depends(require_permission(SALES_RETURN_MANAGE))],
)
async def cancel_return(
    return_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ReturnDetail:
    """Cancel a DRAFT return (PLAN 7.4). A POSTED return is terminal."""
    holder: dict[str, ReturnDetail] = {}

    async def work() -> None:
        await service.cancel_return(session, current.tenant_id, return_id)
        holder["read"] = await return_detail(session, current.tenant_id, return_id)

    await run_in_uow(session, work)
    return holder["read"]

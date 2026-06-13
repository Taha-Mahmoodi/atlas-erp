"""Sales-billing HTTP layer (PLAN 7.4), included into the sales router.

A sibling router under the same ``/api/v1/sales`` prefix, mounted by ``router.include_router`` in
router.py (the delivery_router precedent — ONE module surface, no second mount in main.py).

RBAC (D-009; distinct authorities):
  - read by ``sales.billing.read``;
  - create/cancel the DRAFT by ``sales.billing.manage``;
  - the POST action (trigger the AR customer invoice — recognize revenue + AR) by the distinct
    ``sales.billing.post`` (the journal.post / delivery.post precedent).

Writes commit through ``run_in_uow`` (D-011) so the billing + the AR invoice it triggers commit (or
roll back) atomically; the create + post endpoints are IDEMPOTENT (D-013). The list is O(1) queries
+
paginated (PERFORMANCE §6).
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
    SALES_BILLING_MANAGE,
    SALES_BILLING_POST,
    SALES_BILLING_READ,
)
from app.modules.sales.schemas import (
    BillingCreate,
    BillingDetail,
    BillingLineRead,
    BillingRead,
)

billing_router = APIRouter(tags=["sales-billing"])

CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("sales.billing.create"))
_PostIdem = Depends(Idempotent("sales.billing.post"))


async def billing_detail(
    session: SessionDep, tenant_id: uuid.UUID, billing_id: uuid.UUID
) -> BillingDetail:
    billing = await service.get_billing(session, tenant_id, billing_id)
    await session.refresh(billing)
    lines = await service.get_billing_lines(session, tenant_id, billing_id)
    header = BillingRead.model_validate(billing)
    return BillingDetail(
        **header.model_dump(),
        lines=[BillingLineRead.model_validate(line) for line in lines],
    )


@billing_router.post(
    "/billings",
    response_model=BillingDetail,
    status_code=201,
    dependencies=[Depends(require_permission(SALES_BILLING_MANAGE))],
)
async def create_billing(
    payload: BillingCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> BillingDetail:
    """Create a DRAFT billing against a sales order (PLAN 7.4): the order must be at least partially
    delivered, each line within the delivered-not-invoiced quantity (over-billing → 422). IDEMPOTENT
    (D-013)."""
    holder: dict[str, BillingDetail] = {}

    async def work() -> None:
        billing = await service.create_billing(session, current.tenant_id, payload)
        detail = await billing_detail(session, current.tenant_id, billing.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@billing_router.get(
    "/billings",
    response_model=Page[BillingRead],
    dependencies=[Depends(require_permission(SALES_BILLING_READ))],
)
async def list_billings(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    sales_order_id: uuid.UUID | None = None,
    status: str | None = None,
) -> Page[BillingRead]:
    page = await service.list_billings(
        session,
        current.tenant_id,
        sales_order_id=sales_order_id,
        status=status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, BillingRead)


@billing_router.get(
    "/billings/{billing_id}",
    response_model=BillingDetail,
    dependencies=[Depends(require_permission(SALES_BILLING_READ))],
)
async def get_billing(
    billing_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> BillingDetail:
    return await billing_detail(session, current.tenant_id, billing_id)


@billing_router.post(
    "/billings/{billing_id}/post",
    response_model=BillingDetail,
    dependencies=[Depends(require_permission(SALES_BILLING_POST))],
)
async def post_billing(
    billing_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PostIdem,
) -> BillingDetail:
    """Post a DRAFT billing (PLAN 7.4, D-046): triggers the finance AR customer invoice (Dr AR / Cr
    revenue + tax via the event bus), raises the order line invoiced_quantity, advances the order
    (INVOICED / CLOSED) — all one transaction. A closed billing period rolls the whole post back.
    IDEMPOTENT (D-013)."""
    holder: dict[str, BillingDetail] = {}

    async def work() -> None:
        await service.post_billing(session, current.tenant_id, billing_id)
        detail = await billing_detail(session, current.tenant_id, billing_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@billing_router.post(
    "/billings/{billing_id}/cancel",
    response_model=BillingDetail,
    dependencies=[Depends(require_permission(SALES_BILLING_MANAGE))],
)
async def cancel_billing(
    billing_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> BillingDetail:
    """Cancel a DRAFT billing (PLAN 7.4). A POSTED billing is terminal (corrected by a return /
    credit note)."""
    holder: dict[str, BillingDetail] = {}

    async def work() -> None:
        await service.cancel_billing(session, current.tenant_id, billing_id)
        holder["read"] = await billing_detail(session, current.tenant_id, billing_id)

    await run_in_uow(session, work)
    return holder["read"]

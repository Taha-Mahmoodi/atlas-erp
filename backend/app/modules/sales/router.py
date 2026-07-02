"""Sales HTTP layer (thin): parse -> call service -> return schema (PLAN 7.1).

REST under ``/api/v1/sales``. This file owns the customer master (CRUD + filtered paginated list)
and the customer-group master (CRUD + list), and MOUNTS the sub-routers (the procurement sub-router
precedent: split at the 400-line cap, kept ONE surface via ``router.include_router``, no second
mount
in main.py):

- pricing_router: price lists + items + the price-quote resolver (7.1).
- quote_router: sales quotations + send/accept/reject/cancel/convert actions (7.2).
- order_router: sales orders + confirm (ATP + credit gate) / credit-release / cancel actions and the
  ATP-check endpoint (7.2).
- delivery_router: outbound deliveries + post (issue stock + COGS) / cancel actions (7.3).
- billing_router: billings + post (trigger the AR customer invoice) / cancel actions (7.4).
- return_router: returns (RMA) + post (receive stock + credit note) / cancel actions (7.4).

Every route is guarded by a sales permission key (D-009; manage vs read distinct). Writes commit
through ``run_in_uow`` (D-011) so audit rows ride the same transaction.

The customer + customer-group lists are slow-changing reference data, so they support conditional
GETs via a tenant-scoped collection ETag (PERFORMANCE §3 / D-035): an If-None-Match hit returns 304
without running the page query. The customer status filter folds into the request fingerprint so a
filtered 304 is correct.
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
from app.modules.sales import service
from app.modules.sales.billing_router import billing_router
from app.modules.sales.constants import (
    SALES_CUSTOMER_MANAGE,
    SALES_CUSTOMER_READ,
)
from app.modules.sales.delivery_router import delivery_router
from app.modules.sales.models import Customer, CustomerGroup
from app.modules.sales.order_router import order_router
from app.modules.sales.pricing_router import pricing_router
from app.modules.sales.quote_router import quote_router
from app.modules.sales.return_router import return_router
from app.modules.sales.schemas import (
    CustomerCreate,
    CustomerFilter,
    CustomerGroupCreate,
    CustomerGroupRead,
    CustomerGroupUpdate,
    CustomerRead,
    CustomerUpdate,
)

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])
CursorParamsDep = Depends(cursor_params)

# Mount the sub-routers under the same /api/v1/sales prefix (the procurement sub-router precedent —
# one module surface, included here so main.py mounts once).
router.include_router(pricing_router)
router.include_router(quote_router)
router.include_router(order_router)
router.include_router(delivery_router)
router.include_router(billing_router)
router.include_router(return_router)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, returning its ORM result refreshed in the async
    context so a sync ``model_validate`` never trips MissingGreenlet (the procurement _commit
    twin)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


# --- Customer groups ----------------------------------------------------------


@router.get(
    "/customer-groups",
    response_model=Page[CustomerGroupRead],
    dependencies=[Depends(require_permission(SALES_CUSTOMER_READ))],
)
async def list_customer_groups(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[CustomerGroupRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the customer-group reference list."""
    fingerprint = request_fingerprint(params.cursor, params.limit)
    etag = await collection_etag(session, CustomerGroup, request_fingerprint=fingerprint)

    async def builder() -> Page[CustomerGroupRead]:
        page = await service.list_customer_groups(
            session, current.tenant_id, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, CustomerGroupRead)

    return await conditional_response(request, response, etag, builder)


@router.post(
    "/customer-groups",
    response_model=CustomerGroupRead,
    status_code=201,
    dependencies=[Depends(require_permission(SALES_CUSTOMER_MANAGE))],
)
async def create_customer_group(
    payload: CustomerGroupCreate, current: CurrentUserDep, session: SessionDep
) -> CustomerGroupRead:
    group = await _commit(
        session, lambda: service.create_customer_group(session, current.tenant_id, payload)
    )
    return CustomerGroupRead.model_validate(group)


@router.get(
    "/customer-groups/{group_id}",
    response_model=CustomerGroupRead,
    dependencies=[Depends(require_permission(SALES_CUSTOMER_READ))],
)
async def get_customer_group(
    group_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> CustomerGroupRead:
    group = await service.get_customer_group(session, current.tenant_id, group_id)
    return CustomerGroupRead.model_validate(group)


@router.patch(
    "/customer-groups/{group_id}",
    response_model=CustomerGroupRead,
    dependencies=[Depends(require_permission(SALES_CUSTOMER_MANAGE))],
)
async def update_customer_group(
    group_id: uuid.UUID,
    payload: CustomerGroupUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> CustomerGroupRead:
    group = await _commit(
        session,
        lambda: service.update_customer_group(session, current.tenant_id, group_id, payload),
    )
    return CustomerGroupRead.model_validate(group)


# --- Customers ----------------------------------------------------------------


@router.get(
    "/customers",
    response_model=Page[CustomerRead],
    dependencies=[Depends(require_permission(SALES_CUSTOMER_READ))],
)
async def list_customers(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
) -> Page[CustomerRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the customer reference list; the
    status filter folds into the request fingerprint so a filtered 304 is correct."""
    filters = CustomerFilter(status=status)
    fingerprint = request_fingerprint(params.cursor, params.limit, status)
    etag = await collection_etag(session, Customer, request_fingerprint=fingerprint)

    async def builder() -> Page[CustomerRead]:
        page = await service.list_customers(
            session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, CustomerRead)

    return await conditional_response(request, response, etag, builder)


@router.post(
    "/customers",
    response_model=CustomerRead,
    status_code=201,
    dependencies=[Depends(require_permission(SALES_CUSTOMER_MANAGE))],
)
async def create_customer(
    payload: CustomerCreate, current: CurrentUserDep, session: SessionDep
) -> CustomerRead:
    customer = await _commit(
        session, lambda: service.create_customer(session, current.tenant_id, payload)
    )
    return CustomerRead.model_validate(customer)


@router.get(
    "/customers/{customer_id}",
    response_model=CustomerRead,
    dependencies=[Depends(require_permission(SALES_CUSTOMER_READ))],
)
async def get_customer(
    customer_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> CustomerRead:
    customer = await service.get_customer(session, current.tenant_id, customer_id)
    return CustomerRead.model_validate(customer)


@router.patch(
    "/customers/{customer_id}",
    response_model=CustomerRead,
    dependencies=[Depends(require_permission(SALES_CUSTOMER_MANAGE))],
)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> CustomerRead:
    customer = await _commit(
        session,
        lambda: service.update_customer(session, current.tenant_id, customer_id, payload),
    )
    return CustomerRead.model_validate(customer)

"""Procurement HTTP layer (thin): parse -> call service -> return schema (PLAN 6.1).

REST under ``/api/v1/procurement``: vendors (CRUD + filtered paginated list) and the per-vendor
approved-items nested resource (GET/POST the collection, DELETE one by item id). Every route is
guarded by a procurement permission key (D-009). Writes commit through ``run_in_uow`` (D-011) so
audit rows ride the same transaction; results are validated into their Read schema AFTER the uow
commits.

The vendor list is slow-changing reference data, so it supports conditional GETs via a tenant-scoped
collection ETag (PERFORMANCE §3 / D-035): an If-None-Match hit returns 304 without running the page
query. The status filter folds into the request fingerprint so a filtered 304 is correct.
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
from app.modules.procurement import service
from app.modules.procurement.constants import (
    PROCUREMENT_VENDOR_MANAGE,
    PROCUREMENT_VENDOR_READ,
)
from app.modules.procurement.models import Vendor
from app.modules.procurement.schemas import (
    VendorApprovedItemCreate,
    VendorApprovedItemRead,
    VendorCreate,
    VendorFilter,
    VendorRead,
    VendorUpdate,
)

router = APIRouter(prefix="/api/v1/procurement", tags=["procurement"])
CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, returning its ORM result refreshed in the async
    context so a sync ``model_validate`` never trips MissingGreenlet (twin of inventory _commit)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


# --- Vendors ------------------------------------------------------------------


@router.get(
    "/vendors",
    response_model=Page[VendorRead],
    dependencies=[Depends(require_permission(PROCUREMENT_VENDOR_READ))],
)
async def list_vendors(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
) -> Page[VendorRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the vendor reference list; the
    status filter folds into the request fingerprint so a filtered 304 is correct."""
    filters = VendorFilter(status=status)
    fingerprint = request_fingerprint(params.cursor, params.limit, status)
    etag = await collection_etag(session, Vendor, request_fingerprint=fingerprint)

    async def builder() -> Page[VendorRead]:
        page = await service.list_vendors(
            session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, VendorRead)

    return await conditional_response(request, response, etag, builder)


@router.post(
    "/vendors",
    response_model=VendorRead,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_VENDOR_MANAGE))],
)
async def create_vendor(
    payload: VendorCreate, current: CurrentUserDep, session: SessionDep
) -> VendorRead:
    vendor = await _commit(
        session, lambda: service.create_vendor(session, current.tenant_id, payload)
    )
    return VendorRead.model_validate(vendor)


@router.get(
    "/vendors/{vendor_id}",
    response_model=VendorRead,
    dependencies=[Depends(require_permission(PROCUREMENT_VENDOR_READ))],
)
async def get_vendor(
    vendor_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> VendorRead:
    vendor = await service.get_vendor(session, current.tenant_id, vendor_id)
    return VendorRead.model_validate(vendor)


@router.patch(
    "/vendors/{vendor_id}",
    response_model=VendorRead,
    dependencies=[Depends(require_permission(PROCUREMENT_VENDOR_MANAGE))],
)
async def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> VendorRead:
    vendor = await _commit(
        session, lambda: service.update_vendor(session, current.tenant_id, vendor_id, payload)
    )
    return VendorRead.model_validate(vendor)


# --- Approved items (nested under a vendor) -----------------------------------


@router.get(
    "/vendors/{vendor_id}/approved-items",
    response_model=list[VendorApprovedItemRead],
    dependencies=[Depends(require_permission(PROCUREMENT_VENDOR_READ))],
)
async def list_approved_items(
    vendor_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[VendorApprovedItemRead]:
    approved = await service.list_approved_items(session, current.tenant_id, vendor_id)
    return [VendorApprovedItemRead.model_validate(row) for row in approved]


@router.post(
    "/vendors/{vendor_id}/approved-items",
    response_model=VendorApprovedItemRead,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_VENDOR_MANAGE))],
)
async def add_approved_item(
    vendor_id: uuid.UUID,
    payload: VendorApprovedItemCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> VendorApprovedItemRead:
    approved = await _commit(
        session,
        lambda: service.add_approved_item(session, current.tenant_id, vendor_id, payload),
    )
    return VendorApprovedItemRead.model_validate(approved)


@router.delete(
    "/vendors/{vendor_id}/approved-items/{item_id}",
    status_code=204,
    dependencies=[Depends(require_permission(PROCUREMENT_VENDOR_MANAGE))],
)
async def remove_approved_item(
    vendor_id: uuid.UUID,
    item_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> Response:
    async def _work() -> None:
        await service.remove_approved_item(session, current.tenant_id, vendor_id, item_id)

    await run_in_uow(session, _work)
    return Response(status_code=204)

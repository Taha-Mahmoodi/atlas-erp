"""Procurement vendor-master business logic (PLAN 6.1): vendor CRUD + approved-item management.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. Rules enforced here:

- ``vendor_code`` uniqueness per tenant (friendly ConflictError before the DB UNIQUE would raise);
- ``default_currency_code`` must exist in finance's currency catalog (D-029, via
  ``finance/queries.currency_exists`` — never a cross-module FK);
- ``payment_terms_days`` >= 0 (schema bounds it too; the DB CHECK is the backstop);
- ``status`` transitions are UNRESTRICTED between ACTIVE/BLOCKED/INACTIVE (constants.VendorStatus
  documents why — a block/retire must be reversible; the P2P chain in 6.2 reads the status to refuse
  POs against non-ACTIVE vendors, but the master itself imposes no terminal state);
- approved items: the ``item_id`` must exist in inventory (D-029, via
  ``inventory/queries.item_exists``); a vendor cannot approve the same item twice (friendly
  ConflictError before the UNIQUE backstop).

First file in the procurement ``service/`` package (STRUCTURE §3: split at the 400-line cap when
PLAN
6.2's requisition/RFQ/PO/approval/conversion logic landed, the finance/inventory precedent).
Re-exported from ``service/__init__`` so ``service.create_vendor(...)`` keeps working from one
surface. ``from __future__ import annotations`` keeps ``Page[Vendor]`` (the ORM model) a string at
import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.procurement.constants import VendorStatus
from app.modules.procurement.models import Vendor, VendorApprovedItem
from app.modules.procurement.schemas import (
    VendorApprovedItemCreate,
    VendorCreate,
    VendorFilter,
    VendorUpdate,
)

# --- Vendors ------------------------------------------------------------------


async def _vendor_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, vendor_code: str
) -> Vendor | None:
    stmt = select(Vendor).where(
        Vendor.tenant_id == tenant_id, Vendor.vendor_code == vendor_code
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _validate_currency(
    session: AsyncSession, tenant_id: uuid.UUID, currency_code: str
) -> None:
    """The vendor's default currency must exist in finance's catalog (D-029): validated through the
    finance queries contract, never a cross-module FK."""
    if not await finance_queries.currency_exists(session, tenant_id, currency_code):
        raise ValidationFailedError(
            message=f"Currency {currency_code} does not exist in the finance catalog",
            code="procurement.currency_not_found",
            details={"currency_code": currency_code},
        )


async def get_vendor(
    session: AsyncSession, tenant_id: uuid.UUID, vendor_id: uuid.UUID
) -> Vendor:
    vendor = await session.get(Vendor, vendor_id)
    if vendor is None or vendor.tenant_id != tenant_id:
        raise NotFoundError(message="Vendor not found", code="procurement.vendor_not_found")
    return vendor


async def create_vendor(
    session: AsyncSession, tenant_id: uuid.UUID, payload: VendorCreate
) -> Vendor:
    """Create a vendor. Rejects a duplicate vendor_code; validates the default currency exists in
    finance. ``status`` defaults to ACTIVE; ``payment_terms_days`` defaults to NET30 (schema)."""
    if await _vendor_by_code(session, tenant_id, payload.vendor_code) is not None:
        raise ConflictError(
            message=f"A vendor with code {payload.vendor_code} already exists",
            code="procurement.vendor_code_conflict",
            details={"vendor_code": payload.vendor_code},
        )
    await _validate_currency(session, tenant_id, payload.default_currency_code)
    vendor = Vendor(
        tenant_id=tenant_id,
        vendor_code=payload.vendor_code,
        name=payload.name,
        status=VendorStatus(payload.status).value,
        default_currency_code=payload.default_currency_code,
        payment_terms_days=payload.payment_terms_days,
        tax_reference=payload.tax_reference,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        notes=payload.notes,
    )
    session.add(vendor)
    await session.flush()
    return vendor


async def update_vendor(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
) -> Vendor:
    """Partial update of a vendor (D-010: mutate the loaded object so the audit diff is captured).
    ``vendor_code`` is immutable and absent from the schema; a changed ``default_currency_code`` is
    re-validated against finance; ``status`` may move freely between the three states."""
    vendor = await get_vendor(session, tenant_id, vendor_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("default_currency_code") is not None:
        await _validate_currency(session, tenant_id, data["default_currency_code"])
    if data.get("status") is not None:
        data["status"] = VendorStatus(data["status"]).value
    for field, value in data.items():
        setattr(vendor, field, value)
    await session.flush()
    return vendor


async def list_vendors(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: VendorFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Vendor]:
    """Keyset-paginated vendor list ordered by vendor_code (D-014). The optional status filter
    narrows the set and folds into the cursor fingerprint so a cursor cannot bleed across views
    (the (tenant_id, status) index serves the filtered page, PERFORMANCE §1)."""
    stmt = select(Vendor).where(Vendor.tenant_id == tenant_id)
    if filters.status is not None:
        stmt = stmt.where(Vendor.status == VendorStatus(filters.status).value)
    fingerprint = filter_fingerprint(filters.status)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Vendor.vendor_code, SortDirection.ASC)],
        pk=Vendor.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


# --- Approved items (the v1 info-record-lite) ---------------------------------


async def list_approved_items(
    session: AsyncSession, tenant_id: uuid.UUID, vendor_id: uuid.UUID
) -> list[VendorApprovedItem]:
    """The vendor's approved items, ordered by creation (PLAN 6.1). 404s if the vendor does not
    exist (so a missing vendor and an empty list are distinguishable)."""
    await get_vendor(session, tenant_id, vendor_id)
    stmt = (
        select(VendorApprovedItem)
        .where(
            VendorApprovedItem.tenant_id == tenant_id,
            VendorApprovedItem.vendor_id == vendor_id,
        )
        .order_by(VendorApprovedItem.created_at, VendorApprovedItem.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def add_approved_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    payload: VendorApprovedItemCreate,
) -> VendorApprovedItem:
    """Approve an inventory item for a vendor (info-record-lite). Validates the vendor exists, the
    item exists in inventory (D-029, via ``inventory/queries.item_exists`` — no cross-module FK),
    and the (vendor, item) pair is not already approved (friendly ConflictError before the UNIQUE
    backstop)."""
    await get_vendor(session, tenant_id, vendor_id)
    if not await inventory_queries.item_exists(session, tenant_id, payload.item_id):
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="procurement.item_not_found",
            details={"item_id": str(payload.item_id)},
        )
    existing = (
        await session.execute(
            select(VendorApprovedItem.id).where(
                VendorApprovedItem.tenant_id == tenant_id,
                VendorApprovedItem.vendor_id == vendor_id,
                VendorApprovedItem.item_id == payload.item_id,
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message="This item is already approved for the vendor",
            code="procurement.approved_item_conflict",
            details={"vendor_id": str(vendor_id), "item_id": str(payload.item_id)},
        )
    approved = VendorApprovedItem(
        tenant_id=tenant_id,
        vendor_id=vendor_id,
        item_id=payload.item_id,
        vendor_item_code=payload.vendor_item_code,
        is_active=payload.is_active,
    )
    session.add(approved)
    await session.flush()
    return approved


async def remove_approved_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    item_id: uuid.UUID,
) -> None:
    """Un-approve an item for a vendor (PLAN 6.1). 404s if the (vendor, item) approval does not
    exist. A hard delete: the approved-item link is low-churn config with no document history of its
    own (unlike a posted document), so removal is a real delete, not a status flip."""
    stmt = select(VendorApprovedItem).where(
        VendorApprovedItem.tenant_id == tenant_id,
        VendorApprovedItem.vendor_id == vendor_id,
        VendorApprovedItem.item_id == item_id,
    )
    approved = (await session.execute(stmt)).scalar_one_or_none()
    if approved is None:
        raise NotFoundError(
            message="Approved item not found",
            code="procurement.approved_item_not_found",
        )
    await session.delete(approved)
    await session.flush()

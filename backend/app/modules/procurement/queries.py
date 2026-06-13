"""Procurement's cross-module read interface (STRUCTURE §5).

Procurement sits above inventory (and finance) in the dependency order: the P2P documents in
6.2–6.4 (requisition → RFQ → PO → goods receipt → 3-way match) and finance AP reporting read THIS
file to resolve vendor state synchronously; procurement imports finance/queries + inventory/queries
downward. Keep this surface thin and stable — it is a contract; it is the ONLY procurement file
other modules import.

The central D-029 link: finance AP stores a vendor on each bill/payment as an opaque ``partner_id``
(no FK). ``get_vendor_for_partner`` resolves that ``partner_id`` back to a ``Vendor`` so AP aging /
reporting can render the vendor's name and payment terms — the ``partner_id`` IS the ``Vendor.id``,
so it is a thin alias over ``get_vendor`` named for the reporting intent.

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.procurement.models import Vendor, VendorApprovedItem


async def get_vendor(
    session: AsyncSession, tenant_id: uuid.UUID, vendor_id: uuid.UUID
) -> Vendor | None:
    """The vendor with ``vendor_id`` in the tenant, or None. Lets another module read a vendor's
    master fields (name, status, default currency, payment terms) without importing procurement
    models directly — the analogue of inventory's ``get_item``."""
    stmt = select(Vendor).where(Vendor.tenant_id == tenant_id, Vendor.id == vendor_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_vendor_for_partner(
    session: AsyncSession, tenant_id: uuid.UUID, partner_id: uuid.UUID
) -> Vendor | None:
    """The vendor an AP document's opaque ``partner_id`` refers to (D-029), or None. AP aging /
    reporting calls this to resolve a bill's ``partner_id`` to a vendor name + payment terms. The
    ``partner_id`` IS the ``Vendor.id`` (finance stores it without an FK), so this is ``get_vendor``
    named for the reporting intent — kept as its own function so AP call sites read intent-first and
    the alias survives any future indirection."""
    return await get_vendor(session, tenant_id, partner_id)


async def vendor_exists(
    session: AsyncSession, tenant_id: uuid.UUID, vendor_id: uuid.UUID
) -> bool:
    """Whether a vendor with ``vendor_id`` exists in the tenant. The cheap existence check a
    requisition / PO line uses to validate its vendor_id (the procurement analogue of inventory's
    ``item_exists``)."""
    stmt = select(Vendor.id).where(Vendor.tenant_id == tenant_id, Vendor.id == vendor_id)
    return (await session.execute(stmt)).first() is not None


async def vendor_payment_terms_days(
    session: AsyncSession, tenant_id: uuid.UUID, vendor_id: uuid.UUID
) -> int | None:
    """The vendor's net-days payment terms (e.g. 30 = NET30), or None if the vendor does not exist.
    The PO→bill flow (6.4) reads this to default a bill's due date (bill_date + days), the same
    math AP uses today — exposed so the chain need not import procurement models."""
    stmt = select(Vendor.payment_terms_days).where(
        Vendor.tenant_id == tenant_id, Vendor.id == vendor_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def vendor_default_currency(
    session: AsyncSession, tenant_id: uuid.UUID, vendor_id: uuid.UUID
) -> str | None:
    """The vendor's default currency code (ISO alpha-3), or None if the vendor does not exist. The
    PO flow (6.2) defaults a PO's currency from this; exposed so the chain need not import
    procurement models."""
    stmt = select(Vendor.default_currency_code).where(
        Vendor.tenant_id == tenant_id, Vendor.id == vendor_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def is_item_approved_for_vendor(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    item_id: uuid.UUID,
) -> bool:
    """Whether ``item_id`` is an ACTIVE approved item for ``vendor_id`` (PLAN 6.1, the
    info-record-lite).
    The PO flow (6.2) calls this to enforce "only approved sources" when a tenant opts into it (a
    soft policy hook); an inactive approval reads False so a deactivated source is treated as not
    approved. Index-served by ``(tenant_id, vendor_id)``."""
    stmt = select(VendorApprovedItem.id).where(
        VendorApprovedItem.tenant_id == tenant_id,
        VendorApprovedItem.vendor_id == vendor_id,
        VendorApprovedItem.item_id == item_id,
        VendorApprovedItem.is_active.is_(True),
    )
    return (await session.execute(stmt)).first() is not None

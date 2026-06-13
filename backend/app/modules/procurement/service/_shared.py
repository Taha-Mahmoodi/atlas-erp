"""Shared validation + numbering helpers for the P2P document services (PLAN 6.2).

Kept in one private module so the requisition / RFQ / PO services stay small and the cross-module
validation rules (item exists, currency exists, vendor ACTIVE, item approved for vendor) live in ONE
place — greppable and consistent. Every check goes through the owning module's queries contract
(D-029), never a cross-module FK. The numbering helper wraps ensure_sequence + claim_number so the
three documents claim their gapless number at creation identically (D-040).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.procurement import queries as procurement_queries
from app.modules.procurement.constants import VendorStatus


async def validate_currency(
    session: AsyncSession, tenant_id: uuid.UUID, currency_code: str
) -> None:
    """The currency must exist in finance's catalog (D-029, via finance/queries)."""
    if not await finance_queries.currency_exists(session, tenant_id, currency_code):
        raise ValidationFailedError(
            message=f"Currency {currency_code} does not exist in the finance catalog",
            code="procurement.currency_not_found",
            details={"currency_code": currency_code},
        )


async def validate_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    """The item must exist in inventory (D-029, via inventory/queries.item_exists)."""
    if not await inventory_queries.item_exists(session, tenant_id, item_id):
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="procurement.item_not_found",
            details={"item_id": str(item_id)},
        )


def validate_quantity(quantity: Decimal) -> Decimal:
    """A document line quantity must be > 0 (every requisition/RFQ/PO line)."""
    qty = Decimal(str(quantity))
    if qty <= 0:
        raise ValidationFailedError(
            message="A line quantity must be greater than zero",
            code="procurement.line_quantity_invalid",
            details={"quantity": str(qty)},
        )
    return qty


async def require_active_vendor(
    session: AsyncSession, tenant_id: uuid.UUID, vendor_id: uuid.UUID
) -> None:
    """The vendor must exist AND be ACTIVE (not BLOCKED/INACTIVE) — the v1 PO source-control rule.
    Reads the vendor's status via procurement/queries (intra-module). A BLOCKED/INACTIVE vendor
    cannot receive a NEW PO (constants.VendorStatus documents the soft block)."""
    vendor = await procurement_queries.get_vendor(session, tenant_id, vendor_id)
    if vendor is None:
        raise ValidationFailedError(
            message="Referenced vendor does not exist",
            code="procurement.vendor_not_found",
            details={"vendor_id": str(vendor_id)},
        )
    if VendorStatus(vendor.status) != VendorStatus.ACTIVE:
        raise ValidationFailedError(
            message=f"Vendor is {vendor.status}; a purchase order needs an ACTIVE vendor",
            code="procurement.vendor_not_active",
            details={"vendor_id": str(vendor_id), "status": vendor.status},
        )


async def require_item_approved_for_vendor(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    item_id: uuid.UUID,
) -> None:
    """A PO line item MUST be in the vendor's approved-items list — the v1 source-control rule
    (D-040: enforce approved sources). Reads via procurement/queries.is_item_approved_for_vendor (an
    inactive approval counts as not approved). Raises 422 procurement.item_not_approved
    otherwise."""
    if not await procurement_queries.is_item_approved_for_vendor(
        session, tenant_id, vendor_id, item_id
    ):
        raise ValidationFailedError(
            message="The item is not an approved source for this vendor",
            code="procurement.item_not_approved",
            details={"vendor_id": str(vendor_id), "item_id": str(item_id)},
        )


async def claim_document_number(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    sequence_name: str,
    prefix: str,
    padding: int,
    on_date: date,
) -> str:
    """Ensure the sequence exists (year-resetting) and claim the next gapless number (D-040: claimed
    at creation, so a document is referenceable immediately). The claim runs in the caller's
    transaction so gaplessness for committed documents falls out of ACID."""
    await ensure_sequence(session, tenant_id, sequence_name, prefix, padding, year_reset=True)
    return await claim_number(session, tenant_id, sequence_name, on_date=on_date)

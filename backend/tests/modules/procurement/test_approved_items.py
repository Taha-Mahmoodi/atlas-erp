"""Vendor approved-items service tests (PLAN 6.1, the v1 info-record-lite): add/remove/list,
item-exists validation against inventory (D-029), and the no-duplicate rule. Exercises the real
service layer under the tenant context (D-025).
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.procurement import queries, service
from app.modules.procurement.schemas import VendorApprovedItemCreate
from tests.modules.procurement.conftest import ProcurementSetup
from tests.modules.procurement.factories import build_approved_item, build_vendor


async def test_add_and_list_approved_item(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """Approving an item links it to the vendor with the vendor's own SKU; the list returns it."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    approved = await build_approved_item(
        db_session,
        procurement_setup.tenant_id,
        vendor.id,
        procurement_setup.item_id,
        vendor_item_code="SUP-SKU-9",
    )
    assert approved.item_id == procurement_setup.item_id
    assert approved.vendor_item_code == "SUP-SKU-9"

    with tenant_context(procurement_setup.tenant_id):
        rows = await service.list_approved_items(
            db_session, procurement_setup.tenant_id, vendor.id
        )
    assert len(rows) == 1
    assert rows[0].item_id == procurement_setup.item_id


async def test_approve_unknown_item_rejected(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """An item_id not in inventory is a ValidationFailedError (D-029 cross-module validation)."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    with pytest.raises(ValidationFailedError) as err, tenant_context(procurement_setup.tenant_id):
        await service.add_approved_item(
            db_session,
            procurement_setup.tenant_id,
            vendor.id,
            VendorApprovedItemCreate(item_id=uuid.uuid4()),
        )
    assert err.value.code == "procurement.item_not_found"


async def test_cannot_approve_same_item_twice(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A vendor approving the same item twice is a friendly ConflictError (UNIQUE backstop)."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    await build_approved_item(
        db_session, procurement_setup.tenant_id, vendor.id, procurement_setup.item_id
    )
    with pytest.raises(ConflictError) as err, tenant_context(procurement_setup.tenant_id):
        await service.add_approved_item(
            db_session,
            procurement_setup.tenant_id,
            vendor.id,
            VendorApprovedItemCreate(item_id=procurement_setup.item_id),
        )
    assert err.value.code == "procurement.approved_item_conflict"


async def test_approve_for_unknown_vendor_404(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    with pytest.raises(NotFoundError) as err, tenant_context(procurement_setup.tenant_id):
        await service.add_approved_item(
            db_session,
            procurement_setup.tenant_id,
            uuid.uuid4(),
            VendorApprovedItemCreate(item_id=procurement_setup.item_id),
        )
    assert err.value.code == "procurement.vendor_not_found"


async def test_remove_approved_item(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """Removing an approval deletes it; a second removal 404s."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    await build_approved_item(
        db_session, procurement_setup.tenant_id, vendor.id, procurement_setup.item_id
    )
    with tenant_context(procurement_setup.tenant_id):
        await service.remove_approved_item(
            db_session, procurement_setup.tenant_id, vendor.id, procurement_setup.item_id
        )
        await db_session.commit()
        rows = await service.list_approved_items(
            db_session, procurement_setup.tenant_id, vendor.id
        )
    assert rows == []

    with pytest.raises(NotFoundError) as err, tenant_context(procurement_setup.tenant_id):
        await service.remove_approved_item(
            db_session, procurement_setup.tenant_id, vendor.id, procurement_setup.item_id
        )
    assert err.value.code == "procurement.approved_item_not_found"


async def test_is_item_approved_query(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """``is_item_approved_for_vendor`` reflects active approvals; an inactive one reads False."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    with tenant_context(procurement_setup.tenant_id):
        assert not await queries.is_item_approved_for_vendor(
            db_session, procurement_setup.tenant_id, vendor.id, procurement_setup.item_id
        )
    await build_approved_item(
        db_session, procurement_setup.tenant_id, vendor.id, procurement_setup.item_id
    )
    with tenant_context(procurement_setup.tenant_id):
        assert await queries.is_item_approved_for_vendor(
            db_session, procurement_setup.tenant_id, vendor.id, procurement_setup.item_id
        )

    # An inactive approval is treated as not-approved (a deactivated source).
    inactive_vendor = await build_vendor(
        db_session, procurement_setup.tenant_id, vendor_code="V-INACT"
    )
    await build_approved_item(
        db_session,
        procurement_setup.tenant_id,
        inactive_vendor.id,
        procurement_setup.item_id,
        is_active=False,
    )
    with tenant_context(procurement_setup.tenant_id):
        assert not await queries.is_item_approved_for_vendor(
            db_session,
            procurement_setup.tenant_id,
            inactive_vendor.id,
            procurement_setup.item_id,
        )

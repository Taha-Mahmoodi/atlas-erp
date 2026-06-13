"""Procurement test data builders behind tests/modules/procurement/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping
and audit fire exactly as in production. conftest.py keeps only the thin pytest fixtures.

``build_procurement_setup`` wires a tenant ready to create vendors and approved items: it seeds a
currency (USD) in finance — the cross-module read ``default_currency_code`` validates against — and
an inventory item (via the inventory builders) so approved-item validation has a real item to point
at. ``create_procurement_principal`` mirrors the finance/inventory principal pattern with
procurement.* keys (and supports a narrowed ``keys`` grant for the 403 RBAC tests), plus the finance
+ inventory setup keys the cross-module-aware tests need.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service as finance_service
from app.modules.procurement import service
from app.modules.procurement.constants import ApprovalDocumentType
from app.modules.procurement.models import (
    ApprovalRule,
    PurchaseOrder,
    PurchaseRequisition,
    Rfq,
    Vendor,
    VendorApprovedItem,
)
from app.modules.procurement.schemas import (
    ApprovalRuleCreate,
    PurchaseOrderCreate,
    PurchaseOrderLineCreate,
    RequisitionCreate,
    RequisitionLineCreate,
    RfqCreate,
    RfqLineCreate,
    VendorApprovedItemCreate,
    VendorCreate,
)

# EVERY registered procurement.* key (importing procurement.constants registers them), so a new
# procurement permission is auto-granted to the full-rights principal (self-extending).
_PROCUREMENT_KEYS = tuple(
    sorted(key for key in catalog_keys() if key.startswith("procurement."))
)


async def seed_currency(
    session: AsyncSession, tenant_id: uuid.UUID, code: str = "USD", name: str = "US Dollar"
) -> str:
    """Create a currency in finance through the real service (D-025) so the vendor's
    ``default_currency_code`` has something to validate against (D-029). Returns the code."""
    with tenant_context(tenant_id):
        await finance_service.create_currency(session, tenant_id, code=code, name=name)
        await session.commit()
    return code


async def build_vendor(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    vendor_code: str = "V-001",
    name: str = "Acme Supplies",
    default_currency_code: str = "USD",
    **kwargs: object,
) -> Vendor:
    """Create a vendor through the real service (D-025). ``kwargs`` overrides any VendorCreate field
    (status, payment_terms_days, email, ...)."""
    payload_fields: dict[str, object] = {
        "vendor_code": vendor_code,
        "name": name,
        "default_currency_code": default_currency_code,
    }
    payload_fields.update(kwargs)
    with tenant_context(tenant_id):
        vendor = await service.create_vendor(
            session, tenant_id, VendorCreate(**payload_fields)  # type: ignore[arg-type]
        )
        await session.commit()
    return vendor


async def build_approved_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    vendor_item_code: str | None = None,
    is_active: bool = True,
) -> VendorApprovedItem:
    """Approve an item for a vendor through the real service (D-025)."""
    with tenant_context(tenant_id):
        approved = await service.add_approved_item(
            session,
            tenant_id,
            vendor_id,
            VendorApprovedItemCreate(
                item_id=item_id, vendor_item_code=vendor_item_code, is_active=is_active
            ),
        )
        await session.commit()
    return approved


@dataclass(frozen=True)
class ProcurementSetup:
    """A tenant ready to create vendors + approved items: the USD currency code (seeded in finance,
    so a vendor's default_currency_code validates) and a real inventory item id (so approved-item
    validation has something to point at). Plain ids so a rollback (expiring loaded ORM objects)
    cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    currency_code: str
    item_id: uuid.UUID
    uom_id: uuid.UUID


async def build_procurement_setup(
    session: AsyncSession, tenant_id: uuid.UUID
) -> ProcurementSetup:
    """Seed a USD currency (finance) and a STOCKED inventory item (inventory), so vendor creation
    and approved-item validation both have real cross-module data to validate against (D-029)."""
    # Imported lazily so the procurement factories do not hard-depend on the inventory test package
    # at import time (it is only needed when a real item is required).
    from tests.modules.inventory.factories import build_inventory_setup, build_item

    code = await seed_currency(session, tenant_id)
    inv = await build_inventory_setup(session, tenant_id)
    item = await build_item(
        session,
        tenant_id,
        item_code="ITEM-1",
        category_id=inv.category_id,
        base_uom_id=inv.ea_uom_id,
    )
    return ProcurementSetup(
        tenant_id=tenant_id, currency_code=code, item_id=item.id, uom_id=inv.ea_uom_id
    )


# --- P2P documents (PLAN 6.2) -------------------------------------------------


async def build_requisition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    uom_id: uuid.UUID,
    currency_code: str = "USD",
    quantity: str = "10",
    estimated_unit_cost: str | None = "5",
    requested_by: uuid.UUID | None = None,
) -> PurchaseRequisition:
    """Create a DRAFT requisition with one line through the real service (D-025)."""
    with tenant_context(tenant_id):
        req = await service.create_requisition(
            session,
            tenant_id,
            RequisitionCreate(
                requested_by=requested_by,
                lines=[
                    RequisitionLineCreate(
                        item_id=item_id,
                        quantity=Decimal(quantity),
                        uom_id=uom_id,
                        estimated_unit_cost=(
                            None if estimated_unit_cost is None else Decimal(estimated_unit_cost)
                        ),
                        currency_code=currency_code,
                    )
                ],
            ),
        )
        await session.commit()
    return req


async def build_rfq(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    vendor_id: uuid.UUID,
    item_id: uuid.UUID,
    uom_id: uuid.UUID,
    currency_code: str = "USD",
    quantity: str = "10",
) -> Rfq:
    """Create a DRAFT RFQ with one line through the real service (D-025)."""
    with tenant_context(tenant_id):
        rfq = await service.create_rfq(
            session,
            tenant_id,
            RfqCreate(
                vendor_id=vendor_id,
                currency_code=currency_code,
                lines=[
                    RfqLineCreate(
                        item_id=item_id, quantity=Decimal(quantity), uom_id=uom_id
                    )
                ],
            ),
        )
        await session.commit()
    return rfq


async def build_po(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    vendor_id: uuid.UUID,
    item_id: uuid.UUID,
    uom_id: uuid.UUID,
    quantity: str = "10",
    unit_cost: str = "5",
    currency_code: str | None = None,
) -> PurchaseOrder:
    """Create a DRAFT PO with one line through the real service (D-025). The vendor must be ACTIVE
    and the item approved for it (the caller seeds that)."""
    with tenant_context(tenant_id):
        po = await service.create_purchase_order(
            session,
            tenant_id,
            PurchaseOrderCreate(
                vendor_id=vendor_id,
                currency_code=currency_code,
                lines=[
                    PurchaseOrderLineCreate(
                        item_id=item_id,
                        quantity=Decimal(quantity),
                        uom_id=uom_id,
                        unit_cost=Decimal(unit_cost),
                    )
                ],
            ),
        )
        await session.commit()
    return po


async def build_approval_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    document_type: ApprovalDocumentType,
    threshold_amount: str,
    currency_code: str = "USD",
    is_active: bool = True,
) -> ApprovalRule:
    """Create an approval-threshold rule through the real service (D-025)."""
    with tenant_context(tenant_id):
        rule = await service.create_approval_rule(
            session,
            tenant_id,
            ApprovalRuleCreate(
                document_type=document_type,
                threshold_amount=Decimal(threshold_amount),
                currency_code=currency_code,
                is_active=is_active,
            ),
        )
        await session.commit()
    return rule


# --- Principals ---------------------------------------------------------------

# Finance + inventory setup keys the API tests need to scaffold cross-module data through the wire
# (a vendor's currency lives in finance; an approved item points at a real inventory item).
_FINANCE_SETUP_KEYS = ("finance.fx.manage",)
_INVENTORY_SETUP_KEYS = (
    "inventory.uom.manage",
    "inventory.category.manage",
    "inventory.item.manage",
)
_FULL_KEYS = (*_PROCUREMENT_KEYS, *_FINANCE_SETUP_KEYS, *_INVENTORY_SETUP_KEYS)


@dataclass(frozen=True)
class ProcurementPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_procurement_principal(
    session: AsyncSession,
    slug: str = "proc-acme",
    email: str = "buyer@proc-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _FULL_KEYS,
) -> ProcurementPrincipal:
    """Provision a tenant + user and grant a role with the procurement permission keys (plus the
    finance/inventory setup keys for the cross-module API scaffolding) through the real services
    (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Procurement", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return ProcurementPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )

"""Inventory test data builders behind tests/modules/inventory/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping
and audit fire exactly as in production. conftest.py keeps only the thin pytest fixtures.

``build_inventory_setup`` wires a tenant ready to create items: a couple of UoMs (EA, BOX) and a
category whose default costing is MOVING_AVERAGE. ``create_inventory_principal`` mirrors the
finance principal pattern with inventory.* keys (and supports a narrowed ``keys`` grant for the
403 RBAC tests). Where a category needs real finance GL accounts, the builder seeds a small COA
via the finance service first (the cross-module read those accounts validate against).
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service as finance_service
from app.modules.finance.constants import AccountType
from app.modules.finance.schemas import AccountCreate
from app.modules.inventory import service
from app.modules.inventory.constants import CostingMethod
from app.modules.inventory.models import Item, ItemCategory, Uom
from app.modules.inventory.schemas import (
    ItemCategoryCreate,
    ItemCreate,
    UomConversionCreate,
    UomCreate,
)

# EVERY registered inventory.* key (importing inventory.constants registers them), so a new
# inventory permission is auto-granted to the full-rights principal (self-extending).
_INVENTORY_KEYS = tuple(sorted(key for key in catalog_keys() if key.startswith("inventory.")))


async def seed_uom(
    session: AsyncSession, tenant_id: uuid.UUID, code: str, name: str
) -> Uom:
    """Create a unit of measure through the real service (D-025)."""
    with tenant_context(tenant_id):
        uom = await service.create_uom(session, tenant_id, UomCreate(code=code, name=name))
        await session.commit()
    return uom


async def build_item_category(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "CAT-RAW",
    name: str = "Raw materials",
    costing: CostingMethod = CostingMethod.MOVING_AVERAGE,
    with_accounts: bool = False,
) -> ItemCategory:
    """Create an item category through the real service. ``with_accounts`` seeds a small COA and
    wires the category's inventory/COGS/price-difference accounts to real finance GL accounts so
    the D-029 cross-module validation has something to find."""
    inventory_account_id: uuid.UUID | None = None
    cogs_account_id: uuid.UUID | None = None
    price_difference_account_id: uuid.UUID | None = None
    if with_accounts:
        with tenant_context(tenant_id):
            inventory_account = await finance_service.create_account(
                session,
                tenant_id,
                AccountCreate(code="1300", name="Inventory", account_type=AccountType.ASSET),
            )
            cogs_account = await finance_service.create_account(
                session,
                tenant_id,
                AccountCreate(code="5000", name="COGS", account_type=AccountType.EXPENSE),
            )
            price_diff = await finance_service.create_account(
                session,
                tenant_id,
                AccountCreate(
                    code="5900", name="Price difference", account_type=AccountType.EXPENSE
                ),
            )
            await session.commit()
        inventory_account_id = inventory_account.id
        cogs_account_id = cogs_account.id
        price_difference_account_id = price_diff.id
    with tenant_context(tenant_id):
        category = await service.create_category(
            session,
            tenant_id,
            ItemCategoryCreate(
                code=code,
                name=name,
                default_costing_method=costing,
                inventory_account_id=inventory_account_id,
                cogs_account_id=cogs_account_id,
                price_difference_account_id=price_difference_account_id,
            ),
        )
        await session.commit()
    return category


async def build_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_code: str,
    category_id: uuid.UUID,
    base_uom_id: uuid.UUID,
    **kwargs: object,
) -> Item:
    """Create an item through the real service (D-025). ``kwargs`` overrides any ItemCreate field
    (item_type, tracking_mode, costing_method, name, ...)."""
    payload_fields: dict[str, object] = {
        "item_code": item_code,
        "name": kwargs.pop("name", f"Item {item_code}"),
        "item_type": kwargs.pop("item_type", "STOCKED"),
        "category_id": category_id,
        "base_uom_id": base_uom_id,
    }
    payload_fields.update(kwargs)
    with tenant_context(tenant_id):
        item = await service.create_item(
            session, tenant_id, ItemCreate(**payload_fields)  # type: ignore[arg-type]
        )
        await session.commit()
    return item


async def add_conversion(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    alt_uom_id: uuid.UUID,
    factor_to_base: Decimal,
) -> None:
    """Add an alternate-UoM conversion to an item through the real service (D-025)."""
    with tenant_context(tenant_id):
        await service.create_conversion(
            session,
            tenant_id,
            item_id,
            UomConversionCreate(alt_uom_id=alt_uom_id, factor_to_base=factor_to_base),
        )
        await session.commit()


@dataclass(frozen=True)
class InventorySetup:
    """A tenant ready to create items: EA/BOX UoM ids and a MOVING_AVERAGE category id (no GL
    accounts wired — tests that need them build a category with ``with_accounts=True``). Plain ids
    so a rollback (expiring loaded ORM objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    category_id: uuid.UUID
    ea_uom_id: uuid.UUID
    box_uom_id: uuid.UUID


async def build_inventory_setup(
    session: AsyncSession, tenant_id: uuid.UUID
) -> InventorySetup:
    """EA + BOX units and a MOVING_AVERAGE raw-materials category (PLAN 5.1)."""
    ea = await seed_uom(session, tenant_id, "EA", "Each")
    box = await seed_uom(session, tenant_id, "BOX", "Box")
    category = await build_item_category(session, tenant_id)
    return InventorySetup(
        tenant_id=tenant_id,
        category_id=category.id,
        ea_uom_id=ea.id,
        box_uom_id=box.id,
    )


@dataclass(frozen=True)
class InventoryPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_inventory_principal(
    session: AsyncSession,
    slug: str = "inv-acme",
    email: str = "ops@inv-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _INVENTORY_KEYS,
) -> InventoryPrincipal:
    """Provision a tenant + user and grant a role with the inventory permission keys through the
    real services (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Inventory", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return InventoryPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )

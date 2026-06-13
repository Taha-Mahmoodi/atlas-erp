"""Sales test data builders behind tests/modules/sales/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping and
audit fire exactly as in production. conftest.py keeps only the thin pytest fixtures.

``build_sales_setup`` wires a tenant ready to create customers + price lists: it seeds a currency
(USD) in finance — the cross-module read ``default_currency_code`` / a price list's
``currency_code``
validate against — and an inventory item (so price-list-item validation has a real item to point
at).
``create_sales_principal`` mirrors the finance/inventory/procurement principal pattern with sales.*
keys (and supports a narrowed ``keys`` grant for the 403 RBAC tests), plus the finance + inventory
setup keys the cross-module-aware API tests need.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service as finance_service
from app.modules.sales import service
from app.modules.sales.models import Customer, CustomerGroup, PriceList, PriceListItem
from app.modules.sales.schemas import (
    CustomerCreate,
    CustomerGroupCreate,
    PriceListCreate,
    PriceListItemCreate,
)

# EVERY registered sales.* key (importing sales.constants registers them), so a new sales permission
# is auto-granted to the full-rights principal (self-extending).
_SALES_KEYS = tuple(sorted(key for key in catalog_keys() if key.startswith("sales.")))


async def seed_currency(
    session: AsyncSession, tenant_id: uuid.UUID, code: str = "USD", name: str = "US Dollar"
) -> str:
    """Create a currency in finance through the real service (D-025) so a customer's
    ``default_currency_code`` / a price list's ``currency_code`` have something to validate against
    (D-029). Returns the code."""
    with tenant_context(tenant_id):
        await finance_service.create_currency(session, tenant_id, code=code, name=name)
        await session.commit()
    return code


async def build_customer_group(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "GRP-1",
    name: str = "Wholesale",
) -> CustomerGroup:
    """Create a customer group through the real service (D-025)."""
    with tenant_context(tenant_id):
        group = await service.create_customer_group(
            session, tenant_id, CustomerGroupCreate(code=code, name=name)
        )
        await session.commit()
    return group


async def build_customer(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    customer_code: str = "C-001",
    name: str = "Acme Retail",
    default_currency_code: str = "USD",
    **kwargs: object,
) -> Customer:
    """Create a customer through the real service (D-025). ``kwargs`` overrides any CustomerCreate
    field (status, customer_group_id, credit_limit, payment_terms_days, ...)."""
    payload_fields: dict[str, object] = {
        "customer_code": customer_code,
        "name": name,
        "default_currency_code": default_currency_code,
    }
    payload_fields.update(kwargs)
    with tenant_context(tenant_id):
        customer = await service.create_customer(
            session, tenant_id, CustomerCreate(**payload_fields)  # type: ignore[arg-type]
        )
        await session.commit()
    return customer


async def build_price_list(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "PL-1",
    name: str = "Standard",
    currency_code: str = "USD",
    valid_from: date | None = None,
    **kwargs: object,
) -> PriceList:
    """Create a price list through the real service (D-025). ``valid_from`` defaults to a fixed
    early
    date so date-window tests are deterministic. ``kwargs`` overrides any PriceListCreate field
    (customer_group_id, valid_to, status, priority, ...)."""
    payload_fields: dict[str, object] = {
        "code": code,
        "name": name,
        "currency_code": currency_code,
        "valid_from": valid_from if valid_from is not None else date(2026, 1, 1),
    }
    payload_fields.update(kwargs)
    with tenant_context(tenant_id):
        price_list = await service.create_price_list(
            session, tenant_id, PriceListCreate(**payload_fields)  # type: ignore[arg-type]
        )
        await session.commit()
    return price_list


async def build_price_list_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    price_list_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    unit_price: str = "10",
    min_quantity: str = "0",
) -> PriceListItem:
    """Add a base price for an item to a price list through the real service (D-025)."""
    with tenant_context(tenant_id):
        item = await service.add_price_list_item(
            session,
            tenant_id,
            price_list_id,
            PriceListItemCreate(
                item_id=item_id,
                unit_price=Decimal(unit_price),
                min_quantity=Decimal(min_quantity),
            ),
        )
        await session.commit()
    return item


@dataclass(frozen=True)
class SalesSetup:
    """A tenant ready to create customers + price lists: the USD currency code (seeded in finance,
    so
    a customer's default_currency_code / a price list's currency_code validate) and a real inventory
    item id (so price-list-item validation has something to point at). Plain ids so a rollback
    (expiring loaded ORM objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    currency_code: str
    item_id: uuid.UUID


async def build_sales_setup(session: AsyncSession, tenant_id: uuid.UUID) -> SalesSetup:
    """Seed a USD currency (finance) and an inventory item (inventory), so customer creation and
    price-list-item validation both have real cross-module data to validate against (D-029)."""
    # Imported lazily so the sales factories do not hard-depend on the inventory test package at
    # import time (it is only needed when a real item is required).
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
    return SalesSetup(tenant_id=tenant_id, currency_code=code, item_id=item.id)


# --- Principals ---------------------------------------------------------------

# Finance + inventory setup keys the API tests need to scaffold cross-module data through the wire
# (a customer's / price list's currency lives in finance; a price-list item points at a real
# inventory item).
_FINANCE_SETUP_KEYS = ("finance.fx.manage",)
_INVENTORY_SETUP_KEYS = (
    "inventory.uom.manage",
    "inventory.category.manage",
    "inventory.item.manage",
)
_FULL_KEYS = (*_SALES_KEYS, *_FINANCE_SETUP_KEYS, *_INVENTORY_SETUP_KEYS)


@dataclass(frozen=True)
class SalesPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_sales_principal(
    session: AsyncSession,
    slug: str = "sales-acme",
    email: str = "rep@sales-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _FULL_KEYS,
) -> SalesPrincipal:
    """Provision a tenant + user and grant a role with the sales permission keys (plus the
    finance/inventory setup keys for the cross-module API scaffolding) through the real services
    (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Sales", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return SalesPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )

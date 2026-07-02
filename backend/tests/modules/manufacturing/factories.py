"""Manufacturing test data builders behind tests/modules/manufacturing/conftest.py (STRUCTURE
§6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping and
audit fire exactly as in production. conftest.py keeps only the thin pytest fixtures.

``build_manufacturing_setup`` wires a tenant ready to author masters: it REUSES the inventory item
fixtures (an EA UoM + a category + a PARENT item the BOM/routing produce and a COMPONENT item a BOM
consumes), so the D-029 opaque-id validation has real inventory ids to find. The
``create_mfg_principal`` builder mirrors the inventory principal pattern with manufacturing.* keys
(and supports a narrowed ``keys`` grant for the 403 RBAC tests).
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service as finance_service
from app.modules.finance.controlling_schemas import CostCenterCreate
from app.modules.manufacturing import service
from app.modules.manufacturing.models import (
    Bom,
    BomComponent,
    Routing,
    RoutingOperation,
    WorkCenter,
)
from app.modules.manufacturing.schemas import (
    BomComponentCreate,
    BomCreate,
    RoutingCreate,
    RoutingOperationCreate,
    WorkCenterCreate,
)
from tests.modules.inventory.factories import (
    build_inventory_setup,
    build_item,
)

# EVERY registered manufacturing.* key (importing manufacturing.constants registers them), so a new
# permission is auto-granted to the full-rights principal (self-extending). Plus the finance +
# inventory setup keys the API tests need to scaffold a cost centre / items over the wire.
_SETUP_KEYS = (
    "finance.costcenter.manage",
    "inventory.item.manage",
    "inventory.category.manage",
    "inventory.uom.manage",
)
_MFG_KEYS = (
    *sorted(key for key in catalog_keys() if key.startswith("manufacturing.")),
    *_SETUP_KEYS,
)


async def build_work_center(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "WC-100",
    name: str = "Assembly line",
    cost_center_id: uuid.UUID | None = None,
    capacity_hours_per_day: Decimal = Decimal(8),
    efficiency_percent: Decimal = Decimal(100),
) -> WorkCenter:
    """Create a work centre through the real service (D-025)."""
    with tenant_context(tenant_id):
        work_center = await service.create_work_center(
            session,
            tenant_id,
            WorkCenterCreate(
                code=code,
                name=name,
                cost_center_id=cost_center_id,
                capacity_hours_per_day=capacity_hours_per_day,
                efficiency_percent=efficiency_percent,
            ),
        )
        await session.commit()
    return work_center


async def build_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, *, code: str = "CC-100"
) -> uuid.UUID:
    """Create a finance cost centre through the real finance service (D-025) — the opaque id a work
    centre's ``cost_center_id`` validates against (D-029). Returns its id."""
    with tenant_context(tenant_id):
        center = await finance_service.create_cost_center(
            session, tenant_id, CostCenterCreate(code=code, name="Plant cost centre")
        )
        await session.commit()
        return center.id


async def build_bom(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    uom_id: uuid.UUID,
    version: str = "1",
    name: str = "Default BOM",
    base_quantity: Decimal = Decimal(1),
) -> Bom:
    """Create a BOM header (born DRAFT) through the real service (D-025)."""
    with tenant_context(tenant_id):
        bom = await service.create_bom(
            session,
            tenant_id,
            BomCreate(
                item_id=item_id,
                uom_id=uom_id,
                version=version,
                name=name,
                base_quantity=base_quantity,
            ),
        )
        await session.commit()
    return bom


async def build_bom_component(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    bom_id: uuid.UUID,
    *,
    component_item_id: uuid.UUID,
    uom_id: uuid.UUID,
    quantity_per: Decimal = Decimal(2),
    scrap_percent: Decimal = Decimal(0),
    line_number: int | None = None,
) -> BomComponent:
    """Add a component to a DRAFT BOM through the real service (D-025)."""
    with tenant_context(tenant_id):
        component = await service.add_component(
            session,
            tenant_id,
            bom_id,
            BomComponentCreate(
                component_item_id=component_item_id,
                uom_id=uom_id,
                quantity_per=quantity_per,
                scrap_percent=scrap_percent,
                line_number=line_number,
            ),
        )
        await session.commit()
    return component


async def build_routing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    version: str = "1",
    name: str = "Default routing",
) -> Routing:
    """Create a routing header (born DRAFT) through the real service (D-025)."""
    with tenant_context(tenant_id):
        routing = await service.create_routing(
            session,
            tenant_id,
            RoutingCreate(item_id=item_id, version=version, name=name),
        )
        await session.commit()
    return routing


async def build_routing_operation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    routing_id: uuid.UUID,
    *,
    work_center_id: uuid.UUID,
    setup_time_minutes: Decimal = Decimal(30),
    run_time_minutes_per_unit: Decimal = Decimal(5),
    operation_number: int | None = None,
    description: str | None = "Operation",
) -> RoutingOperation:
    """Add an operation to a DRAFT routing through the real service (D-025)."""
    with tenant_context(tenant_id):
        operation = await service.add_operation(
            session,
            tenant_id,
            routing_id,
            RoutingOperationCreate(
                work_center_id=work_center_id,
                setup_time_minutes=setup_time_minutes,
                run_time_minutes_per_unit=run_time_minutes_per_unit,
                operation_number=operation_number,
                description=description,
            ),
        )
        await session.commit()
    return operation


@dataclass(frozen=True)
class ManufacturingSetup:
    """A tenant ready to author manufacturing masters: an EA UoM id, a category id, and two
    inventory items — a PARENT item (the finished good a BOM/routing produce) and a COMPONENT item
    (a raw material a BOM consumes). Plain ids so a rollback (expiring loaded ORM objects) cannot
    break a follow-up payload."""

    tenant_id: uuid.UUID
    ea_uom_id: uuid.UUID
    category_id: uuid.UUID
    parent_item_id: uuid.UUID
    component_item_id: uuid.UUID


async def build_manufacturing_setup(
    session: AsyncSession, tenant_id: uuid.UUID
) -> ManufacturingSetup:
    """Reuse the inventory setup (EA/BOX UoMs + a category), then create a PARENT and a COMPONENT
    item so BOM/routing authoring has real opaque inventory ids (D-029) to reference."""
    inv = await build_inventory_setup(session, tenant_id)
    parent = await build_item(
        session,
        tenant_id,
        item_code="FG-1",
        category_id=inv.category_id,
        base_uom_id=inv.ea_uom_id,
        name="Finished good",
    )
    component = await build_item(
        session,
        tenant_id,
        item_code="RM-1",
        category_id=inv.category_id,
        base_uom_id=inv.ea_uom_id,
        name="Raw material",
    )
    return ManufacturingSetup(
        tenant_id=tenant_id,
        ea_uom_id=inv.ea_uom_id,
        category_id=inv.category_id,
        parent_item_id=parent.id,
        component_item_id=component.id,
    )


@dataclass(frozen=True)
class ManufacturingPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_mfg_principal(
    session: AsyncSession,
    slug: str = "mfg-acme",
    email: str = "ops@mfg-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _MFG_KEYS,
) -> ManufacturingPrincipal:
    """Provision a tenant + user and grant a role with the manufacturing permission keys through the
    real services (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Manufacturing", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return ManufacturingPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )

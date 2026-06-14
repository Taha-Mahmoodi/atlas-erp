"""Maintenance test data builders behind tests/modules/maintenance/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping,
numbering, docflow and audit fire exactly as in production. conftest.py keeps only the thin pytest
fixtures.

``build_maintenance_setup`` wires a tenant ready for the PM flow: a piece of ACTIVE equipment (the
target of corrective orders + plans) plus a finance cost centre (the opaque id an equipment's
``cost_center_id`` validates against, D-029). ``create_maintenance_principal`` mirrors the
manufacturing principal pattern with maintenance.* keys (and the finance setup key the API
cost-centre tests need), supporting a narrowed ``keys`` grant for the 403 RBAC tests.
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
from app.modules.finance.controlling_schemas import CostCenterCreate
from app.modules.maintenance import service
from app.modules.maintenance.constants import IntervalUnit
from app.modules.maintenance.models import Equipment, MaintenanceOrder, MaintenancePlan
from app.modules.maintenance.schemas import (
    EquipmentCreate,
    MaintenanceOrderCreate,
    MaintenancePlanCreate,
)

# EVERY registered maintenance.* key (importing maintenance.constants registers them), so a new
# permission is auto-granted to the full-rights principal (self-extending). Plus the finance
# cost-centre setup key the API tests need to scaffold a cost centre over the wire.
_SETUP_KEYS = ("finance.costcenter.manage",)
_MAINTENANCE_KEYS = (
    *sorted(key for key in catalog_keys() if key.startswith("maintenance.")),
    *_SETUP_KEYS,
)


async def build_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, *, code: str = "CC-PM"
) -> uuid.UUID:
    """Create a finance cost centre through the real finance service (D-025) — the opaque id an
    equipment's ``cost_center_id`` validates against (D-029). Returns its id."""
    with tenant_context(tenant_id):
        center = await finance_service.create_cost_center(
            session, tenant_id, CostCenterCreate(code=code, name="Plant cost centre")
        )
        await session.commit()
        return center.id


async def build_equipment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "EQ-100",
    name: str = "Compressor",
    cost_center_id: uuid.UUID | None = None,
    status=None,
) -> Equipment:
    """Create a piece of equipment through the real service (D-025)."""
    payload = EquipmentCreate(
        code=code,
        name=name,
        cost_center_id=cost_center_id,
        location="Plant A",
        **({"status": status} if status is not None else {}),
    )
    with tenant_context(tenant_id):
        equipment = await service.create_equipment(session, tenant_id, payload)
        await session.commit()
    return equipment


async def build_corrective_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    equipment_id: uuid.UUID,
    description: str = "Replace bearing",
    scheduled_date: date | None = None,
) -> MaintenanceOrder:
    """Create a CORRECTIVE maintenance order through the real service (D-025)."""
    with tenant_context(tenant_id):
        order = await service.create_corrective(
            session,
            tenant_id,
            MaintenanceOrderCreate(
                equipment_id=equipment_id,
                description=description,
                scheduled_date=scheduled_date,
            ),
        )
        await session.commit()
    return order


async def build_plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    equipment_id: uuid.UUID,
    code: str = "MP-100",
    interval_value: int = 1,
    interval_unit: IntervalUnit = IntervalUnit.MONTHS,
    task_description: str = "Routine service",
    start_date: date | None = None,
    estimated_cost: Decimal | None = None,
) -> MaintenancePlan:
    """Create an interval-based preventive plan through the real service (D-025)."""
    with tenant_context(tenant_id):
        plan = await service.create_plan(
            session,
            tenant_id,
            MaintenancePlanCreate(
                code=code,
                name="Preventive plan",
                equipment_id=equipment_id,
                interval_value=interval_value,
                interval_unit=interval_unit,
                task_description=task_description,
                start_date=start_date,
                estimated_cost=estimated_cost,
            ),
        )
        await session.commit()
    return plan


@dataclass(frozen=True)
class MaintenanceSetup:
    """A tenant ready for the PM flow: a finance cost-centre id and a piece of ACTIVE equipment
    (carrying that cost centre). Plain ids so a rollback (expiring loaded ORM objects) cannot break
    a follow-up payload."""

    tenant_id: uuid.UUID
    cost_center_id: uuid.UUID
    equipment_id: uuid.UUID
    equipment_code: str


async def build_maintenance_setup(
    session: AsyncSession, tenant_id: uuid.UUID
) -> MaintenanceSetup:
    """A cost centre + a piece of ACTIVE equipment in the tenant, ready to raise corrective orders
    and author plans."""
    cost_center_id = await build_cost_center(session, tenant_id)
    equipment = await build_equipment(
        session, tenant_id, cost_center_id=cost_center_id
    )
    return MaintenanceSetup(
        tenant_id=tenant_id,
        cost_center_id=cost_center_id,
        equipment_id=equipment.id,
        equipment_code=equipment.code,
    )


# --- Principals ---------------------------------------------------------------


@dataclass(frozen=True)
class MaintenancePrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_maintenance_principal(
    session: AsyncSession,
    slug: str = "pm-acme",
    email: str = "ops@pm-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _MAINTENANCE_KEYS,
) -> MaintenancePrincipal:
    """Provision a tenant + user and grant a role with the maintenance permission keys through the
    real services (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Maintenance", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return MaintenancePrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )

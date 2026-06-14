"""HR test data builders behind tests/modules/hr/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping and
audit fire exactly as in production. conftest.py keeps only the thin pytest fixtures.

``build_hr_setup`` wires a tenant ready for the HCM flow: a finance cost centre (the opaque id a
department's ``cost_center_id`` validates against, D-029) and one root department.
``create_hr_principal`` mirrors the maintenance principal pattern with hr.* keys, supporting a
narrowed ``keys`` grant for the masking / RBAC tests (e.g. a manager WITHOUT
``hr.employee.read_compensation``).
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
from app.modules.hr import service
from app.modules.hr.constants import EmploymentStatus, EmploymentType
from app.modules.hr.models import Department, Employee, Position
from app.modules.hr.schemas import (
    DepartmentCreate,
    EmployeeCreate,
    PositionCreate,
)

# EVERY registered hr.* key (importing hr.constants registers them), so a new permission is
# auto-granted to the full-rights principal (self-extending). Plus the finance cost-centre setup key
# the API tests need to scaffold a cost centre over the wire.
_SETUP_KEYS = ("finance.costcenter.manage",)
_HR_KEYS = (
    *sorted(key for key in catalog_keys() if key.startswith("hr.")),
    *_SETUP_KEYS,
)


async def build_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, *, code: str = "CC-HR"
) -> uuid.UUID:
    """Create a finance cost centre through the real finance service (D-025) — the opaque id a
    department's ``cost_center_id`` validates against (D-029). Returns its id."""
    with tenant_context(tenant_id):
        center = await finance_service.create_cost_center(
            session, tenant_id, CostCenterCreate(code=code, name="HR cost centre")
        )
        await session.commit()
        return center.id


async def build_department(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "DEP-ENG",
    name: str = "Engineering",
    parent_id: uuid.UUID | None = None,
    cost_center_id: uuid.UUID | None = None,
    manager_employee_id: uuid.UUID | None = None,
) -> Department:
    """Create a department through the real service (D-025)."""
    with tenant_context(tenant_id):
        department = await service.create_department(
            session,
            tenant_id,
            DepartmentCreate(
                code=code,
                name=name,
                parent_id=parent_id,
                cost_center_id=cost_center_id,
                manager_employee_id=manager_employee_id,
            ),
        )
        await session.commit()
    return department


async def build_position(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "POS-ENG",
    title: str = "Engineer",
    department_id: uuid.UUID | None = None,
) -> Position:
    """Create a position through the real service (D-025)."""
    with tenant_context(tenant_id):
        position = await service.create_position(
            session,
            tenant_id,
            PositionCreate(code=code, title=title, department_id=department_id),
        )
        await session.commit()
    return position


async def build_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    employee_code: str = "EMP-100",
    first_name: str = "Ada",
    last_name: str = "Lovelace",
    department_id: uuid.UUID | None = None,
    position_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    status: EmploymentStatus = EmploymentStatus.ACTIVE,
    employment_type: EmploymentType = EmploymentType.FULL_TIME,
    base_salary: Decimal | None = Decimal("120000"),
    currency_code: str | None = "USD",
    national_id: str | None = "NID-123",
    bank_account: str | None = "BANK-456",
    date_of_birth: date | None = date(1990, 1, 1),
) -> Employee:
    """Create an employee through the real service (D-025). Defaults seed the masked
    compensation/PII so masking tests have real values to redact."""
    with tenant_context(tenant_id):
        employee = await service.create_employee(
            session,
            tenant_id,
            EmployeeCreate(
                employee_code=employee_code,
                first_name=first_name,
                last_name=last_name,
                email=f"{employee_code.lower()}@acme.test",
                department_id=department_id,
                position_id=position_id,
                manager_id=manager_id,
                user_id=user_id,
                status=status,
                employment_type=employment_type,
                hire_date=date(2020, 1, 1),
                base_salary=base_salary,
                currency_code=currency_code,
                national_id=national_id,
                bank_account=bank_account,
                date_of_birth=date_of_birth,
            ),
        )
        await session.commit()
    return employee


@dataclass(frozen=True)
class HrSetup:
    """A tenant ready for the HCM flow: a finance cost-centre id and one root department (carrying
    that cost centre). Plain ids so a rollback (expiring loaded ORM objects) cannot break a
    follow-up payload."""

    tenant_id: uuid.UUID
    cost_center_id: uuid.UUID
    department_id: uuid.UUID
    department_code: str


async def build_hr_setup(session: AsyncSession, tenant_id: uuid.UUID) -> HrSetup:
    """A cost centre + a root department in the tenant, ready to author positions and employees."""
    cost_center_id = await build_cost_center(session, tenant_id)
    department = await build_department(session, tenant_id, cost_center_id=cost_center_id)
    return HrSetup(
        tenant_id=tenant_id,
        cost_center_id=cost_center_id,
        department_id=department.id,
        department_code=department.code,
    )


# --- Principals ---------------------------------------------------------------


@dataclass(frozen=True)
class HrPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_hr_principal(
    session: AsyncSession,
    slug: str = "hr-acme",
    email: str = "people@hr-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _HR_KEYS,
) -> HrPrincipal:
    """Provision a tenant + user and grant a role with the hr permission keys through the real
    services (D-025); ``keys`` narrows the grant for the masking / RBAC tests (e.g. a manager
    without ``hr.employee.read_compensation``)."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "HR", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return HrPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )

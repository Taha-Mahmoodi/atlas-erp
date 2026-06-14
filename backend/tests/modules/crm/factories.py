"""CRM test data builders behind tests/modules/crm/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping,
the
gapless numbering, the opportunity's core_documents registration and audit fire exactly as in
production. conftest.py keeps only the thin pytest fixtures.

``build_crm_setup`` wires a tenant ready for the CRM flow: a USD currency (finance — a
lead/opportunity
currency validates against it), a real inventory item + its base UoM (an opportunity line references
the
item, and convert resolves the base UoM for the quote line), an existing sales customer (the opaque
id
an opportunity's ``customer_id`` validates against + the convert-against-existing-customer path),
and an
hr employee (the opaque id an owner_employee_id validates against). ``create_crm_principal`` mirrors
the
projects principal pattern with crm.* keys, supporting a narrowed ``keys`` grant for the 403 RBAC
tests.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.crm import service
from app.modules.crm.models import Activity, Lead, Opportunity
from app.modules.crm.schemas import (
    ActivityCreate,
    LeadCreate,
    OpportunityCreate,
    OpportunityLineCreate,
)

# EVERY registered crm.* key (importing crm.constants registers them), so a new permission is
# auto-granted to the full-rights principal (self-extending). The setup data (currency, item,
# customer, employee) is scaffolded through the SERVICE layer under tenant_context (D-025), which is
# not RBAC-gated, so no finance/sales/inventory/hr keys are needed on the principal — the API tests
# drive ONLY crm endpoints over the wire.
_CRM_KEYS = tuple(sorted(key for key in catalog_keys() if key.startswith("crm.")))


@dataclass(frozen=True)
class CrmSetup:
    """A tenant ready for the CRM flow: the USD currency code, a real inventory item + its base UoM
    (for opportunity lines + the convert quote line), an existing sales customer id (for the
    convert-against-existing path + opportunity.customer_id validation), and an hr employee id (for
    owner validation). Plain ids so a rollback (expiring loaded ORM objects) cannot break a
    follow-up
    payload."""

    tenant_id: uuid.UUID
    currency_code: str
    item_id: uuid.UUID
    uom_id: uuid.UUID
    customer_id: uuid.UUID
    employee_id: uuid.UUID


async def build_crm_setup(session: AsyncSession, tenant_id: uuid.UUID) -> CrmSetup:
    """Seed the cross-module data CRM validates against (D-029): a USD currency + an inventory item
    (with a base UoM) via the sales setup, an existing customer, and an hr employee — all through
    the
    real services under the tenant context (D-025)."""
    from tests.modules.hr.factories import build_employee
    from tests.modules.sales.factories import build_customer, build_sales_setup

    sales = await build_sales_setup(session, tenant_id)
    customer = await build_customer(
        session, tenant_id, customer_code="C-CRM", name="Existing customer"
    )
    employee = await build_employee(session, tenant_id, employee_code="EMP-CRM")
    return CrmSetup(
        tenant_id=tenant_id,
        currency_code=sales.currency_code,
        item_id=sales.item_id,
        uom_id=sales.uom_id,
        customer_id=customer.id,
        employee_id=employee.id,
    )


async def build_lead(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    company_name: str = "Prospect Co",
    estimated_value: Decimal | None = Decimal("5000"),
    currency_code: str | None = "USD",
    owner_employee_id: uuid.UUID | None = None,
    **kwargs: object,
) -> Lead:
    """Create a lead through the real service (D-025). ``kwargs`` overrides any LeadCreate field."""
    fields: dict[str, object] = {
        "company_name": company_name,
        "estimated_value": estimated_value,
        "currency_code": currency_code,
        "owner_employee_id": owner_employee_id,
    }
    fields.update(kwargs)
    with tenant_context(tenant_id):
        lead = await service.create_lead(session, tenant_id, LeadCreate(**fields))  # type: ignore[arg-type]
        await session.commit()
    return lead


async def build_opportunity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name: str = "Deal A",
    company_name: str = "Prospect Co",
    currency_code: str = "USD",
    customer_id: uuid.UUID | None = None,
    estimated_value: Decimal = Decimal("5000"),
    lines: list[OpportunityLineCreate] | None = None,
    **kwargs: object,
) -> Opportunity:
    """Create an opportunity through the real service (D-025). ``lines`` (optional) are the expected
    products; ``kwargs`` overrides any OpportunityCreate field."""
    fields: dict[str, object] = {
        "name": name,
        "company_name": company_name,
        "currency_code": currency_code,
        "customer_id": customer_id,
        "estimated_value": estimated_value,
        "lines": lines or [],
    }
    fields.update(kwargs)
    with tenant_context(tenant_id):
        opportunity = await service.create_opportunity(
            session, tenant_id, OpportunityCreate(**fields)  # type: ignore[arg-type]
        )
        await session.commit()
    return opportunity


async def build_opportunity_with_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    setup: CrmSetup,
    *,
    name: str = "Deal A",
    customer_id: uuid.UUID | None = None,
    quantity: Decimal = Decimal("3"),
    unit_price: Decimal = Decimal("100"),
) -> Opportunity:
    """Create an opportunity carrying ONE expected-product line (the convertible shape) through the
    real service (D-025) — the convert tests need an opportunity with at least one line."""
    return await build_opportunity(
        session,
        tenant_id,
        name=name,
        currency_code=setup.currency_code,
        customer_id=customer_id,
        lines=[
            OpportunityLineCreate(
                item_id=setup.item_id, quantity=quantity, estimated_unit_price=unit_price
            )
        ],
    )


async def build_activity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    subject: str = "Intro call",
    activity_type=None,
    lead_id: uuid.UUID | None = None,
    opportunity_id: uuid.UUID | None = None,
    due_date: date | None = None,
    **kwargs: object,
) -> Activity:
    """Create an activity through the real service (D-025) against a lead OR an opportunity."""
    fields: dict[str, object] = {
        "subject": subject,
        "lead_id": lead_id,
        "opportunity_id": opportunity_id,
        "due_date": due_date,
    }
    if activity_type is not None:
        fields["activity_type"] = activity_type
    else:
        from app.modules.crm.constants import ActivityType

        fields["activity_type"] = ActivityType.CALL
    fields.update(kwargs)
    with tenant_context(tenant_id):
        activity = await service.create_activity(
            session, tenant_id, ActivityCreate(**fields)  # type: ignore[arg-type]
        )
        await session.commit()
    return activity


# --- Principals ---------------------------------------------------------------


@dataclass(frozen=True)
class CrmPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_crm_principal(
    session: AsyncSession,
    slug: str = "crm-acme",
    email: str = "sales@crm-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _CRM_KEYS,
) -> CrmPrincipal:
    """Provision a tenant + user and grant a role with the crm permission keys through the real
    services (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "CRM", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return CrmPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )

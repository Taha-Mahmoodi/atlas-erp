"""Projects test data builders behind tests/modules/projects/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping and
audit fire exactly as in production. conftest.py keeps only the thin pytest fixtures.

``build_projects_setup`` wires a tenant ready for the PS flow: a finance cost centre (the opaque id
a project's ``cost_center_id`` validates against, D-029), a sales customer (the opaque id a
project's ``customer_id`` validates against), a project, and a small chart of accounts + open year
(so journal lines can be POSTED tagged with a WBS id for the cost report). The WBS ids those
postings tag ARE the costing objects (D-056). ``create_projects_principal`` mirrors the maintenance
principal pattern with projects.* keys, supporting a narrowed ``keys`` grant for the 403 RBAC
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
from app.modules.finance import service as finance_service
from app.modules.finance.constants import AccountType, DocumentType
from app.modules.finance.controlling_schemas import CostCenterCreate
from app.modules.finance.schemas import (
    AccountCreate,
    FiscalYearCreate,
    JournalEntryCreate,
    JournalLineCreate,
)
from app.modules.hr import service as hr_service
from app.modules.projects import service
from app.modules.projects.models import Project, WbsElement
from app.modules.projects.schemas import ProjectCreate, WbsElementCreate
from app.modules.sales import service as sales_service
from app.modules.sales.schemas import CustomerCreate

# EVERY registered projects.* key (importing projects.constants registers them), so a new permission
# is auto-granted to the full-rights principal (self-extending). The setup data (cost centre,
# customer, accounts, journals, timesheets) is scaffolded through the SERVICE layer under
# tenant_context (D-025), which is not RBAC-gated, so no finance/sales/hr keys are needed on the
# principal — the API tests drive ONLY projects endpoints over the wire.
_PROJECTS_KEYS = tuple(sorted(key for key in catalog_keys() if key.startswith("projects.")))

# A minimal chart for posting WBS-tagged journal entries: an expense and a payable.
_COA: tuple[tuple[str, str, AccountType], ...] = (
    ("5000", "Project Expense", AccountType.EXPENSE),
    ("2000", "Accounts Payable", AccountType.LIABILITY),
)


async def build_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, *, code: str = "CC-PS"
) -> uuid.UUID:
    """Create a finance cost centre through the real finance service (D-025) — the opaque id a
    project's ``cost_center_id`` validates against (D-029). Returns its id."""
    with tenant_context(tenant_id):
        center = await finance_service.create_cost_center(
            session, tenant_id, CostCenterCreate(code=code, name="Project cost centre")
        )
        await session.commit()
        return center.id


async def build_customer(
    session: AsyncSession, tenant_id: uuid.UUID, *, code: str = "CUST-PS"
) -> uuid.UUID:
    """Create a sales customer through the real sales service (D-025) — the opaque id a project's
    ``customer_id`` validates against (D-029). Returns its id. Assumes the USD currency exists in
    finance (``build_finance_base`` seeds it), since create_customer validates the currency."""
    with tenant_context(tenant_id):
        customer = await sales_service.create_customer(
            session,
            tenant_id,
            CustomerCreate(
                customer_code=code, name="Project customer", default_currency_code="USD"
            ),
        )
        await session.commit()
        return customer.id


async def build_finance_base(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, uuid.UUID]:
    """A USD currency + a small COA + an open 2026 fiscal year (D-017): the precondition for posting
    WBS-tagged journal entries (and for the customer's currency validation). Returns account ids by
    code."""
    with tenant_context(tenant_id):
        await finance_service.create_currency(
            session, tenant_id, code="USD", name="US Dollar", is_functional=True
        )
        by_code: dict[str, uuid.UUID] = {}
        for code, name, account_type in _COA:
            account = await finance_service.create_account(
                session, tenant_id, AccountCreate(code=code, name=name, account_type=account_type)
            )
            by_code[code] = account.id
        await finance_service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await session.commit()
    return by_code


async def build_project(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "PRJ-100",
    name: str = "Atlas rollout",
    customer_id: uuid.UUID | None = None,
    cost_center_id: uuid.UUID | None = None,
    budget_amount: Decimal | None = None,
    status=None,
) -> Project:
    """Create a project through the real service (D-025)."""
    payload = ProjectCreate(
        code=code,
        name=name,
        customer_id=customer_id,
        cost_center_id=cost_center_id,
        budget_amount=budget_amount,
        **({"status": status} if status is not None else {}),
    )
    with tenant_context(tenant_id):
        project = await service.create_project(session, tenant_id, payload)
        await session.commit()
    return project


async def build_wbs_element(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    code: str = "WBS-1",
    name: str = "Phase 1",
    parent_id: uuid.UUID | None = None,
    budget_amount: Decimal | None = None,
) -> WbsElement:
    """Create a WBS element through the real service (D-025)."""
    with tenant_context(tenant_id):
        element = await service.create_wbs_element(
            session,
            tenant_id,
            project_id,
            WbsElementCreate(
                code=code, name=name, parent_id=parent_id, budget_amount=budget_amount
            ),
        )
        await session.commit()
    return element


async def post_wbs_journal(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    accounts: dict[str, uuid.UUID],
    wbs_element_id: uuid.UUID,
    amount: Decimal,
    *,
    posting_date: date = date(2026, 3, 15),
) -> uuid.UUID:
    """Post a balanced journal entry whose EXPENSE line is tagged with ``wbs_element_id`` as its
    project dimension — "posting a purchase to a WBS" (D-056). Dr 5000 expense (WBS-tagged) / Cr
    2000 payable. Returns the entry id. Goes through the real journal service (D-025), so the line
    carries the opaque project_id the cost report projects."""
    with tenant_context(tenant_id):
        entry = await finance_service.create_draft_entry(
            session,
            tenant_id,
            JournalEntryCreate(
                posting_date=posting_date,
                currency_code="USD",
                description="WBS cost",
                document_type=DocumentType.JOURNAL,
                lines=[
                    JournalLineCreate(
                        account_id=accounts["5000"],
                        transaction_debit_amount=amount,
                        project_id=wbs_element_id,
                    ),
                    JournalLineCreate(
                        account_id=accounts["2000"],
                        transaction_credit_amount=amount,
                    ),
                ],
            ),
        )
        await finance_service.post_entry(session, tenant_id, entry.id)
        await session.commit()
        return entry.id


async def post_approved_hours(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    wbs_element_id: uuid.UUID,
    hours: Decimal,
    *,
    employee_code: str = "EMP-PS",
    period_start: date = date(2026, 3, 1),
    entry_date: date = date(2026, 3, 10),
) -> uuid.UUID:
    """Create an employee + an APPROVED timesheet with one entry allocating ``hours`` to
    ``wbs_element_id`` as its project dimension — "posting time to a WBS" (D-056). Only APPROVED
    hours feed the cost report (D-054). Reuses the HR factory builders (the real service, D-025).
    Returns the employee id (so a second timesheet can reuse it). The approver is the employee."""
    from tests.modules.hr.factories import (
        build_employee,
        build_time_entry,
        build_timesheet,
    )

    employee = await build_employee(session, tenant_id, employee_code=employee_code)
    timesheet = await build_timesheet(
        session,
        tenant_id,
        employee_id=employee.id,
        period_start=period_start,
        period_end=date(period_start.year, period_start.month, 28),
    )
    await build_time_entry(
        session,
        tenant_id,
        timesheet_id=timesheet.id,
        entry_date=entry_date,
        hours=hours,
        project_id=wbs_element_id,
    )
    with tenant_context(tenant_id):
        await hr_service.submit_timesheet(session, tenant_id, timesheet.id)
        await hr_service.approve_timesheet(
            session, tenant_id, timesheet.id, approved_by=employee.id
        )
        await session.commit()
    return employee.id


@dataclass(frozen=True)
class ProjectsSetup:
    """A tenant ready for the PS flow: a finance cost centre, a sales customer, account ids by code,
    and a project (carrying the cost centre + customer). Plain ids so a rollback (expiring loaded
    ORM objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    cost_center_id: uuid.UUID
    customer_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    project_id: uuid.UUID
    project_code: str


async def build_projects_setup(session: AsyncSession, tenant_id: uuid.UUID) -> ProjectsSetup:
    """A cost centre + a customer + a COA/open year + a project in the tenant, ready to author WBS
    elements and post WBS-tagged journal entries for the cost report."""
    cost_center_id = await build_cost_center(session, tenant_id)
    accounts = await build_finance_base(session, tenant_id)
    customer_id = await build_customer(session, tenant_id)
    project = await build_project(
        session,
        tenant_id,
        customer_id=customer_id,
        cost_center_id=cost_center_id,
        budget_amount=Decimal("1000"),
    )
    return ProjectsSetup(
        tenant_id=tenant_id,
        cost_center_id=cost_center_id,
        customer_id=customer_id,
        accounts=accounts,
        project_id=project.id,
        project_code=project.code,
    )


# --- Principals ---------------------------------------------------------------


@dataclass(frozen=True)
class ProjectsPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_projects_principal(
    session: AsyncSession,
    slug: str = "ps-acme",
    email: str = "pm@ps-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _PROJECTS_KEYS,
) -> ProjectsPrincipal:
    """Provision a tenant + user and grant a role with the projects permission keys through the real
    services (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Projects", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return ProjectsPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )

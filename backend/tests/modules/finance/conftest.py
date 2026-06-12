"""Finance test fixtures (STRUCTURE §6): a tenant with a small chart of accounts and a
fiscal year, plus bearer-token clients holding finance permissions.

Factories go through the REAL service layer under the tenant context (D-025), so tenancy
stamping and audit fire exactly as in production. The finance-permissioned clients provision
a user, sync the catalog, and grant a role carrying the four finance keys — mirroring the
core admin_client pattern but with finance.* instead of admin.* permissions.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_ACCOUNT_MANAGE,
    FINANCE_ACCOUNT_READ,
    FINANCE_JOURNAL_POST,
    FINANCE_JOURNAL_READ,
    FINANCE_JOURNAL_REVERSE,
    FINANCE_PERIOD_MANAGE,
    FINANCE_PERIOD_READ,
    AccountType,
)
from app.modules.finance.models import Account, FiscalYear
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate

_FINANCE_KEYS = (
    FINANCE_ACCOUNT_READ,
    FINANCE_ACCOUNT_MANAGE,
    FINANCE_PERIOD_READ,
    FINANCE_PERIOD_MANAGE,
    FINANCE_JOURNAL_READ,
    FINANCE_JOURNAL_POST,
    FINANCE_JOURNAL_REVERSE,
)

# A minimal but type-complete chart of accounts: one account per statement-deriving type.
_SMALL_COA: tuple[tuple[str, str, AccountType], ...] = (
    ("1000", "Cash", AccountType.ASSET),
    ("2000", "Accounts Payable", AccountType.LIABILITY),
    ("3000", "Share Capital", AccountType.EQUITY),
    ("4000", "Sales Revenue", AccountType.REVENUE),
    ("5000", "Cost of Goods Sold", AccountType.EXPENSE),
)


async def seed_small_coa(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[Account]:
    """Create one account per account type through the real service (D-025)."""
    accounts: list[Account] = []
    with tenant_context(tenant_id):
        for code, name, account_type in _SMALL_COA:
            account = await service.create_account(
                session,
                tenant_id,
                AccountCreate(code=code, name=name, account_type=account_type),
            )
            accounts.append(account)
        await session.commit()
    return accounts


async def seed_fiscal_year(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str = "2026",
    start_date: date = date(2026, 1, 1),
) -> FiscalYear:
    """Create a 12-period fiscal year through the real service (D-025)."""
    with tenant_context(tenant_id):
        year = await service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code=code, name=f"FY{code}", start_date=start_date),
        )
        await session.commit()
    return year


@pytest.fixture
async def coa(db_session: AsyncSession, tenant_a: uuid.UUID) -> list[Account]:
    """A small chart of accounts (one account per type) in tenant A."""
    return await seed_small_coa(db_session, tenant_a)


@pytest.fixture
async def fiscal_year(db_session: AsyncSession, tenant_a: uuid.UUID) -> FiscalYear:
    """A 12-period fiscal year (2026) in tenant A."""
    return await seed_fiscal_year(db_session, tenant_a)


@dataclass(frozen=True)
class JournalSetup:
    """A tenant ready to post: account ids by code + the open 2026 fiscal year id.

    Plain ids (not ORM objects) so a test that triggers a rollback — which expires every loaded
    ORM object — can still build the next payload without an out-of-greenlet lazy refresh."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    fiscal_year_id: uuid.UUID


@pytest.fixture
async def journal_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> JournalSetup:
    """COA + open fiscal year in tenant A — the precondition for posting (D-017)."""
    accounts = await seed_small_coa(db_session, tenant_a)
    year = await seed_fiscal_year(db_session, tenant_a)
    return JournalSetup(
        tenant_id=tenant_a,
        accounts={account.code: account.id for account in accounts},
        fiscal_year_id=year.id,
    )


# --- Finance-permissioned HTTP clients ----------------------------------------


@dataclass(frozen=True)
class FinancePrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


@pytest.fixture
def finance_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[FinancePrincipal]"]:
    """Provision a tenant + user and grant a role with the four finance permission keys,
    through the real services (D-025). ``keys`` lets a test request a narrower grant (for the
    403 RBAC tests)."""

    async def _create(
        slug: str = "fin-acme",
        email: str = "cfo@fin-acme.test",
        password: str = "correct-horse-battery",
        keys: tuple[str, ...] = _FINANCE_KEYS,
    ) -> FinancePrincipal:
        tenant = await provision_tenant(db_session, slug=slug, name=slug.title())
        user = await provision_user(db_session, tenant.id, email=email, password=password)
        with system_context():
            await sync_permission_catalog(db_session)
        role = await create_role(db_session, tenant.id, "Finance", keys, is_system=True)
        await assign_role(db_session, tenant.id, user.id, role.id, user.token_version)
        await db_session.commit()
        return FinancePrincipal(
            tenant_id=tenant.id,
            tenant_slug=slug,
            user_id=user.id,
            email=email,
            password=password,
        )

    return _create


async def _login(client: AsyncClient, principal: FinancePrincipal) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
async def finance_client(
    client: AsyncClient,
    finance_user_factory: Callable[..., AsyncIterator[FinancePrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client whose principal holds all four finance permissions."""
    principal = await finance_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client

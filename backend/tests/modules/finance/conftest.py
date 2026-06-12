"""Finance test fixtures (STRUCTURE §6): a tenant with a small chart of accounts and a
fiscal year, plus bearer-token clients holding finance permissions.

The data builders live in tests/modules/finance/factories.py (issue #30, STRUCTURE §8.4);
this conftest keeps only the thin pytest fixtures wrapping them. Factories go through the
REAL service layer under the tenant context (D-025), so tenancy stamping and audit fire
exactly as in production. The finance-permissioned clients provision a user, sync the
catalog, and grant a role carrying the finance keys — mirroring the core admin_client
pattern but with finance.* instead of admin.* permissions.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.models import Account, FiscalYear
from tests.modules.finance.factories import (
    ApSetup,
    ArSetup,
    BankSetup,
    CoSetup,
    FinancePrincipal,
    FxSetup,
    JournalSetup,
    build_ap_setup,
    build_ar_setup,
    build_bank_setup,
    build_co_setup,
    build_fx_setup,
    build_journal_setup,
    create_finance_principal,
    seed_fiscal_year,
    seed_small_coa,
)
from tests.modules.finance.factories_assets import AssetSetup, build_asset_setup

__all__ = [
    "ApSetup",
    "ArSetup",
    "AssetSetup",
    "BankSetup",
    "CoSetup",
    "FinancePrincipal",
    "FxSetup",
    "JournalSetup",
]


@pytest.fixture
async def coa(db_session: AsyncSession, tenant_a: uuid.UUID) -> list[Account]:
    """A small chart of accounts (one account per type) in tenant A."""
    return await seed_small_coa(db_session, tenant_a)


@pytest.fixture
async def fiscal_year(db_session: AsyncSession, tenant_a: uuid.UUID) -> FiscalYear:
    """A 12-period fiscal year (2026) in tenant A."""
    return await seed_fiscal_year(db_session, tenant_a)


@pytest.fixture
async def journal_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> JournalSetup:
    """COA + open fiscal year in tenant A — the precondition for posting (D-017)."""
    return await build_journal_setup(db_session, tenant_a)


@pytest.fixture
async def ap_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> ApSetup:
    """COA + an input-tax receivable account + a 20% input tax code + open year (PLAN 4.5)."""
    return await build_ap_setup(db_session, tenant_a)


@pytest.fixture
async def ar_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> ArSetup:
    """COA + an AR control account + an output-tax payable account + a 20% output tax code + open
    year (PLAN 4.6)."""
    return await build_ar_setup(db_session, tenant_a)


@pytest.fixture
async def fx_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> FxSetup:
    """A tenant wired for multi-currency posting + revaluation (D-019)."""
    return await build_fx_setup(db_session, tenant_a)


@pytest.fixture
async def co_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> CoSetup:
    """COA + a cost-allocation clearing account wired as the ``cost_allocation`` posting default +
    open 2026 year (PLAN 4.7)."""
    return await build_co_setup(db_session, tenant_a)


@pytest.fixture
async def bank_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> BankSetup:
    """COA + a cash-equivalent bank account + the ``bank_unmatched_clearing`` suspense default +
    open 2026 year (PLAN 4.9)."""
    return await build_bank_setup(db_session, tenant_a)


@pytest.fixture
async def asset_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> AssetSetup:
    """COA + asset/accumulated/expense accounts + the ``asset_acquisition_clearing`` posting
    default + open 2026 year (PLAN 4.10)."""
    return await build_asset_setup(db_session, tenant_a)


# --- Finance-permissioned HTTP clients ----------------------------------------


@pytest.fixture
def finance_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[FinancePrincipal]"]:
    """Provision a tenant + user and grant a role with the finance permission keys,
    through the real services (D-025). ``keys`` lets a test request a narrower grant (for the
    403 RBAC tests)."""
    return partial(create_finance_principal, db_session)


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
    """A real bearer-token client whose principal holds all finance permissions."""
    principal = await finance_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client

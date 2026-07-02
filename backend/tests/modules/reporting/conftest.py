"""Reporting test fixtures (STRUCTURE §6): a tenant with every dashboard KPI non-zero (seeded across
finance / sales / procurement / inventory through the REAL services, D-025) + bearer-token clients
holding chosen reporting permission subsets for the role-based RBAC tests.

The data builders live in tests/modules/reporting/factories.py + factories_crossmod.py (STRUCTURE
§8.4); this conftest keeps only the thin pytest fixtures. The reporting-permissioned clients
provision a user, sync the catalog, and grant a role carrying an EXPLICIT key set — reporting is
role-based, so each test grants exactly the keys (the base dashboard key + a chosen subset of source
read keys) whose KPIs it wants to see.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import register_event_handlers
from app.modules.reporting.constants import KPI_PERMISSIONS, REPORTING_DASHBOARD_READ
from tests.modules.reporting.factories import ReportingPrincipal, create_reporting_principal
from tests.modules.reporting.factories_crossmod import ReportingSetup, build_reporting_setup

__all__ = ["ReportingPrincipal", "ReportingSetup"]

# The base dashboard key + EVERY source read key — the "sees all KPIs" grant for the headline tests.
ALL_REPORTING_KEYS: tuple[str, ...] = (
    REPORTING_DASHBOARD_READ,
    *sorted(set(KPI_PERMISSIONS.values())),
)


@pytest.fixture(autouse=True)
def _register_event_handlers(clear_event_subscriptions: Callable[[], None]) -> None:
    """Register the cross-module handlers for every reporting test. Reporting publishes / subscribes
    to NO cross-module event (a read aggregator, D-058), but the seeders post invoices / bills /
    deliveries that DO fire finance's AR/AP/COGS handlers, so this wires the same handlers the app
    registers (idempotent). Depends on ``clear_event_subscriptions`` so it runs AFTER the per-test
    reset."""
    register_event_handlers()


@pytest.fixture
async def reporting_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> ReportingSetup:
    """A tenant with every dashboard KPI non-zero, ready for the service-level KPI tests."""
    return await build_reporting_setup(db_session, tenant_a)


# --- Reporting-permissioned HTTP clients --------------------------------------


@pytest.fixture
def reporting_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[ReportingPrincipal]"]:
    """Provision a tenant + user and grant a role with an EXPLICIT reporting key set (D-025)."""
    return partial(create_reporting_principal, db_session)


async def _login(client: AsyncClient, principal: ReportingPrincipal) -> str:
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


@dataclass(frozen=True)
class ReportingApi:
    """A logged-in client holding ALL reporting keys plus a ReportingSetup seeded in THAT client's
    tenant — so the dashboard endpoint can be driven over the wire against a tenant with KPIs."""

    client: AsyncClient
    setup: ReportingSetup


@pytest.fixture
async def reporting_api(
    client: AsyncClient,
    db_session: AsyncSession,
    reporting_user_factory: Callable[..., AsyncIterator[ReportingPrincipal]],
) -> AsyncIterator[ReportingApi]:
    """A bearer-token client holding all reporting keys, with the all-KPIs setup seeded in that
    principal's tenant (PLAN 13.1)."""
    principal = await reporting_user_factory(keys=ALL_REPORTING_KEYS)
    setup = await build_reporting_setup(db_session, principal.tenant_id)
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield ReportingApi(client=client, setup=setup)

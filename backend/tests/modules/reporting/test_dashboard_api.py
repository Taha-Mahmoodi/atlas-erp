"""Reporting dashboard API behaviour (PLAN 13.1, D-058), SQLite.

Proves GET /api/v1/reporting/dashboard returns the permitted KPI bundle, requires the base
reporting.dashboard.read permission, gates each KPI by the source module's read key (role-based —
the permitted subset per role), isolates tenants, serializes money as strings, and runs a bounded
(non-N+1) set of aggregates for the whole bundle.
"""

from collections.abc import AsyncIterator, Callable
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import (
    FINANCE_AP_READ,
    FINANCE_AR_READ,
    FINANCE_STATEMENTS_READ,
)
from app.modules.procurement.constants import PROCUREMENT_PO_READ
from app.modules.reporting.constants import REPORTING_DASHBOARD_READ
from app.modules.sales.constants import SALES_ORDER_READ
from tests.modules.reporting.conftest import ReportingApi, ReportingPrincipal
from tests.modules.reporting.factories_crossmod import build_reporting_setup

pytestmark = pytest.mark.asyncio

_URL = "/api/v1/reporting/dashboard"


async def test_dashboard_returns_the_permitted_bundle(reporting_api: ReportingApi) -> None:
    """A full-rights principal gets every KPI card, money serialized as strings (build-spec)."""
    response = await reporting_api.client.get(_URL)
    assert response.status_code == 200, response.text
    body = response.json()
    for key in (
        "cash_position",
        "ar_aging",
        "ap_aging",
        "inventory_value",
        "open_sales_orders",
        "open_purchase_orders",
        "otd_percent",
        "wip_value",
    ):
        assert key in body, f"missing KPI {key}"
    # Money fields are STRINGS, not JSON numbers (build-spec §13.1) — compare as Decimal so the
    # micro-unit scale (e.g. "1500.000000") matches the seeded value regardless of trailing zeros.
    assert isinstance(body["cash_position"]["value"], str)
    assert Decimal(body["cash_position"]["value"]) == reporting_api.setup.cash_position
    assert isinstance(body["open_sales_orders"]["total"], str)
    assert body["otd_percent"]["percent"] == 100.0


async def test_dashboard_requires_the_base_permission(
    client: AsyncClient,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """A principal WITHOUT reporting.dashboard.read is 403 even if it holds source read keys."""
    principal = await reporting_user_factory(keys=(FINANCE_STATEMENTS_READ,))
    token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    response = await client.get(_URL)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "rbac.permission_denied"


async def test_finance_role_sees_only_finance_kpis(
    client: AsyncClient,
    db_session: AsyncSession,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """A finance role (base + statements/AR/AP) gets cash / AR / AP / WIP but NOT inventory / open
    orders / OTD — the role-based KPI subset over the wire (D-058)."""
    principal = await reporting_user_factory(
        keys=(REPORTING_DASHBOARD_READ, FINANCE_STATEMENTS_READ, FINANCE_AR_READ, FINANCE_AP_READ)
    )
    await build_reporting_setup(db_session, principal.tenant_id)
    token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    response = await client.get(_URL)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"cash_position", "ar_aging", "ap_aging", "wip_value"}


async def test_sales_role_sees_only_sales_kpis(
    client: AsyncClient,
    db_session: AsyncSession,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """A sales role (base + sales.order.read) gets open sales orders + OTD but no finance KPIs (the
    open-sales and OTD KPIs both gate on sales.order.read, D-058)."""
    principal = await reporting_user_factory(
        keys=(REPORTING_DASHBOARD_READ, SALES_ORDER_READ)
    )
    await build_reporting_setup(db_session, principal.tenant_id)
    token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    response = await client.get(_URL)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"open_sales_orders", "otd_percent"}


async def test_buyer_role_sees_only_open_purchase_orders(
    client: AsyncClient,
    db_session: AsyncSession,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """A buyer role (base + procurement.po.read) gets ONLY the open-purchase-orders KPI."""
    principal = await reporting_user_factory(
        keys=(REPORTING_DASHBOARD_READ, PROCUREMENT_PO_READ)
    )
    await build_reporting_setup(db_session, principal.tenant_id)
    token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    response = await client.get(_URL)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"open_purchase_orders"}


async def test_dashboard_is_tenant_isolated(
    reporting_api: ReportingApi,
    client: AsyncClient,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """A second tenant's principal (all keys, but an EMPTY tenant) sees zero KPIs — never tenant A's
    figures (D-007)."""
    from tests.modules.reporting.conftest import ALL_REPORTING_KEYS

    principal_b = await reporting_user_factory(
        slug="rep-beta", email="analyst@rep-beta.test", keys=ALL_REPORTING_KEYS
    )
    transport = client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        token = await _login(client_b, principal_b)
        client_b.headers["Authorization"] = f"Bearer {token}"
        response = await client_b.get(_URL)
    assert response.status_code == 200, response.text
    body = response.json()
    # Tenant B has a functional currency only when seeded; with no setup the money KPIs read zero
    # and open-order counts are zero — never tenant A's non-zero figures.
    assert body["open_sales_orders"]["count"] == 0
    assert body["open_purchase_orders"]["count"] == 0


async def test_dashboard_bundle_is_bounded(
    reporting_api: ReportingApi,
    query_counter: Callable[[], object],
) -> None:
    """The whole-bundle dashboard runs a BOUNDED, fixed set of aggregates — NOT N+1 (PERFORMANCE
    §6). The internal count exceeds the §4 ≤3-list budget by design (N aggregates for N KPIs), but
    the CLIENT makes ONE call; the budget here is a generous fixed ceiling that catches a regression
    into per-row queries."""
    warm = await reporting_api.client.get(_URL)
    assert warm.status_code == 200, warm.text
    with query_counter() as qc:
        response = await reporting_api.client.get(_URL)
    assert response.status_code == 200, response.text
    # 8 KPIs run ~12 statements (auth user + functional currency + the per-KPI aggregates, two for
    # inventory + the WIP posting-default lookup); 16 is a fixed ceiling, not a per-KPI multiple.
    assert qc.count <= 16, (
        f"dashboard ran {qc.count} queries (ceiling 16 for 8 KPIs):\n" + "\n".join(qc.statements)
    )


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

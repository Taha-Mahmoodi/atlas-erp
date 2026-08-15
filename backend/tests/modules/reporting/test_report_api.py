"""Report-builder API behaviour (PLAN 13.2, D-059), SQLite.

Proves the three report-builder endpoints over the wire: GET /reports/entities lists the whitelist
filtered to the caller's role; POST /reports/run returns the JSON grid; POST /reports/export streams
CSV (text/csv + attachment). RBAC: the base reporting.report.run key is required, AND each entity is
gated by its source read permission (a role without sales.order.read is 403 on a sales report).
Tenant isolation: a second tenant's report sees only its own rows.
"""

from collections.abc import AsyncIterator, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reporting.constants import REPORTING_REPORT_RUN
from app.modules.sales.constants import SALES_ORDER_READ
from tests.modules.reporting.conftest import ReportingPrincipal
from tests.modules.reporting.factories_reportbuilder import build_report_builder_setup

pytestmark = pytest.mark.asyncio

_ENTITIES_URL = "/api/v1/reporting/reports/entities"
_RUN_URL = "/api/v1/reporting/reports/run"
_EXPORT_URL = "/api/v1/reporting/reports/export"

# A role that can run reports AND read sales orders — the headline report-builder principal.
_REPORT_KEYS = (REPORTING_REPORT_RUN, SALES_ORDER_READ)


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


async def _authed(
    client: AsyncClient, principal: ReportingPrincipal
) -> AsyncClient:
    token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


async def test_entities_lists_only_permitted_entities(
    client: AsyncClient,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """The entities catalog returns ONLY entities the caller's role permits (a sales-read role sees
    sales.orders, never finance/hr entities) — role-based, D-059."""
    principal = await reporting_user_factory(keys=_REPORT_KEYS)
    await _authed(client, principal)
    response = await client.get(_ENTITIES_URL)
    assert response.status_code == 200, response.text
    keys = {e["key"] for e in response.json()["entities"]}
    assert keys == {"sales.orders"}
    # The picker carries each column's capability flags.
    sales = next(e for e in response.json()["entities"] if e["key"] == "sales.orders")
    by_name = {c["name"]: c for c in sales["columns"]}
    assert by_name["status"]["groupable"] is True
    assert by_name["total_amount"]["is_aggregatable"] is True


async def test_run_returns_json_grid(
    client: AsyncClient,
    db_session: AsyncSession,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """POST /reports/run returns the JSON grid for a whitelisted entity over the wire."""
    principal = await reporting_user_factory(keys=_REPORT_KEYS)
    setup = await build_report_builder_setup(db_session, principal.tenant_id)
    await _authed(client, principal)
    response = await client.post(
        _RUN_URL,
        json={"entity": "sales.orders", "columns": ["order_number", "status"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["columns"] == ["order_number", "status"]
    # #166: the display headers travel with the grid, so the client never has to invent them.
    assert body["column_labels"] == ["Order Number", "Status"]
    assert body["row_count"] == setup.confirmed_count + setup.draft_count
    assert body["truncated"] is False


async def test_run_grouped_aggregation(
    client: AsyncClient,
    db_session: AsyncSession,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """A grouped + aggregated report runs end to end and returns per-group rows."""
    principal = await reporting_user_factory(keys=_REPORT_KEYS)
    setup = await build_report_builder_setup(db_session, principal.tenant_id)
    await _authed(client, principal)
    response = await client.post(
        _RUN_URL,
        json={
            "entity": "sales.orders",
            "group_by": ["status"],
            "aggregations": [{"func": "count", "alias": "n"}],
        },
    )
    assert response.status_code == 200, response.text
    by_status = {r["status"]: r["n"] for r in response.json()["rows"]}
    assert by_status["CONFIRMED"] == setup.confirmed_count
    assert by_status["DRAFT"] == setup.draft_count


async def test_run_unknown_entity_is_400(
    client: AsyncClient,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    principal = await reporting_user_factory(keys=_REPORT_KEYS)
    await _authed(client, principal)
    response = await client.post(_RUN_URL, json={"entity": "nope.nope"})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "reporting.invalid_report"


async def test_run_requires_base_report_permission(
    client: AsyncClient,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """A principal WITHOUT reporting.report.run is 403 even holding the source key."""
    principal = await reporting_user_factory(keys=(SALES_ORDER_READ,))
    await _authed(client, principal)
    response = await client.post(
        _RUN_URL, json={"entity": "sales.orders", "columns": ["order_number"]}
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "rbac.permission_denied"


async def test_run_requires_entity_source_permission(
    client: AsyncClient,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """A principal with the base report key but NOT the entity's source read key is 403 — the
    per-entity role gate (D-059). Holds reporting.report.run but not sales.order.read."""
    principal = await reporting_user_factory(keys=(REPORTING_REPORT_RUN,))
    await _authed(client, principal)
    response = await client.post(
        _RUN_URL, json={"entity": "sales.orders", "columns": ["order_number"]}
    )
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["error"]["code"] == "rbac.permission_denied"
    assert body["error"]["details"]["permission"] == SALES_ORDER_READ


async def test_export_streams_csv(
    client: AsyncClient,
    db_session: AsyncSession,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """POST /reports/export returns text/csv with an attachment disposition, the DISPLAY-label
    header line (#166), and the right rows."""
    principal = await reporting_user_factory(keys=_REPORT_KEYS)
    setup = await build_report_builder_setup(db_session, principal.tenant_id)
    await _authed(client, principal)
    response = await client.post(
        _EXPORT_URL,
        json={"entity": "sales.orders", "columns": ["order_number", "status"]},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert lines[0] == "Order Number,Status"
    assert len(lines) - 1 == setup.confirmed_count + setup.draft_count


async def test_export_requires_entity_source_permission(
    client: AsyncClient,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """The export endpoint gates the entity by its source permission too (403, before streaming)."""
    principal = await reporting_user_factory(keys=(REPORTING_REPORT_RUN,))
    await _authed(client, principal)
    response = await client.post(
        _EXPORT_URL, json={"entity": "sales.orders", "columns": ["order_number"]}
    )
    assert response.status_code == 403, response.text


async def test_report_is_tenant_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
    reporting_user_factory: Callable[..., "AsyncIterator[ReportingPrincipal]"],
) -> None:
    """Tenant B's principal (same keys) runs the same report and sees ONLY tenant B's rows — never
    tenant A's (D-007). A and B are seeded the SAME way, but B runs in its own tenant context, so
    the count equals B's own population, not the combined total."""
    principal_a = await reporting_user_factory(keys=_REPORT_KEYS)
    setup_a = await build_report_builder_setup(db_session, principal_a.tenant_id)

    principal_b = await reporting_user_factory(
        slug="rb-beta", email="rb@rb-beta.test", keys=_REPORT_KEYS
    )
    setup_b = await build_report_builder_setup(db_session, principal_b.tenant_id)

    transport = client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        await _authed(client_b, principal_b)
        response = await client_b.post(
            _RUN_URL, json={"entity": "sales.orders", "columns": ["order_number"]}
        )
    assert response.status_code == 200, response.text
    # B sees only B's rows (== B's seeded population), never A's combined total.
    expected_b = setup_b.confirmed_count + setup_b.draft_count
    assert response.json()["row_count"] == expected_b
    # Sanity: A's population is the same size, so a leak would have doubled it.
    assert setup_a.confirmed_count + setup_a.draft_count == expected_b

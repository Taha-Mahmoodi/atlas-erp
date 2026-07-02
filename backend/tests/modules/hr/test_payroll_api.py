"""Payroll HTTP behaviour (PLAN 10.4, D-055): the payroll-run endpoints (create / list / detail /
post / cancel), RBAC (the manage vs post split), pagination, the ≤3-query list budget
(PERFORMANCE §6), and tenant isolation.

Driven against a real bearer-token client whose tenant is wired for the gross→net flow (functional
currency + open year + the three payroll posting defaults + a department and salaried employees).
"""

import uuid
from collections.abc import AsyncIterator, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.constants import (
    HR_PAYROLL_MANAGE,
    HR_PAYROLL_READ,
)
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.hr.conftest import HrPrincipal, PayrollApi
from tests.modules.hr.payroll_factories import build_payroll_setup

_HR = "/api/v1/hr"


def _idem() -> dict[str, str]:
    """A fresh Idempotency-Key header (D-013): create / post need one."""
    return {"Idempotency-Key": uuid.uuid4().hex}


def _run_body(**overrides) -> dict:
    body = {
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "pay_date": "2026-06-30",
        "tax_rate_percent": "20",
    }
    body.update(overrides)
    return body


async def _create_run(client: AsyncClient, **overrides) -> dict:
    resp = await client.post(
        f"{_HR}/payroll-runs", json=_run_body(**overrides), headers=_idem()
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_run_endpoint(payroll_api: PayrollApi) -> None:
    """POST /payroll-runs computes a DRAFT run (gross/tax/net totals) over the wire (PLAN 10.4)."""
    run = await _create_run(payroll_api.client)
    assert run["status"] == "DRAFT"
    assert run["total_gross"] == "8000.000000"
    assert run["total_tax"] == "1600.000000"
    assert run["total_net"] == "6400.000000"
    assert run["employee_count"] == 2
    assert run["run_number"] is None  # claimed at posting


async def test_get_run_detail_includes_lines(payroll_api: PayrollApi) -> None:
    """GET /payroll-runs/{id} returns the run + its per-employee lines (PLAN 10.4)."""
    run = await _create_run(payroll_api.client)
    resp = await payroll_api.client.get(f"{_HR}/payroll-runs/{run['id']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["lines"]) == 2
    for line in body["lines"]:
        gross = float(line["gross_amount"])
        assert float(line["tax_amount"]) + float(line["net_amount"]) == gross


async def test_post_run_endpoint(payroll_api: PayrollApi) -> None:
    """POST /payroll-runs/{id}/post posts the consolidated journal and the run goes POSTED with a
    PAY- number + journal link (PLAN 10.4)."""
    run = await _create_run(payroll_api.client)
    resp = await payroll_api.client.post(
        f"{_HR}/payroll-runs/{run['id']}/post", json={}, headers=_idem()
    )
    assert resp.status_code == 200, resp.text
    posted = resp.json()
    assert posted["status"] == "POSTED"
    assert posted["run_number"].startswith("PAY-")
    # The journal id is set by the finance handler during the event drain (after the post response
    # is captured in-uow, the manufacturing-finish precedent), so it surfaces on the next GET.
    detail = await payroll_api.client.get(f"{_HR}/payroll-runs/{run['id']}")
    assert detail.json()["journal_entry_id"] is not None


async def test_cancel_run_endpoint(payroll_api: PayrollApi) -> None:
    """POST /payroll-runs/{id}/cancel cancels a DRAFT run (PLAN 10.4)."""
    run = await _create_run(payroll_api.client)
    resp = await payroll_api.client.post(f"{_HR}/payroll-runs/{run['id']}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CANCELLED"


async def test_list_runs_paginated_and_filtered(payroll_api: PayrollApi) -> None:
    """GET /payroll-runs is paginated and filters by status (PLAN 10.4)."""
    run_a = await _create_run(payroll_api.client)
    await payroll_api.client.post(f"{_HR}/payroll-runs/{run_a['id']}/cancel")
    await _create_run(payroll_api.client, period_start="2026-07-01", period_end="2026-07-31")

    page = await payroll_api.client.get(f"{_HR}/payroll-runs?limit=1")
    assert page.status_code == 200, page.text
    body = page.json()
    assert len(body["items"]) == 1
    assert body["next_cursor"] is not None

    drafts = await payroll_api.client.get(f"{_HR}/payroll-runs?status=DRAFT")
    assert drafts.status_code == 200
    assert all(item["status"] == "DRAFT" for item in drafts.json()["items"])


async def test_list_runs_query_budget(
    payroll_api: PayrollApi,
    query_counter: Callable[[], QueryCounter],  # noqa: ANN001 - fixture factory typed in conftest
) -> None:
    """The list endpoint stays within the ≤3-query budget (PERFORMANCE §6)."""
    await _create_run(payroll_api.client)
    await assert_query_budget(payroll_api.client, query_counter, f"{_HR}/payroll-runs")


async def test_rbac_manage_cannot_post(
    client: AsyncClient,
    db_session: AsyncSession,
    hr_user_factory: Callable[..., "AsyncIterator[HrPrincipal]"],
) -> None:
    """A principal with manage + read but NOT post can create but is 403 on post — the distinct
    GL-posting authority (D-055)."""
    principal: HrPrincipal = await hr_user_factory(
        slug="pay-mgr",
        email="mgr@pay.test",
        keys=(HR_PAYROLL_READ, HR_PAYROLL_MANAGE, "finance.costcenter.manage"),
    )
    setup = await build_payroll_setup(db_session, principal.tenant_id)
    token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    run = await _create_run(client)
    denied = await client.post(
        f"{_HR}/payroll-runs/{run['id']}/post", json={}, headers=_idem()
    )
    assert denied.status_code == 403
    # Sanity: the run is untouched (still creatable proves manage worked); setup is wired.
    assert setup.employee_ids


async def test_rbac_read_only_cannot_create(
    client: AsyncClient,
    db_session: AsyncSession,
    hr_user_factory: Callable[..., "AsyncIterator[HrPrincipal]"],
) -> None:
    """A read-only principal (``hr.payroll.read`` only) is 403 on create (D-055)."""
    principal: HrPrincipal = await hr_user_factory(
        slug="pay-ro", email="ro@pay.test", keys=(HR_PAYROLL_READ,)
    )
    await build_payroll_setup(db_session, principal.tenant_id)
    token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    denied = await client.post(
        f"{_HR}/payroll-runs", json=_run_body(), headers=_idem()
    )
    assert denied.status_code == 403


async def test_tenant_isolation(
    payroll_api: PayrollApi,
    client: AsyncClient,
    db_session: AsyncSession,
    hr_user_factory: Callable[..., "AsyncIterator[HrPrincipal]"],
) -> None:
    """One tenant's payroll run is not visible to another tenant (D-007)."""
    run = await _create_run(payroll_api.client)
    other: HrPrincipal = await hr_user_factory(slug="pay-other", email="other@pay.test")
    transport = client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        token = await _login(client_b, other)
        client_b.headers["Authorization"] = f"Bearer {token}"
        cross = await client_b.get(f"{_HR}/payroll-runs/{run['id']}")
    assert cross.status_code == 404


async def _login(client: AsyncClient, principal: HrPrincipal) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]

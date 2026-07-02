"""Projects HTTP behaviour (PLAN 11.1, D-056): project / WBS endpoints over the wire, RBAC (read vs
manage vs report.read), pagination, the ≤3-query list budgets (PERFORMANCE §6), the conditional-GET
ETag on the project + WBS reference lists, tenant isolation, and the cost-report endpoint.

Driven against a real bearer-token client whose tenant has a seeded cost centre + customer + COA +
a project.
"""

import uuid
from collections.abc import Callable
from decimal import Decimal

from httpx import AsyncClient

from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.projects.conftest import ProjectsApi, ProjectsPrincipal

_PS = "/api/v1/projects"


# --- Project endpoints --------------------------------------------------------


async def test_create_and_get_project(projects_client: AsyncClient) -> None:
    create = await projects_client.post(
        _PS, json={"code": "PRJ-API", "name": "API project"}
    )
    assert create.status_code == 201, create.text
    project_id = create.json()["id"]
    got = await projects_client.get(f"{_PS}/{project_id}")
    assert got.status_code == 200
    assert got.json()["code"] == "PRJ-API"
    assert got.json()["status"] == "PLANNING"


async def test_update_project_over_the_wire(projects_api: ProjectsApi) -> None:
    resp = await projects_api.client.patch(
        f"{_PS}/{projects_api.setup.project_id}",
        json={"status": "ACTIVE", "name": "Renamed"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ACTIVE"
    assert resp.json()["name"] == "Renamed"


async def test_list_projects_filters_by_status(projects_api: ProjectsApi) -> None:
    """The seeded PLANNING project shows under a PLANNING filter and is excluded by ACTIVE."""
    planning = await projects_api.client.get(_PS, params={"status": "PLANNING"})
    assert planning.status_code == 200
    assert len(planning.json()["items"]) == 1
    active = await projects_api.client.get(_PS, params={"status": "ACTIVE"})
    assert active.json()["items"] == []


async def test_create_project_unknown_customer_422(projects_client: AsyncClient) -> None:
    resp = await projects_client.post(
        _PS,
        json={"code": "PRJ-BADCUST", "name": "X", "customer_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "projects.customer_not_found"


# --- WBS endpoints ------------------------------------------------------------


async def test_create_and_get_wbs_element(projects_api: ProjectsApi) -> None:
    create = await projects_api.client.post(
        f"{_PS}/{projects_api.setup.project_id}/wbs-elements",
        json={"code": "WBS-API", "name": "Phase 1", "budget_amount": "750"},
    )
    assert create.status_code == 201, create.text
    wbs_id = create.json()["id"]
    assert create.json()["status"] == "OPEN"
    got = await projects_api.client.get(f"{_PS}/wbs-elements/{wbs_id}")
    assert got.status_code == 200
    assert got.json()["code"] == "WBS-API"
    assert Decimal(got.json()["budget_amount"]) == Decimal("750")


async def test_wbs_tree_over_the_wire(projects_api: ProjectsApi) -> None:
    base = f"{_PS}/{projects_api.setup.project_id}/wbs-elements"
    parent = await projects_api.client.post(base, json={"code": "WBS-PP", "name": "Parent"})
    parent_id = parent.json()["id"]
    child = await projects_api.client.post(
        base, json={"code": "WBS-CC", "name": "Child", "parent_id": parent_id}
    )
    assert child.status_code == 201, child.text
    assert child.json()["parent_id"] == parent_id


async def test_wbs_cycle_rejected_over_the_wire(projects_api: ProjectsApi) -> None:
    base = f"{_PS}/{projects_api.setup.project_id}/wbs-elements"
    element = await projects_api.client.post(base, json={"code": "WBS-SELF", "name": "Self"})
    element_id = element.json()["id"]
    resp = await projects_api.client.patch(
        f"{_PS}/wbs-elements/{element_id}", json={"parent_id": element_id}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "projects.wbs_cycle"


# --- Cost-report endpoint -----------------------------------------------------


async def test_cost_report_endpoint(projects_api: ProjectsApi, db_session) -> None:
    """The cost-report endpoint returns per-WBS lines with actuals + hours + variance, rolled up.
    The WBS is authored over the wire; the WBS-tagged journal actuals are posted via the finance
    service (there is no projects posting endpoint — projects posts nothing, D-056)."""
    from datetime import date

    from tests.modules.projects.factories import post_wbs_journal

    setup = projects_api.setup
    wbs = await projects_api.client.post(
        f"{_PS}/{setup.project_id}/wbs-elements",
        json={"code": "WBS-RPT", "name": "Reported", "budget_amount": "500"},
    )
    wbs_id = uuid.UUID(wbs.json()["id"])
    await post_wbs_journal(
        db_session,
        setup.tenant_id,
        setup.accounts,
        wbs_id,
        Decimal("300"),
        posting_date=date(2026, 3, 15),
    )
    report = await projects_api.client.get(f"{_PS}/{setup.project_id}/cost-report")
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["project_id"] == str(setup.project_id)
    line = next(line for line in body["lines"] if line["wbs_element_id"] == str(wbs_id))
    assert Decimal(line["budget_amount"]) == Decimal("500")
    assert Decimal(line["actual_cost"]) == Decimal("300")
    assert Decimal(line["variance"]) == Decimal("200")  # 500 − 300


# --- RBAC ---------------------------------------------------------------------


async def _login(client: AsyncClient, principal: ProjectsPrincipal) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


async def test_read_requires_permission(
    client: AsyncClient, projects_user_factory: Callable[..., object]
) -> None:
    """A principal with no projects keys cannot list projects (403)."""
    principal: ProjectsPrincipal = await projects_user_factory(keys=())
    await _login(client, principal)
    resp = await client.get(_PS)
    assert resp.status_code == 403


async def test_manage_requires_manage_permission(
    client: AsyncClient, projects_user_factory: Callable[..., object]
) -> None:
    """A principal with project.read but NOT project.manage cannot create a project (403)."""
    principal: ProjectsPrincipal = await projects_user_factory(keys=("projects.project.read",))
    await _login(client, principal)
    resp = await client.post(_PS, json={"code": "PRJ-NO", "name": "No"})
    assert resp.status_code == 403


async def test_cost_report_requires_report_permission(
    client: AsyncClient, db_session, projects_user_factory: Callable[..., object]
) -> None:
    """A principal with project.read but NOT report.read cannot read the cost report (403)."""
    from tests.modules.projects.factories import build_projects_setup

    principal: ProjectsPrincipal = await projects_user_factory(
        keys=("projects.project.read", "projects.wbs.read")
    )
    setup = await build_projects_setup(db_session, principal.tenant_id)
    await _login(client, principal)
    resp = await client.get(f"{_PS}/{setup.project_id}/cost-report")
    assert resp.status_code == 403


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(
    projects_api: ProjectsApi, projects_client_b: AsyncClient
) -> None:
    """Tenant B cannot see (or read) tenant A's project."""
    project_id = projects_api.setup.project_id
    list_resp = await projects_client_b.get(_PS)
    assert list_resp.status_code == 200
    assert list_resp.json()["items"] == []
    get_resp = await projects_client_b.get(f"{_PS}/{project_id}")
    assert get_resp.status_code == 404


# --- Pagination + ETag + query budgets ----------------------------------------


async def test_project_list_paginated_and_budget(
    projects_api: ProjectsApi, query_counter: Callable[[], QueryCounter]
) -> None:
    for i in range(3):
        resp = await projects_api.client.post(
            _PS, json={"code": f"PRJ-L{i}", "name": f"L{i}"}
        )
        assert resp.status_code == 201, resp.text
    page = await projects_api.client.get(_PS, params={"limit": 2})
    assert page.status_code == 200
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"] is not None
    await assert_query_budget(projects_api.client, query_counter, _PS)


async def test_project_list_etag(projects_api: ProjectsApi) -> None:
    """The project list returns a weak ETag; a matching If-None-Match yields 304 (D-035)."""
    first = await projects_api.client.get(_PS)
    etag = first.headers.get("etag")
    assert etag is not None
    cached = await projects_api.client.get(_PS, headers={"If-None-Match": etag})
    assert cached.status_code == 304


async def test_wbs_list_etag(projects_api: ProjectsApi) -> None:
    """The project's WBS list returns a weak ETag; a matching If-None-Match yields 304 (D-035)."""
    url = f"{_PS}/{projects_api.setup.project_id}/wbs-elements"
    first = await projects_api.client.get(url)
    etag = first.headers.get("etag")
    assert etag is not None
    cached = await projects_api.client.get(url, headers={"If-None-Match": etag})
    assert cached.status_code == 304


async def test_wbs_list_query_budget(
    projects_api: ProjectsApi, query_counter: Callable[[], QueryCounter]
) -> None:
    # Budget 4 (the nested-resource budget per assert_query_budget): user load + ETag count + the
    # project-existence 404 guard + the page select. Still bounded — no per-WBS N+1.
    url = f"{_PS}/{projects_api.setup.project_id}/wbs-elements"
    await assert_query_budget(projects_api.client, query_counter, url, budget=4)

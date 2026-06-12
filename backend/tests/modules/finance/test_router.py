"""Finance HTTP layer: endpoint happy paths, cursor pagination over the wire, and RBAC —
account.manage / period.manage are required (403 without)."""

from collections.abc import AsyncIterator, Callable

from httpx import AsyncClient

from app.modules.finance.constants import (
    FINANCE_ACCOUNT_READ,
    FINANCE_PERIOD_READ,
)
from tests.modules.finance.conftest import FinancePrincipal


async def test_create_and_get_account_endpoint(finance_client: AsyncClient) -> None:
    response = await finance_client.post(
        "/api/v1/finance/accounts",
        json={"code": "1000", "name": "Cash", "account_type": "ASSET"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["normal_balance"] == "DEBIT"  # derived from ASSET
    account_id = body["id"]

    fetched = await finance_client.get(f"/api/v1/finance/accounts/{account_id}")
    assert fetched.status_code == 200
    assert fetched.json()["code"] == "1000"


async def test_list_accounts_endpoint_paginates(finance_client: AsyncClient) -> None:
    for i in range(5):
        resp = await finance_client.post(
            "/api/v1/finance/accounts",
            json={"code": f"{1000 + i}", "name": f"a{i}", "account_type": "ASSET"},
        )
        assert resp.status_code == 201
    page = await finance_client.get("/api/v1/finance/accounts?limit=2")
    assert page.status_code == 200
    body = page.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None
    assert body["limit"] == 2


async def test_create_fiscal_year_endpoint_generates_periods(
    finance_client: AsyncClient,
) -> None:
    response = await finance_client.post(
        "/api/v1/finance/fiscal-years",
        json={"code": "2026", "name": "FY2026", "start_date": "2026-01-01"},
    )
    assert response.status_code == 201, response.text
    year = response.json()
    assert year["end_date"] == "2026-12-31"
    assert year["status"] == "OPEN"

    periods = await finance_client.get(
        f"/api/v1/finance/fiscal-periods?fiscal_year_id={year['id']}"
    )
    assert periods.status_code == 200
    assert len(periods.json()) == 12


async def test_close_and_open_period_endpoints(finance_client: AsyncClient) -> None:
    year = (
        await finance_client.post(
            "/api/v1/finance/fiscal-years",
            json={"code": "2026", "name": "FY2026", "start_date": "2026-01-01"},
        )
    ).json()
    periods = (
        await finance_client.get(
            f"/api/v1/finance/fiscal-periods?fiscal_year_id={year['id']}"
        )
    ).json()
    period_id = periods[0]["id"]

    closed = await finance_client.post(f"/api/v1/finance/fiscal-periods/{period_id}/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"

    reopened = await finance_client.post(f"/api/v1/finance/fiscal-periods/{period_id}/open")
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "OPEN"


async def test_account_manage_required_to_create(
    client: AsyncClient,
    finance_user_factory: Callable[..., AsyncIterator[FinancePrincipal]],
) -> None:
    # A principal holding only the READ keys may not create an account.
    principal = await finance_user_factory(
        slug="ro-acme",
        email="ro@acme.test",
        keys=(FINANCE_ACCOUNT_READ, FINANCE_PERIOD_READ),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    # Read is allowed.
    assert (await client.get("/api/v1/finance/accounts")).status_code == 200
    # Manage is denied.
    forbidden = await client.post(
        "/api/v1/finance/accounts",
        json={"code": "1000", "name": "Cash", "account_type": "ASSET"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "rbac.permission_denied"


async def test_period_manage_required_to_close(
    client: AsyncClient,
    finance_user_factory: Callable[..., AsyncIterator[FinancePrincipal]],
) -> None:
    principal = await finance_user_factory(
        slug="ro2-acme",
        email="ro2@acme.test",
        keys=(FINANCE_ACCOUNT_READ, FINANCE_PERIOD_READ),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    # A fabricated period id is fine: the permission check runs before any lookup.
    import uuid

    forbidden = await client.post(
        f"/api/v1/finance/fiscal-periods/{uuid.uuid4()}/close"
    )
    assert forbidden.status_code == 403


async def test_unauthenticated_request_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/finance/accounts")
    assert response.status_code == 401

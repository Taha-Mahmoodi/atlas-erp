"""Conditional GETs on the slow-changing reference endpoints (PERFORMANCE §3 / D-035, closes #28).

Over the wire: first GET returns 200 + ETag; an immediate If-None-Match re-GET returns 304 with the
same ETag and an empty body; creating a row in that collection invalidates the prior ETag (200, new
tag); a write to a DIFFERENT tenant's same collection does NOT invalidate this tenant's ETag; a
different page (cursor/limit) carries a DIFFERENT ETag so a 304 can never serve the wrong slice; the
304 path is cheaper than the 200 path (it skips the page query); the ``*`` wildcard yields 304; and
tenancy + RBAC are unchanged on these endpoints.
"""

from collections.abc import Callable

from httpx import AsyncClient

from tests.conftest import QueryCounter

# The seven reference endpoints that support conditional requests (PERFORMANCE §3). Journal
# entries / bills / receipts / bank statements / depreciation runs / jobs are deliberately absent —
# they are transactional/fast-changing and carry no ETag. (exchange-rates is transactional rate
# history, not slow-changing reference data, so it is intentionally excluded too.)
_REFERENCE_ENDPOINTS = (
    "/api/v1/finance/accounts",
    "/api/v1/finance/account-groups",
    "/api/v1/finance/currencies",
    "/api/v1/finance/tax-codes",
    "/api/v1/finance/fiscal-years",
    "/api/v1/finance/fiscal-periods",
    "/api/v1/finance/posting-defaults",
)


async def _first_get_returns_etag(client: AsyncClient, url: str) -> str:
    response = await client.get(url)
    assert response.status_code == 200, response.text
    etag = response.headers.get("etag")
    assert etag is not None and etag.startswith('W/"'), response.headers
    return etag


async def test_reference_endpoints_return_etag_and_304(finance_client: AsyncClient) -> None:
    """First GET → 200 + ETag; re-GET with If-None-Match → 304, same ETag, empty body."""
    for url in _REFERENCE_ENDPOINTS:
        etag = await _first_get_returns_etag(finance_client, url)
        again = await finance_client.get(url, headers={"If-None-Match": etag})
        assert again.status_code == 304, f"{url}: {again.text}"
        assert again.headers["etag"] == etag
        assert again.content == b"", f"{url} 304 had a body"


async def test_star_if_none_match_returns_304(finance_client: AsyncClient) -> None:
    """``If-None-Match: *`` matches any existing representation → 304."""
    await finance_client.get("/api/v1/finance/accounts")  # ensure the resource exists
    response = await finance_client.get(
        "/api/v1/finance/accounts", headers={"If-None-Match": "*"}
    )
    assert response.status_code == 304


async def test_creating_a_row_invalidates_the_etag(finance_client: AsyncClient) -> None:
    """After a new row lands in the collection the prior validator no longer matches: the
    If-None-Match re-GET now returns 200 with a NEW ETag."""
    url = "/api/v1/finance/accounts"
    etag = await _first_get_returns_etag(finance_client, url)
    created = await finance_client.post(
        url, json={"code": "2000", "name": "Bank", "account_type": "ASSET"}
    )
    assert created.status_code == 201, created.text
    after = await finance_client.get(url, headers={"If-None-Match": etag})
    assert after.status_code == 200, after.text
    assert after.headers["etag"] != etag


async def test_cross_tenant_write_does_not_invalidate_etag(
    finance_client: AsyncClient, finance_client_b: AsyncClient
) -> None:
    """D-007: tenant B creating accounts must not move tenant A's validator, so A's cached
    conditional request still returns 304. A cross-tenant 304 (B's tag satisfying A) is also
    impossible — the tags differ — but the live RBAC/tenancy filter already prevents B from
    reading A's data at all; here we prove the validator itself is tenant-scoped."""
    url = "/api/v1/finance/accounts"
    await finance_client.post(
        url, json={"code": "1000", "name": "Cash", "account_type": "ASSET"}
    )
    etag_a = await _first_get_returns_etag(finance_client, url)
    # Tenant B writes three accounts into its OWN collection.
    for code in ("9000", "9001", "9002"):
        created = await finance_client_b.post(
            url, json={"code": code, "name": f"B {code}", "account_type": "ASSET"}
        )
        assert created.status_code == 201, created.text
    # Tenant A's validator is unchanged → still a 304.
    still = await finance_client.get(url, headers={"If-None-Match": etag_a})
    assert still.status_code == 304, still.text
    assert still.headers["etag"] == etag_a
    # And B's own tag is a DIFFERENT value (tenant component + data differ).
    etag_b = await _first_get_returns_etag(finance_client_b, url)
    assert etag_b != etag_a


async def test_different_page_has_a_different_etag(finance_client: AsyncClient) -> None:
    """The ETag folds in the request fingerprint (cursor+limit+filters), so two different page
    requests over the same collection get different validators — a 304 can never serve the wrong
    slice. Sending page-1's If-None-Match against a page-2 request must NOT 304."""
    url = "/api/v1/finance/accounts"
    for i in range(4):
        created = await finance_client.post(
            url, json={"code": f"{1000 + i}", "name": f"a{i}", "account_type": "ASSET"}
        )
        assert created.status_code == 201
    page_one = await finance_client.get(f"{url}?limit=2")
    etag_one = page_one.headers["etag"]
    cursor = page_one.json()["next_cursor"]
    assert cursor is not None
    # Same collection, different slice: the page-1 validator must not satisfy a page-2 request.
    page_two = await finance_client.get(
        f"{url}?limit=2&cursor={cursor}", headers={"If-None-Match": etag_one}
    )
    assert page_two.status_code == 200, page_two.text
    assert page_two.headers["etag"] != etag_one
    # A 304 IS available for the identical page-2 request once we hold its own tag.
    etag_two = page_two.headers["etag"]
    repeat = await finance_client.get(
        f"{url}?limit=2&cursor={cursor}", headers={"If-None-Match": etag_two}
    )
    assert repeat.status_code == 304


async def test_304_path_is_cheaper_than_200_path(
    finance_client: AsyncClient, query_counter: Callable[[], QueryCounter]
) -> None:
    """The 304 path must NOT run the full page query: it runs auth + the single ETag aggregate
    (≤3), and strictly fewer statements than the 200 path which additionally runs the page select.
    """
    url = "/api/v1/finance/accounts"
    for i in range(3):
        created = await finance_client.post(
            url, json={"code": f"{1000 + i}", "name": f"a{i}", "account_type": "ASSET"}
        )
        assert created.status_code == 201
    # Warm the RBAC TTL cache so neither measurement pays the permission-resolution query.
    warm = await finance_client.get(url)
    etag = warm.headers["etag"]

    with query_counter() as qc_200:
        ok = await finance_client.get(url)
    assert ok.status_code == 200

    with query_counter() as qc_304:
        not_modified = await finance_client.get(url, headers={"If-None-Match": etag})
    assert not_modified.status_code == 304

    assert qc_304.count <= 3, qc_304.statements
    assert qc_304.count < qc_200.count, (
        f"304 ran {qc_304.count} queries, 200 ran {qc_200.count}; the 304 path must skip the "
        f"page query.\n304:\n" + "\n".join(qc_304.statements) + "\n200:\n"
        + "\n".join(qc_200.statements)
    )


async def test_conditional_endpoints_still_enforce_rbac(
    finance_user_factory, client: AsyncClient
) -> None:
    """RBAC is unchanged: a principal lacking finance.account.read is 403 on the ETag endpoint
    (the conditional path never runs before the permission dependency)."""
    principal = await finance_user_factory(
        slug="no-read", email="x@no-read.test", keys=("finance.fx.manage",)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    token = login.json()["access_token"]
    response = await client.get(
        "/api/v1/finance/accounts", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


async def test_unauthenticated_conditional_request_is_rejected(client: AsyncClient) -> None:
    """No bearer token → 401 even with an If-None-Match header (auth precedes the ETag logic)."""
    response = await client.get(
        "/api/v1/finance/accounts", headers={"If-None-Match": "*"}
    )
    assert response.status_code == 401

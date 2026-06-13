"""Conditional-request core helpers (D-035): collection ETag + If-None-Match comparison + the
304-or-200 epilogue.

Proves at the unit level: the validator is computed from one aggregate query, is tenant-scoped
(tenant B's writes don't move tenant A's tag), flips on any insert/update in the collection, varies
per request fingerprint (so a 304 can't serve a different page slice), and that
``check_not_modified`` honors weak comparison and the ``*`` wildcard. The endpoint-level 304 wiring
(status, empty body, query-count) is proven in tests/modules/finance/test_router_conditional.py.
"""

import uuid

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.conditional import (
    check_not_modified,
    collection_etag,
    conditional_response,
    request_fingerprint,
)
from app.core.tenancy import tenant_context
from app.modules.admin.models import Tenant
from app.modules.finance.constants import AccountType, NormalBalance
from app.modules.finance.models import Account
from tests.conftest import _create_tenant


def _request(if_none_match: str | None = None) -> Request:
    """A minimal ASGI Request carrying an optional If-None-Match header for the comparison tests."""
    headers: list[tuple[bytes, bytes]] = []
    if if_none_match is not None:
        headers.append((b"if-none-match", if_none_match.encode("latin-1")))
    scope = {"type": "http", "method": "GET", "headers": headers, "path": "/"}
    return Request(scope)


async def _add_account(session: AsyncSession, tenant_id: uuid.UUID, code: str) -> Account:
    with tenant_context(tenant_id):
        account = Account(
            code=code,
            name=f"Account {code}",
            account_type=AccountType.ASSET.value,
            normal_balance=NormalBalance.DEBIT.value,
        )
        session.add(account)
        await session.commit()
    return account


# --- check_not_modified ------------------------------------------------------


def test_check_not_modified_matches_identical_tag() -> None:
    etag = 'W/"3-123-abcd1234-ff"'
    assert check_not_modified(_request(etag), etag) is True


def test_check_not_modified_weak_prefix_is_ignored_on_both_sides() -> None:
    """RFC 7232 weak comparison: ``W/"x"`` and ``"x"`` are equal."""
    etag = 'W/"3-123-abcd1234-ff"'
    assert check_not_modified(_request('"3-123-abcd1234-ff"'), etag) is True


def test_check_not_modified_star_matches_any_existing_resource() -> None:
    assert check_not_modified(_request("*"), 'W/"7-9-aaaa-00"') is True


def test_check_not_modified_false_when_tag_differs() -> None:
    assert check_not_modified(_request('W/"3-123-abcd1234-ff"'), 'W/"4-130-abcd1234-ff"') is False


def test_check_not_modified_false_when_header_absent() -> None:
    assert check_not_modified(_request(None), 'W/"3-123-abcd1234-ff"') is False


def test_check_not_modified_matches_within_a_list() -> None:
    target = 'W/"3-123-abcd1234-ff"'
    header = 'W/"1-1-abcd1234-ff", W/"3-123-abcd1234-ff"'
    assert check_not_modified(_request(header), target) is True


# --- collection_etag ---------------------------------------------------------


async def test_collection_etag_is_one_query(
    db_session: AsyncSession, tenant_a: uuid.UUID, query_counter
) -> None:
    """The validator is a single cheap aggregate (PERFORMANCE §2) — COUNT + MAX in one statement."""
    await _add_account(db_session, tenant_a, "1000")
    with tenant_context(tenant_a), query_counter() as qc:
        await collection_etag(db_session, Account)
    assert qc.count == 1, qc.statements


async def test_collection_etag_changes_on_insert(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        empty = await collection_etag(db_session, Account)
    await _add_account(db_session, tenant_a, "1000")
    with tenant_context(tenant_a):
        after = await collection_etag(db_session, Account)
    assert empty != after
    # The empty-collection validator is the documented stable form (count 0, no max).
    assert empty.startswith('W/"0--')


async def test_collection_etag_changes_on_update(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An UPDATE moves MAX(updated_at) (TimestampMixin.onupdate), so the count-stable change is
    still caught — count alone would miss it."""
    account = await _add_account(db_session, tenant_a, "1000")
    with tenant_context(tenant_a):
        before = await collection_etag(db_session, Account)
        account.name = "Renamed"
        await db_session.commit()
        after = await collection_etag(db_session, Account)
    assert before != after


async def test_collection_etag_is_tenant_scoped(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """D-007: a write to tenant B's accounts must NOT move tenant A's validator — the aggregate is
    tenant-filtered AND the tenant component differs, so a cross-tenant 304 is impossible."""
    await _add_account(db_session, tenant_a, "1000")
    with tenant_context(tenant_a):
        before = await collection_etag(db_session, Account)
    # Three writes into tenant B's collection.
    for code in ("2000", "2001", "2002"):
        await _add_account(db_session, tenant_b, code)
    with tenant_context(tenant_a):
        after = await collection_etag(db_session, Account)
    assert before == after
    # And the two tenants never share a validator even with overlapping data.
    with tenant_context(tenant_b):
        tag_b = await collection_etag(db_session, Account)
    assert before != tag_b


async def test_collection_etag_varies_by_request_fingerprint(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The request fingerprint (cursor+limit+filters) is baked into the tag, so two different page
    requests over the SAME unchanged collection get DIFFERENT validators — a 304 can never serve
    the wrong slice."""
    await _add_account(db_session, tenant_a, "1000")
    page_one = request_fingerprint(None, 2)
    page_two = request_fingerprint("some-cursor", 2)
    with tenant_context(tenant_a):
        tag_one = await collection_etag(db_session, Account, request_fingerprint=page_one)
        tag_two = await collection_etag(db_session, Account, request_fingerprint=page_two)
    assert tag_one != tag_two


# --- conditional_response ----------------------------------------------------


async def test_conditional_response_returns_304_without_running_builder() -> None:
    """On a matching If-None-Match the builder is NOT awaited (the 304 path skips the page query)
    and a bare 304 + ETag header comes back with no body."""
    etag = 'W/"3-123-abcd1234-ff"'
    ran = False

    async def builder() -> str:
        nonlocal ran
        ran = True
        return "page-body"

    result = await conditional_response(_request(etag), Response(), etag, builder)
    assert isinstance(result, Response)
    assert result.status_code == 304
    assert result.headers["ETag"] == etag
    assert result.body == b""
    assert ran is False


async def test_conditional_response_runs_builder_and_sets_header_on_miss() -> None:
    etag = 'W/"3-123-abcd1234-ff"'
    response = Response()

    async def builder() -> str:
        return "page-body"

    result = await conditional_response(_request('W/"old"'), response, etag, builder)
    assert result == "page-body"
    assert response.headers["ETag"] == etag


# --- a third tenant via the raw helper (kept self-contained) ------------------


async def test_create_tenant_helper_available(db_session: AsyncSession) -> None:
    """Guards against the shared _create_tenant helper drifting (used by the cross-tenant fixture
    pattern); a trivial smoke so the import above is exercised even if a refactor removes a use."""
    tenant_id = await _create_tenant(db_session, "tenant-c")
    assert isinstance(tenant_id, uuid.UUID)
    fetched = await db_session.get(Tenant, tenant_id)
    assert fetched is not None

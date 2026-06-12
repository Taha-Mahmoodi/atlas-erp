"""Journal HTTP API: create/post/reverse/list/get, idempotent posting, RBAC (D-017/D-013/D-009).

Exercises the real router over httpx.AsyncClient with bearer tokens. The finance_client holds all
journal permissions; a narrower client proves the per-action RBAC guards. Posting/reversal carry
the required Idempotency-Key header (D-013).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_ACCOUNT_MANAGE,
    FINANCE_ACCOUNT_READ,
    FINANCE_JOURNAL_READ,
    FINANCE_PERIOD_MANAGE,
    FINANCE_PERIOD_READ,
)
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate

# The finance_client provisions tenant "fin-acme"; mint its COA + open FY against that tenant.
_PD = "2026-03-15"


async def _bootstrap(db_session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, str]:
    """Create Cash (1000) + Sales (4000) accounts and an open 2026 fiscal year for the
    finance_client's tenant. Returns the two account ids as strings (for JSON bodies)."""
    with tenant_context(tenant_id):
        cash = await service.create_account(
            db_session, tenant_id, AccountCreate(code="1000", name="Cash", account_type="ASSET")
        )
        sales = await service.create_account(
            db_session,
            tenant_id,
            AccountCreate(code="4000", name="Sales", account_type="REVENUE"),
        )
        await service.create_fiscal_year(
            db_session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
    return {"cash": str(cash.id), "sales": str(sales.id)}


def _entry_body(accounts: dict[str, str], amount: str = "100.00") -> dict:
    return {
        "posting_date": _PD,
        "currency_code": "USD",
        "description": "API test",
        "lines": [
            {"account_id": accounts["cash"], "transaction_debit_amount": amount},
            {"account_id": accounts["sales"], "transaction_credit_amount": amount},
        ],
    }


async def _tenant_of(client: AsyncClient) -> uuid.UUID:
    me = await client.get("/api/v1/auth/me")
    return uuid.UUID(me.json()["tenant_id"])


async def test_create_post_get_flow(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    accounts = await _bootstrap(db_session, tenant_id)

    create = await finance_client.post(
        "/api/v1/finance/journal-entries", json=_entry_body(accounts)
    )
    assert create.status_code == 201, create.text
    entry_id = create.json()["id"]
    assert create.json()["status"] == "DRAFT"
    assert create.json()["entry_number"] is None

    post = await finance_client.post(
        f"/api/v1/finance/journal-entries/{entry_id}/post",
        headers={"Idempotency-Key": "post-1"},
    )
    assert post.status_code == 200, post.text
    body = post.json()
    assert body["status"] == "POSTED"
    assert body["entry_number"] == "JE-2026-00001"
    assert all(line["is_posted"] for line in body["lines"])
    assert all(line["posting_date"] == _PD for line in body["lines"])

    got = await finance_client.get(f"/api/v1/finance/journal-entries/{entry_id}")
    assert got.status_code == 200
    assert len(got.json()["lines"]) == 2


async def test_post_is_idempotent(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    accounts = await _bootstrap(db_session, tenant_id)
    entry_id = (
        await finance_client.post(
            "/api/v1/finance/journal-entries", json=_entry_body(accounts)
        )
    ).json()["id"]

    first = await finance_client.post(
        f"/api/v1/finance/journal-entries/{entry_id}/post",
        headers={"Idempotency-Key": "idem-post"},
    )
    second = await finance_client.post(
        f"/api/v1/finance/journal-entries/{entry_id}/post",
        headers={"Idempotency-Key": "idem-post"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers.get("Idempotency-Replayed") == "true"
    # Same response; one posting only (the number is identical, not incremented).
    assert first.json()["entry_number"] == second.json()["entry_number"] == "JE-2026-00001"


async def test_post_requires_idempotency_key(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    accounts = await _bootstrap(db_session, tenant_id)
    entry_id = (
        await finance_client.post(
            "/api/v1/finance/journal-entries", json=_entry_body(accounts)
        )
    ).json()["id"]
    resp = await finance_client.post(f"/api/v1/finance/journal-entries/{entry_id}/post")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "idempotency.key_required"


async def test_post_to_closed_period_returns_422(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    accounts = await _bootstrap(db_session, tenant_id)
    # Close the March period.
    with tenant_context(tenant_id):
        years = await service.list_fiscal_years(db_session, tenant_id)
        periods = await service.list_fiscal_periods(db_session, tenant_id, years[0].id)
        march = next(p for p in periods if p.start_date == date(2026, 3, 1))
        await service.close_period(db_session, tenant_id, march.id)
        await db_session.commit()

    entry_id = (
        await finance_client.post(
            "/api/v1/finance/journal-entries", json=_entry_body(accounts)
        )
    ).json()["id"]
    resp = await finance_client.post(
        f"/api/v1/finance/journal-entries/{entry_id}/post",
        headers={"Idempotency-Key": "closed-post"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "finance.period_closed"


async def test_reverse_flow(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    accounts = await _bootstrap(db_session, tenant_id)
    entry_id = (
        await finance_client.post(
            "/api/v1/finance/journal-entries", json=_entry_body(accounts)
        )
    ).json()["id"]
    await finance_client.post(
        f"/api/v1/finance/journal-entries/{entry_id}/post",
        headers={"Idempotency-Key": "rev-post"},
    )
    reverse = await finance_client.post(
        f"/api/v1/finance/journal-entries/{entry_id}/reverse",
        headers={"Idempotency-Key": "rev-1"},
        json={"reversal_date": "2026-04-01"},
    )
    assert reverse.status_code == 200, reverse.text
    reversal = reverse.json()
    assert reversal["status"] == "POSTED"
    assert reversal["reverses_entry_id"] == entry_id
    assert reversal["entry_number"] == "JE-2026-00002"

    original = await finance_client.get(f"/api/v1/finance/journal-entries/{entry_id}")
    assert original.json()["status"] == "REVERSED"
    assert original.json()["reversed_by_entry_id"] == reversal["id"]


async def test_list_journal_entries(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    accounts = await _bootstrap(db_session, tenant_id)
    for _ in range(2):
        await finance_client.post(
            "/api/v1/finance/journal-entries", json=_entry_body(accounts)
        )
    resp = await finance_client.get("/api/v1/finance/journal-entries")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


# --- RBAC ---------------------------------------------------------------------


@pytest.fixture
async def reader_client(
    client: AsyncClient,
    finance_user_factory,
) -> AsyncClient:
    """A client whose principal holds read-only finance keys (no journal.post/reverse)."""
    from tests.modules.finance.conftest import _login

    principal = await finance_user_factory(
        slug="fin-reader",
        email="reader@fin-reader.test",
        keys=(
            FINANCE_ACCOUNT_READ,
            FINANCE_ACCOUNT_MANAGE,
            FINANCE_PERIOD_READ,
            FINANCE_PERIOD_MANAGE,
            FINANCE_JOURNAL_READ,
        ),
    )
    token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


async def test_post_requires_journal_post_permission(
    reader_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(reader_client)
    accounts = await _bootstrap(db_session, tenant_id)
    # The reader can create a draft? No — create is guarded by journal.post too. So create is 403.
    create = await reader_client.post(
        "/api/v1/finance/journal-entries", json=_entry_body(accounts)
    )
    assert create.status_code == 403
    assert create.json()["error"]["code"] == "rbac.permission_denied"


async def test_reverse_requires_journal_reverse_permission(
    reader_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(reader_client)
    accounts = await _bootstrap(db_session, tenant_id)
    # Build + post an entry directly (service) so the reader has something to attempt to reverse.
    from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate

    with tenant_context(tenant_id):
        from app.core.events import run_in_uow

        entry = await service.create_draft_entry(
            db_session,
            tenant_id,
            JournalEntryCreate(
                posting_date=date(2026, 3, 15),
                currency_code="USD",
                lines=[
                    JournalLineCreate(
                        account_id=uuid.UUID(accounts["cash"]),
                        transaction_debit_amount=Decimal("5.00"),
                    ),
                    JournalLineCreate(
                        account_id=uuid.UUID(accounts["sales"]),
                        transaction_credit_amount=Decimal("5.00"),
                    ),
                ],
            ),
        )
        await db_session.commit()
        await run_in_uow(
            db_session, lambda: service.post_entry(db_session, tenant_id, entry.id)
        )

    resp = await reader_client.post(
        f"/api/v1/finance/journal-entries/{entry.id}/reverse",
        headers={"Idempotency-Key": "rev-403"},
        json={"reversal_date": "2026-04-01"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "rbac.permission_denied"

"""AR HTTP API: invoice create/post, receipt, dunning run, aging, idempotency, RBAC (PLAN 4.6).

Exercises the real ar_router over httpx.AsyncClient with bearer tokens. The finance_client holds all
AR permissions; narrower clients prove the per-action RBAC guards. Post/receipt/dunning carry the
required Idempotency-Key header (D-013). The AP API suite (test_payables_api.py) mirror.
"""

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_AR_MANAGE,
    FINANCE_AR_READ,
)
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate
from tests.conftest import QueryCounter, assert_query_budget


async def _bootstrap(db_session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, str]:
    """Create bank (1000), AR control (1200), revenue (4000) accounts + open 2026 year for the
    finance_client's tenant. Returns the account ids as strings (for JSON bodies)."""
    ids: dict[str, str] = {}
    with tenant_context(tenant_id):
        for code, name, atype in (
            ("1000", "Bank", "ASSET"),
            ("1200", "Accounts Receivable", "ASSET"),
            ("4000", "Service Revenue", "REVENUE"),
        ):
            account = await service.create_account(
                db_session, tenant_id, AccountCreate(code=code, name=name, account_type=atype)
            )
            ids[code] = str(account.id)
        await service.create_fiscal_year(
            db_session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()
    return ids


def _invoice_body(ids: dict[str, str], partner_id: str, net: str = "100.00") -> dict:
    return {
        "partner_id": partner_id,
        "partner_name": "Globex Inc",
        "invoice_date": "2026-03-01",
        "due_date": "2026-03-31",
        "currency_code": "USD",
        "ar_account_id": ids["1200"],
        "lines": [{"account_id": ids["4000"], "net_amount": net}],
    }


async def _tenant_of(client: AsyncClient) -> uuid.UUID:
    me = await client.get("/api/v1/auth/me")
    return uuid.UUID(me.json()["tenant_id"])


async def test_create_post_receive_flow(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    partner = str(uuid.uuid4())

    create = await finance_client.post(
        "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner)
    )
    assert create.status_code == 201, create.text
    invoice_id = create.json()["id"]

    post = await finance_client.post(
        f"/api/v1/finance/customer-invoices/{invoice_id}/post",
        headers={"Idempotency-Key": "invoice-post-1"},
    )
    assert post.status_code == 200, post.text
    body = post.json()
    assert body["status"] == "POSTED"
    assert body["invoice_number"] == "INV-2026-00001"
    assert Decimal(body["open_amount"]) == Decimal("100.00")
    assert body["dunning_level"] == 0

    receive = await finance_client.post(
        "/api/v1/finance/customer-receipts",
        json={
            "partner_id": partner,
            "partner_name": "Globex Inc",
            "receipt_date": "2026-03-15",
            "currency_code": "USD",
            "bank_account_id": ids["1000"],
            "amount": "100.00",
            "allocations": [{"invoice_id": invoice_id, "amount": "100.00"}],
        },
        headers={"Idempotency-Key": "receipt-1"},
    )
    assert receive.status_code == 201, receive.text
    assert receive.json()["status"] == "POSTED"
    assert len(receive.json()["allocations"]) == 1

    detail = await finance_client.get(f"/api/v1/finance/customer-invoices/{invoice_id}")
    assert detail.json()["status"] == "PAID"
    assert Decimal(detail.json()["open_amount"]) == Decimal("0")


async def test_post_invoice_is_idempotent_over_http(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    partner = str(uuid.uuid4())
    invoice_id = (
        await finance_client.post(
            "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner)
        )
    ).json()["id"]
    first = await finance_client.post(
        f"/api/v1/finance/customer-invoices/{invoice_id}/post",
        headers={"Idempotency-Key": "idem-invoice"},
    )
    second = await finance_client.post(
        f"/api/v1/finance/customer-invoices/{invoice_id}/post",
        headers={"Idempotency-Key": "idem-invoice"},
    )
    assert first.status_code == second.status_code == 200
    assert second.headers.get("Idempotency-Replayed") == "true"
    assert first.json()["invoice_number"] == second.json()["invoice_number"]


async def test_dunning_run_endpoint(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    partner = str(uuid.uuid4())
    invoice_id = (
        await finance_client.post(
            "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner)
        )
    ).json()["id"]
    await finance_client.post(
        f"/api/v1/finance/customer-invoices/{invoice_id}/post",
        headers={"Idempotency-Key": "dun-invoice"},
    )
    run = await finance_client.post(
        "/api/v1/finance/dunning-runs",
        json={"as_of": "2026-04-10"},  # due 2026-03-31 -> 10 days overdue -> level 1
        headers={"Idempotency-Key": "dun-1"},
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert len(body["notices"]) == 1
    assert body["notices"][0]["new_level"] == 1
    # The invoice now reads dunning_level 1.
    detail = await finance_client.get(f"/api/v1/finance/customer-invoices/{invoice_id}")
    assert detail.json()["dunning_level"] == 1
    assert detail.json()["last_dunned_date"] == "2026-04-10"


async def test_ar_aging_endpoint(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    partner = str(uuid.uuid4())
    invoice_id = (
        await finance_client.post(
            "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner)
        )
    ).json()["id"]
    await finance_client.post(
        f"/api/v1/finance/customer-invoices/{invoice_id}/post",
        headers={"Idempotency-Key": "aging-invoice"},
    )
    aging = await finance_client.get("/api/v1/finance/ar-aging?as_of=2026-04-15")
    assert aging.status_code == 200, aging.text
    body = aging.json()
    # Due 2026-03-31, as-of 2026-04-15 -> 15 days overdue -> the 1-30 bucket.
    assert Decimal(body["days_1_30"]) == Decimal("100.00")
    assert Decimal(body["total"]) == Decimal("100.00")
    assert len(body["partners"]) == 1


async def test_ar_list_and_detail_query_count(
    finance_client: AsyncClient,
    db_session: AsyncSession,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """PERFORMANCE §2: warm-path invoice/receipt lists ≤3 queries; invoice detail ≤4."""
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    partner = str(uuid.uuid4())
    invoice_id = ""
    for _ in range(3):
        created = await finance_client.post(
            "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner)
        )
        assert created.status_code == 201
        invoice_id = created.json()["id"]
    posted = await finance_client.post(
        f"/api/v1/finance/customer-invoices/{invoice_id}/post",
        headers={"Idempotency-Key": "qc-invoice"},
    )
    assert posted.status_code == 200, posted.text
    received = await finance_client.post(
        "/api/v1/finance/customer-receipts",
        json={
            "partner_id": partner,
            "partner_name": "Globex Inc",
            "receipt_date": "2026-03-15",
            "currency_code": "USD",
            "bank_account_id": ids["1000"],
            "amount": "100.00",
            "allocations": [{"invoice_id": invoice_id, "amount": "100.00"}],
        },
        headers={"Idempotency-Key": "qc-receipt"},
    )
    assert received.status_code == 201, received.text
    await assert_query_budget(finance_client, query_counter, "/api/v1/finance/customer-invoices")
    await assert_query_budget(finance_client, query_counter, "/api/v1/finance/customer-receipts")
    await assert_query_budget(
        finance_client, query_counter, f"/api/v1/finance/customer-invoices/{invoice_id}", budget=4
    )


# --- RBAC ---------------------------------------------------------------------


async def test_post_invoice_requires_ar_manage(
    client: AsyncClient, db_session: AsyncSession, finance_user_factory
) -> None:
    # A reader (ar.read only) cannot create an invoice (guarded by ar.manage).
    principal = await finance_user_factory(
        slug="ar-reader", email="r@ar.test", keys=(FINANCE_AR_READ,)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "ar-reader", "email": "r@ar.test", "password": principal.password},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    ids = await _bootstrap(db_session, principal.tenant_id)
    resp = await client.post(
        "/api/v1/finance/customer-invoices", json=_invoice_body(ids, str(uuid.uuid4()))
    )
    assert resp.status_code == 403


async def test_receipt_requires_ar_collect(
    client: AsyncClient, db_session: AsyncSession, finance_user_factory
) -> None:
    # A manager (ar.manage + ar.read, no ar.collect) can post an invoice but not receive it.
    principal = await finance_user_factory(
        slug="ar-mgr", email="m@ar.test", keys=(FINANCE_AR_READ, FINANCE_AR_MANAGE)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "ar-mgr", "email": "m@ar.test", "password": principal.password},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    ids = await _bootstrap(db_session, principal.tenant_id)
    partner = str(uuid.uuid4())
    invoice_id = (
        await client.post("/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner))
    ).json()["id"]
    await client.post(
        f"/api/v1/finance/customer-invoices/{invoice_id}/post",
        headers={"Idempotency-Key": "mgr-post"},
    )
    receive = await client.post(
        "/api/v1/finance/customer-receipts",
        json={
            "partner_id": partner,
            "partner_name": "Globex Inc",
            "receipt_date": "2026-03-15",
            "currency_code": "USD",
            "bank_account_id": ids["1000"],
            "amount": "100.00",
            "allocations": [{"invoice_id": invoice_id, "amount": "100.00"}],
        },
        headers={"Idempotency-Key": "mgr-receive"},
    )
    assert receive.status_code == 403


async def test_dunning_requires_ar_collect(
    client: AsyncClient, db_session: AsyncSession, finance_user_factory
) -> None:
    # ar.manage + ar.read (no ar.collect) cannot run dunning either.
    principal = await finance_user_factory(
        slug="ar-mgr2", email="m2@ar.test", keys=(FINANCE_AR_READ, FINANCE_AR_MANAGE)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "ar-mgr2", "email": "m2@ar.test", "password": principal.password},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    resp = await client.post(
        "/api/v1/finance/dunning-runs",
        json={"as_of": "2026-04-10"},
        headers={"Idempotency-Key": "dun-rbac"},
    )
    assert resp.status_code == 403

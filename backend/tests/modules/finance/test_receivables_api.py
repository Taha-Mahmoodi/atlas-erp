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
from tests.modules.finance.factories import seed_advance_account


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


def _idem() -> dict[str, str]:
    """A fresh Idempotency-Key header (#88 — draft creation now requires one)."""
    return {"Idempotency-Key": str(uuid.uuid4())}


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
        "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner), headers=_idem()
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
            "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner), headers=_idem()
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
            "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner), headers=_idem()
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
            "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner), headers=_idem()
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
            "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner), headers=_idem()
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


async def test_a_deposit_is_taken_and_applied_over_http_and_the_apply_is_idempotent(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The PLAN 20.4 endpoints end to end: a receipt with NO allocations is accepted and stands as
    on-account money, and POST /customer-receipts/{id}/applications spends it onto an invoice.

    The replay is the point of the second half — applying is a financial-document effect (D-013),
    so a retried request must return the first response and NOT spend the deposit twice. The
    service tests bypass HTTP; nothing else exercises the router, the schema or the key.
    """
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    await seed_advance_account(db_session, tenant_id)
    partner = str(uuid.uuid4())

    deposit = await finance_client.post(
        "/api/v1/finance/customer-receipts",
        json={
            "partner_id": partner,
            "partner_name": "Globex Inc",
            "receipt_date": "2026-03-15",
            "currency_code": "USD",
            "bank_account_id": ids["1000"],
            "amount": "500.00",
        },
        headers={"Idempotency-Key": "deposit-1"},
    )
    assert deposit.status_code == 201, deposit.text
    assert Decimal(deposit.json()["unapplied_amount"]) == Decimal("500.00")
    assert deposit.json()["allocations"] == []
    receipt_id = deposit.json()["id"]

    invoice_id = (
        await finance_client.post(
            "/api/v1/finance/customer-invoices",
            json=_invoice_body(ids, partner, net="300.00"),
            headers=_idem(),
        )
    ).json()["id"]
    posted = await finance_client.post(
        f"/api/v1/finance/customer-invoices/{invoice_id}/post",
        headers={"Idempotency-Key": "deposit-invoice-post"},
    )
    assert posted.status_code == 200, posted.text

    body = {"allocations": [{"invoice_id": invoice_id, "amount": "300.00"}]}
    applied = await finance_client.post(
        f"/api/v1/finance/customer-receipts/{receipt_id}/applications",
        json=body,
        headers={"Idempotency-Key": "apply-1"},
    )
    assert applied.status_code == 201, applied.text
    assert Decimal(applied.json()["unapplied_amount"]) == Decimal("200.00")
    assert len(applied.json()["allocations"]) == 1

    replay = await finance_client.post(
        f"/api/v1/finance/customer-receipts/{receipt_id}/applications",
        json=body,
        headers={"Idempotency-Key": "apply-1"},
    )
    assert replay.status_code == 201, replay.text
    assert replay.json() == applied.json()
    invoice = await finance_client.get(f"/api/v1/finance/customer-invoices/{invoice_id}")
    assert invoice.json()["status"] == "PAID"
    assert Decimal(invoice.json()["open_amount"]) == Decimal("0")


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
        "/api/v1/finance/customer-invoices",
        json=_invoice_body(ids, str(uuid.uuid4())),
        headers=_idem(),
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
        await client.post(
            "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner), headers=_idem()
        )
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


async def test_create_invoice_is_idempotent_and_requires_key(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Regression for #88: draft invoice creation registers a core document, so it must carry the
    D-013 idempotency contract like every other document-creating endpoint."""
    ids = await _bootstrap(db_session, await _tenant_of(finance_client))
    partner = str(uuid.uuid4())

    missing = await finance_client.post(
        "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner)
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "idempotency.key_required"

    headers = {"Idempotency-Key": "inv-create-1"}
    first = await finance_client.post(
        "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner), headers=headers
    )
    assert first.status_code == 201, first.text
    replay = await finance_client.post(
        "/api/v1/finance/customer-invoices", json=_invoice_body(ids, partner), headers=headers
    )
    assert replay.status_code == 201
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert replay.json()["id"] == first.json()["id"]  # ONE draft document, not two

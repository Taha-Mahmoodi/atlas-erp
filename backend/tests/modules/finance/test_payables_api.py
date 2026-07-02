"""AP HTTP API: bill create/post, payment, payment run, aging, idempotency, RBAC (PLAN 4.5).

Exercises the real ap_router over httpx.AsyncClient with bearer tokens. The finance_client holds all
AP permissions; narrower clients prove the per-action RBAC guards. Post/pay/run carry the required
Idempotency-Key header (D-013).
"""

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs import JobStatus, wait_for_jobs
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_AP_MANAGE,
    FINANCE_AP_READ,
)
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate
from tests.conftest import QueryCounter, assert_query_budget


async def _bootstrap(db_session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, str]:
    """Create bank (1000), AP control (2000), expense (5000) accounts + open 2026 year for the
    finance_client's tenant. Returns the account ids as strings (for JSON bodies)."""
    ids: dict[str, str] = {}
    with tenant_context(tenant_id):
        for code, name, atype in (
            ("1000", "Bank", "ASSET"),
            ("2000", "Accounts Payable", "LIABILITY"),
            ("5000", "Office Expense", "EXPENSE"),
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


def _bill_body(ids: dict[str, str], partner_id: str, net: str = "100.00") -> dict:
    return {
        "partner_id": partner_id,
        "partner_name": "Acme Supplies",
        "bill_date": "2026-03-01",
        "due_date": "2026-03-31",
        "currency_code": "USD",
        "ap_account_id": ids["2000"],
        "lines": [{"account_id": ids["5000"], "net_amount": net}],
    }


async def _tenant_of(client: AsyncClient) -> uuid.UUID:
    me = await client.get("/api/v1/auth/me")
    return uuid.UUID(me.json()["tenant_id"])


async def test_create_post_pay_flow(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    partner = str(uuid.uuid4())

    create = await finance_client.post(
        "/api/v1/finance/vendor-bills", json=_bill_body(ids, partner), headers=_idem()
    )
    assert create.status_code == 201, create.text
    bill_id = create.json()["id"]

    post = await finance_client.post(
        f"/api/v1/finance/vendor-bills/{bill_id}/post",
        headers={"Idempotency-Key": "bill-post-1"},
    )
    assert post.status_code == 200, post.text
    body = post.json()
    assert body["status"] == "POSTED"
    assert body["bill_number"] == "BILL-2026-00001"
    assert Decimal(body["open_amount"]) == Decimal("100.00")

    pay = await finance_client.post(
        "/api/v1/finance/vendor-payments",
        json={
            "partner_id": partner,
            "partner_name": "Acme Supplies",
            "payment_date": "2026-03-15",
            "currency_code": "USD",
            "bank_account_id": ids["1000"],
            "amount": "100.00",
            "allocations": [{"bill_id": bill_id, "amount": "100.00"}],
        },
        headers={"Idempotency-Key": "pay-1"},
    )
    assert pay.status_code == 201, pay.text
    assert pay.json()["status"] == "POSTED"
    assert len(pay.json()["allocations"]) == 1

    detail = await finance_client.get(f"/api/v1/finance/vendor-bills/{bill_id}")
    assert detail.json()["status"] == "PAID"
    assert Decimal(detail.json()["open_amount"]) == Decimal("0")


async def test_post_bill_is_idempotent_over_http(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    partner = str(uuid.uuid4())
    bill_id = (
        await finance_client.post(
            "/api/v1/finance/vendor-bills", json=_bill_body(ids, partner), headers=_idem()
        )
    ).json()["id"]
    first = await finance_client.post(
        f"/api/v1/finance/vendor-bills/{bill_id}/post",
        headers={"Idempotency-Key": "idem-bill"},
    )
    second = await finance_client.post(
        f"/api/v1/finance/vendor-bills/{bill_id}/post",
        headers={"Idempotency-Key": "idem-bill"},
    )
    assert first.status_code == second.status_code == 200
    assert second.headers.get("Idempotency-Replayed") == "true"
    assert first.json()["bill_number"] == second.json()["bill_number"]


async def test_payment_run_returns_202_and_pays_due_bills_in_background(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The #26 contract: POST /payment-runs returns 202 {job_id, PENDING}; the background job
    completes, its result carries the created payment, and the business outcome is unchanged
    (the due bill ends PAID with one posted payment)."""
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    partner = str(uuid.uuid4())
    bill_id = (
        await finance_client.post(
            "/api/v1/finance/vendor-bills", json=_bill_body(ids, partner), headers=_idem()
        )
    ).json()["id"]
    await finance_client.post(
        f"/api/v1/finance/vendor-bills/{bill_id}/post",
        headers={"Idempotency-Key": "run-bill"},
    )
    run = await finance_client.post(
        "/api/v1/finance/payment-runs",
        json={"up_to_due_date": "2026-03-31", "bank_account_id": ids["1000"]},
        headers={"Idempotency-Key": "run-1"},
    )
    assert run.status_code == 202, run.text
    assert run.json()["status"] == JobStatus.PENDING.value
    job_id = run.json()["job_id"]
    # A replayed key returns the SAME job id — the run cannot be submitted twice (D-013).
    replay = await finance_client.post(
        "/api/v1/finance/payment-runs",
        json={"up_to_due_date": "2026-03-31", "bank_account_id": ids["1000"]},
        headers={"Idempotency-Key": "run-1"},
    )
    assert replay.status_code == 202
    assert replay.json()["job_id"] == job_id

    await wait_for_jobs()
    job = await finance_client.get(f"/api/v1/jobs/{job_id}")
    assert job.status_code == 200, job.text
    assert job.json()["status"] == JobStatus.COMPLETED.value
    assert job.json()["result"]["payment_count"] == 1
    assert len(job.json()["result"]["payment_ids"]) == 1

    # Business outcomes unchanged from the old synchronous run: the bill is fully paid.
    detail = await finance_client.get(f"/api/v1/finance/vendor-bills/{bill_id}")
    assert detail.json()["status"] == "PAID"
    assert Decimal(detail.json()["open_amount"]) == Decimal("0")
    payments = await finance_client.get("/api/v1/finance/vendor-payments")
    assert [p["id"] for p in payments.json()["items"]] == job.json()["result"]["payment_ids"]


async def test_ap_aging_endpoint(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    partner = str(uuid.uuid4())
    bill_id = (
        await finance_client.post(
            "/api/v1/finance/vendor-bills", json=_bill_body(ids, partner), headers=_idem()
        )
    ).json()["id"]
    await finance_client.post(
        f"/api/v1/finance/vendor-bills/{bill_id}/post",
        headers={"Idempotency-Key": "aging-bill"},
    )
    aging = await finance_client.get("/api/v1/finance/ap-aging?as_of=2026-04-15")
    assert aging.status_code == 200, aging.text
    body = aging.json()
    # Due 2026-03-31, as-of 2026-04-15 -> 15 days overdue -> the 1-30 bucket.
    assert Decimal(body["days_1_30"]) == Decimal("100.00")
    assert Decimal(body["total"]) == Decimal("100.00")
    assert len(body["partners"]) == 1


async def test_ap_list_and_detail_query_count(
    finance_client: AsyncClient,
    db_session: AsyncSession,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """PERFORMANCE §2: warm-path bill/payment lists ≤3 queries; bill detail (with lines) ≤4."""
    tenant_id = await _tenant_of(finance_client)
    ids = await _bootstrap(db_session, tenant_id)
    partner = str(uuid.uuid4())
    bill_id = ""
    for _ in range(3):
        created = await finance_client.post(
            "/api/v1/finance/vendor-bills", json=_bill_body(ids, partner), headers=_idem()
        )
        assert created.status_code == 201
        bill_id = created.json()["id"]
    posted = await finance_client.post(
        f"/api/v1/finance/vendor-bills/{bill_id}/post",
        headers={"Idempotency-Key": "qc-bill"},
    )
    assert posted.status_code == 200, posted.text
    paid = await finance_client.post(
        "/api/v1/finance/vendor-payments",
        json={
            "partner_id": partner,
            "partner_name": "Acme Supplies",
            "payment_date": "2026-03-15",
            "currency_code": "USD",
            "bank_account_id": ids["1000"],
            "amount": "100.00",
            "allocations": [{"bill_id": bill_id, "amount": "100.00"}],
        },
        headers={"Idempotency-Key": "qc-pay"},
    )
    assert paid.status_code == 201, paid.text
    await assert_query_budget(finance_client, query_counter, "/api/v1/finance/vendor-bills")
    await assert_query_budget(finance_client, query_counter, "/api/v1/finance/vendor-payments")
    await assert_query_budget(
        finance_client, query_counter, f"/api/v1/finance/vendor-bills/{bill_id}", budget=4
    )


# --- RBAC ---------------------------------------------------------------------


async def test_post_bill_requires_ap_manage(
    client: AsyncClient, db_session: AsyncSession, finance_user_factory
) -> None:
    # A reader (ap.read only) cannot create a bill (guarded by ap.manage).
    principal = await finance_user_factory(
        slug="ap-reader", email="r@ap.test", keys=(FINANCE_AP_READ,)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "ap-reader", "email": "r@ap.test", "password": principal.password},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    ids = await _bootstrap(db_session, principal.tenant_id)
    resp = await client.post(
        "/api/v1/finance/vendor-bills", json=_bill_body(ids, str(uuid.uuid4())), headers=_idem()
    )
    assert resp.status_code == 403


async def test_payment_requires_ap_pay(
    client: AsyncClient, db_session: AsyncSession, finance_user_factory
) -> None:
    # A manager (ap.manage + ap.read, no ap.pay) can post a bill but not pay it.
    principal = await finance_user_factory(
        slug="ap-mgr", email="m@ap.test", keys=(FINANCE_AP_READ, FINANCE_AP_MANAGE)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "ap-mgr", "email": "m@ap.test", "password": principal.password},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    ids = await _bootstrap(db_session, principal.tenant_id)
    partner = str(uuid.uuid4())
    bill_id = (
        await client.post(
            "/api/v1/finance/vendor-bills", json=_bill_body(ids, partner), headers=_idem()
        )
    ).json()["id"]
    await client.post(
        f"/api/v1/finance/vendor-bills/{bill_id}/post",
        headers={"Idempotency-Key": "mgr-post"},
    )
    pay = await client.post(
        "/api/v1/finance/vendor-payments",
        json={
            "partner_id": partner,
            "partner_name": "Acme Supplies",
            "payment_date": "2026-03-15",
            "currency_code": "USD",
            "bank_account_id": ids["1000"],
            "amount": "100.00",
            "allocations": [{"bill_id": bill_id, "amount": "100.00"}],
        },
        headers={"Idempotency-Key": "mgr-pay"},
    )
    assert pay.status_code == 403


async def test_create_bill_is_idempotent_and_requires_key(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Regression for #88 (AP mirror): draft bill creation must carry the D-013 contract."""
    ids = await _bootstrap(db_session, await _tenant_of(finance_client))
    partner = str(uuid.uuid4())

    missing = await finance_client.post(
        "/api/v1/finance/vendor-bills", json=_bill_body(ids, partner)
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "idempotency.key_required"

    headers = {"Idempotency-Key": "bill-create-1"}
    first = await finance_client.post(
        "/api/v1/finance/vendor-bills", json=_bill_body(ids, partner), headers=headers
    )
    assert first.status_code == 201, first.text
    replay = await finance_client.post(
        "/api/v1/finance/vendor-bills", json=_bill_body(ids, partner), headers=headers
    )
    assert replay.status_code == 201
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert replay.json()["id"] == first.json()["id"]  # ONE draft document, not two

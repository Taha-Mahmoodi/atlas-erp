"""Bank reconciliation HTTP API (PLAN 4.9): import sync/202 split, reconciliation actions,
idempotency, RBAC, tenant isolation, pagination + query budgets.

Exercises the real bank_router over httpx.AsyncClient with bearer tokens. The finance_client
holds all bank permissions; narrower clients prove the per-action guards. The import and clear
endpoints carry the required Idempotency-Key (D-013); the >1000-line import asserts the
PERFORMANCE §3 202 {job_id} contract end to end (job completes, statement + all lines exist).
"""

import uuid
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs import JobStatus, wait_for_jobs
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_BANK_IMPORT,
    FINANCE_BANK_READ,
)
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from tests.conftest import assert_query_budget
from tests.modules.finance.factories import BankSetup, build_bank_setup

_CSV_HEADER = "value_date,amount,description,counterparty_ref"


def _csv(rows: list[str]) -> str:
    return "\n".join([_CSV_HEADER, *rows]) + "\n"


def _import_body(
    setup: BankSetup, rows: list[str], *, opening: str = "0.00", closing: str
) -> dict:
    return {
        "bank_account_id": str(setup.bank_account_id),
        "statement_date": "2026-03-31",
        "opening_balance": opening,
        "closing_balance": closing,
        "currency_code": "USD",
        "csv_text": _csv(rows),
        "source_filename": "march.csv",
    }


async def _tenant_of(client: AsyncClient) -> uuid.UUID:
    me = await client.get("/api/v1/auth/me")
    return uuid.UUID(me.json()["tenant_id"])


async def _bootstrap(db_session: AsyncSession, client: AsyncClient) -> BankSetup:
    return await build_bank_setup(db_session, await _tenant_of(client))


async def _post_bank_entry(
    db_session: AsyncSession, setup: BankSetup, amount: str, posting_date: date
) -> None:
    """Dr bank / Cr revenue through the real service — a match candidate."""
    with tenant_context(setup.tenant_id):
        entry = await service.create_draft_entry(
            db_session,
            setup.tenant_id,
            JournalEntryCreate(
                posting_date=posting_date,
                currency_code="USD",
                description="Bank movement",
                lines=[
                    JournalLineCreate(
                        account_id=setup.bank_account_id,
                        transaction_debit_amount=Decimal(amount),
                    ),
                    JournalLineCreate(
                        account_id=setup.accounts["4000"],
                        transaction_credit_amount=Decimal(amount),
                    ),
                ],
            ),
        )
        await service.post_entry(db_session, setup.tenant_id, entry.id)
        await db_session.commit()


# --- import: sync (201) vs background (202) -------------------------------------


async def test_small_import_returns_201_and_is_idempotent(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    setup = await _bootstrap(db_session, finance_client)
    body = _import_body(setup, ["2026-03-02,100.00,Payment,", "2026-03-05,-12.50,Fee,"],
                        closing="87.50")
    first = await finance_client.post(
        "/api/v1/finance/bank-statements", json=body, headers={"Idempotency-Key": "imp-1"}
    )
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "IMPORTED"
    assert first.json()["line_count"] == 2
    assert first.json()["import_job_id"] is None

    replay = await finance_client.post(
        "/api/v1/finance/bank-statements", json=body, headers={"Idempotency-Key": "imp-1"}
    )
    assert replay.status_code == 201
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert replay.json()["id"] == first.json()["id"]


async def test_unbalanced_and_malformed_csv_rejected_over_http(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    setup = await _bootstrap(db_session, finance_client)
    unbalanced = await finance_client.post(
        "/api/v1/finance/bank-statements",
        json=_import_body(setup, ["2026-03-02,100.00,Payment,"], closing="999.00"),
        headers={"Idempotency-Key": "imp-bad-1"},
    )
    assert unbalanced.status_code == 422
    assert unbalanced.json()["error"]["code"] == "finance.statement_unbalanced"

    malformed = await finance_client.post(
        "/api/v1/finance/bank-statements",
        json=_import_body(setup, ["2026-03-02,XX,Bad,", "nope,1.00,Bad,"], closing="0.00"),
        headers={"Idempotency-Key": "imp-bad-2"},
    )
    assert malformed.status_code == 422
    error = malformed.json()["error"]
    assert error["code"] == "finance.statement_csv_invalid"
    assert [item["row"] for item in error["details"]["row_errors"]] == [1, 2]


async def test_large_import_returns_202_job_and_imports_in_background(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    """PERFORMANCE §3: 1200 lines > the 1000 sync max -> 202 {job_id}; the job completes and
    the statement exists with ALL lines; a replayed key returns the SAME job id (D-013)."""
    setup = await _bootstrap(db_session, finance_client)
    rows = [f"2026-03-01,1.00,Line {i}," for i in range(1, 1201)]
    body = _import_body(setup, rows, closing="1200.00")

    accepted = await finance_client.post(
        "/api/v1/finance/bank-statements", json=body, headers={"Idempotency-Key": "imp-big"}
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["status"] == JobStatus.PENDING.value
    job_id = accepted.json()["job_id"]

    replay = await finance_client.post(
        "/api/v1/finance/bank-statements", json=body, headers={"Idempotency-Key": "imp-big"}
    )
    assert replay.status_code == 202
    assert replay.json()["job_id"] == job_id

    await wait_for_jobs()
    job = await finance_client.get(f"/api/v1/jobs/{job_id}")
    assert job.json()["status"] == JobStatus.COMPLETED.value
    statement_id = job.json()["result"]["statement_id"]
    assert job.json()["result"]["line_count"] == 1200

    detail = await finance_client.get(f"/api/v1/finance/bank-statements/{statement_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["line_count"] == 1200
    assert detail.json()["import_job_id"] == job_id
    assert detail.json()["progress"]["total"] == 1200
    assert detail.json()["progress"]["unmatched"] == 1200

    lines = await finance_client.get(
        f"/api/v1/finance/bank-statements/{statement_id}/lines?limit=200"
    )
    assert len(lines.json()["items"]) == 200  # paginated, hard-capped page
    assert lines.json()["next_cursor"] is not None


# --- reconciliation flow ----------------------------------------------------------


async def test_reconciliation_flow_over_http(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    """suggest -> confirm + clear -> statement RECONCILED, all over the HTTP surface."""
    setup = await _bootstrap(db_session, finance_client)
    await _post_bank_entry(db_session, setup, "100.00", date(2026, 3, 10))
    statement_id = (
        await finance_client.post(
            "/api/v1/finance/bank-statements",
            json=_import_body(
                setup,
                ["2026-03-10,100.00,Payment,", "2026-03-05,-12.50,Fee,"],
                closing="87.50",
            ),
            headers={"Idempotency-Key": "flow-imp"},
        )
    ).json()["id"]

    suggest = await finance_client.post(
        f"/api/v1/finance/bank-statements/{statement_id}/suggest-matches"
    )
    assert suggest.status_code == 200, suggest.text
    assert suggest.json() == {"suggested": 1, "unmatched": 1}

    suggested = await finance_client.get(
        f"/api/v1/finance/bank-statements/{statement_id}/lines?status=SUGGESTED"
    )
    assert len(suggested.json()["items"]) == 1
    suggested_line = suggested.json()["items"][0]
    assert suggested_line["matched_journal_line_id"] is not None

    confirm = await finance_client.post(
        f"/api/v1/finance/bank-statement-lines/{suggested_line['id']}/confirm-match"
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "MATCHED"

    unmatched = await finance_client.get(
        f"/api/v1/finance/bank-statements/{statement_id}/lines?status=UNMATCHED"
    )
    fee_line = unmatched.json()["items"][0]
    clear = await finance_client.post(
        f"/api/v1/finance/bank-statement-lines/{fee_line['id']}/clear",
        json={},
        headers={"Idempotency-Key": "flow-clear"},
    )
    assert clear.status_code == 200, clear.text
    assert clear.json()["status"] == "CLEARED"
    assert clear.json()["cleared_journal_entry_id"] is not None

    # Clear is IDEMPOTENT (D-013): the replay returns the SAME entry, no double posting.
    clear_replay = await finance_client.post(
        f"/api/v1/finance/bank-statement-lines/{fee_line['id']}/clear",
        json={},
        headers={"Idempotency-Key": "flow-clear"},
    )
    assert clear_replay.headers.get("Idempotency-Replayed") == "true"
    assert (
        clear_replay.json()["cleared_journal_entry_id"]
        == clear.json()["cleared_journal_entry_id"]
    )

    detail = await finance_client.get(f"/api/v1/finance/bank-statements/{statement_id}")
    assert detail.json()["status"] == "RECONCILED"
    assert detail.json()["progress"]["resolved"] == 2

    reject_resolved = await finance_client.post(
        f"/api/v1/finance/bank-statement-lines/{suggested_line['id']}/reject-suggestion"
    )
    assert reject_resolved.status_code == 409  # MATCHED is no longer rejectable


# --- pagination + query budgets ----------------------------------------------------


async def test_statement_lists_paginate_within_query_budget(
    finance_client: AsyncClient, db_session: AsyncSession, query_counter
) -> None:
    setup = await _bootstrap(db_session, finance_client)
    for index in range(3):
        resp = await finance_client.post(
            "/api/v1/finance/bank-statements",
            json={
                **_import_body(setup, [f"2026-03-0{index + 1},10.00,Pay {index},"],
                               closing="10.00"),
                "statement_date": f"2026-03-0{index + 1}",
            },
            headers={"Idempotency-Key": f"page-imp-{index}"},
        )
        assert resp.status_code == 201, resp.text

    first_page = await finance_client.get("/api/v1/finance/bank-statements?limit=2")
    assert len(first_page.json()["items"]) == 2
    cursor = first_page.json()["next_cursor"]
    assert cursor is not None
    second_page = await finance_client.get(
        f"/api/v1/finance/bank-statements?limit=2&cursor={cursor}"
    )
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["next_cursor"] is None

    statement_id = first_page.json()["items"][0]["id"]
    await assert_query_budget(
        finance_client, query_counter, "/api/v1/finance/bank-statements?limit=2"
    )
    await assert_query_budget(
        finance_client,
        query_counter,
        f"/api/v1/finance/bank-statements/{statement_id}/lines",
    )
    # Detail = user + statement + refresh + progress count.
    await assert_query_budget(
        finance_client,
        query_counter,
        f"/api/v1/finance/bank-statements/{statement_id}",
        budget=4,
    )


# --- RBAC + tenant isolation --------------------------------------------------------


async def _narrow_client(
    client: AsyncClient, finance_user_factory, slug: str, email: str, keys: tuple[str, ...]
):
    principal = await finance_user_factory(slug=slug, email=email, keys=keys)
    login = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": slug, "email": email, "password": principal.password},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return principal


async def test_import_requires_bank_import_permission(
    client: AsyncClient, db_session: AsyncSession, finance_user_factory
) -> None:
    principal = await _narrow_client(
        client, finance_user_factory, "bank-reader", "r@bank.test", (FINANCE_BANK_READ,)
    )
    setup = await build_bank_setup(db_session, principal.tenant_id)
    resp = await client.post(
        "/api/v1/finance/bank-statements",
        json=_import_body(setup, ["2026-03-02,1.00,Tiny,"], closing="1.00"),
        headers={"Idempotency-Key": "rbac-imp"},
    )
    assert resp.status_code == 403


async def test_reconcile_actions_require_bank_reconcile_permission(
    client: AsyncClient, db_session: AsyncSession, finance_user_factory
) -> None:
    # An importer (read + import, no reconcile) can import but not suggest/confirm/clear.
    principal = await _narrow_client(
        client,
        finance_user_factory,
        "bank-importer",
        "i@bank.test",
        (FINANCE_BANK_READ, FINANCE_BANK_IMPORT),
    )
    setup = await build_bank_setup(db_session, principal.tenant_id)
    statement = await client.post(
        "/api/v1/finance/bank-statements",
        json=_import_body(setup, ["2026-03-02,1.00,Tiny,"], closing="1.00"),
        headers={"Idempotency-Key": "rbac-imp-2"},
    )
    assert statement.status_code == 201, statement.text
    statement_id = statement.json()["id"]
    line_id = (
        await client.get(f"/api/v1/finance/bank-statements/{statement_id}/lines")
    ).json()["items"][0]["id"]

    suggest = await client.post(
        f"/api/v1/finance/bank-statements/{statement_id}/suggest-matches"
    )
    assert suggest.status_code == 403
    clear = await client.post(
        f"/api/v1/finance/bank-statement-lines/{line_id}/clear",
        json={},
        headers={"Idempotency-Key": "rbac-clear"},
    )
    assert clear.status_code == 403


async def test_statements_are_tenant_isolated_over_http(
    client: AsyncClient, finance_client: AsyncClient, db_session: AsyncSession,
    finance_user_factory,
) -> None:
    setup = await _bootstrap(db_session, finance_client)
    statement_id = (
        await finance_client.post(
            "/api/v1/finance/bank-statements",
            json=_import_body(setup, ["2026-03-02,1.00,Tiny,"], closing="1.00"),
            headers={"Idempotency-Key": "iso-imp"},
        )
    ).json()["id"]

    await _narrow_client(
        client,
        finance_user_factory,
        "bank-other",
        "o@bank.test",
        (FINANCE_BANK_READ, FINANCE_BANK_IMPORT),
    )
    foreign_detail = await client.get(f"/api/v1/finance/bank-statements/{statement_id}")
    assert foreign_detail.status_code == 404
    foreign_lines = await client.get(
        f"/api/v1/finance/bank-statements/{statement_id}/lines"
    )
    assert foreign_lines.status_code == 404
    own_list = await client.get("/api/v1/finance/bank-statements")
    assert own_list.json()["items"] == []

"""Unrealized-FX revaluation run with auto-reversal + re-run (D-019), SQLite.

Proves: a foreign monetary balance revalues at the CLOSING rate and posts a BALANCED FX_REVAL
entry plus its next-period auto-reversal; the next-period-not-open precondition raises 422 up
front before any entry posts; a re-run reverses the prior run then reposts; runs are tracked in
fin_fx_revaluation_runs and the adjustment/reversal pair is docflow-linked; and RBAC on
finance.fx.revalue.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.docflow import get_document_chain
from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.jobs import JobStatus, wait_for_jobs
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import DocumentType, EntryStatus, FxRunStatus
from app.modules.finance.models import FxRevaluationRun, JournalEntry, JournalLine
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from tests.conftest import assert_query_budget
from tests.modules.finance.conftest import FxSetup

# A EUR entry posted mid-March gives the EUR bank a 100 EUR foreign balance carried at the
# 2026-03-01 SPOT rate of 1.20 -> 120.00 USD functional.
_POST_DATE = date(2026, 3, 15)
_RATE_DATE = date(2026, 3, 31)  # March period end; CLOSING rate 1.25
_NEXT_PERIOD_START = date(2026, 4, 1)


async def _post_eur_balance(
    session: AsyncSession, fx_setup: FxSetup, amount: str = "100.00"
) -> None:
    """Post a balanced EUR entry (Dr EUR-bank / Cr Sales) so the EUR bank carries a foreign bal."""
    with tenant_context(fx_setup.tenant_id):
        entry = await service.create_draft_entry(
            session,
            fx_setup.tenant_id,
            JournalEntryCreate(
                posting_date=_POST_DATE,
                currency_code="EUR",
                lines=[
                    JournalLineCreate(
                        account_id=fx_setup.eur_bank_id,
                        transaction_debit_amount=Decimal(amount),
                    ),
                    JournalLineCreate(
                        account_id=fx_setup.accounts["4000"],
                        transaction_credit_amount=Decimal(amount),
                    ),
                ],
            ),
        )
        await session.commit()
        await run_in_uow(
            session, lambda: service.post_entry(session, fx_setup.tenant_id, entry.id)
        )


async def _march_period_id(session: AsyncSession, fx_setup: FxSetup):
    with tenant_context(fx_setup.tenant_id):
        periods = (
            await service.list_fiscal_periods(
                session, fx_setup.tenant_id, fx_setup.fiscal_year_id
            )
        ).items
    return next(p.id for p in periods if p.start_date == date(2026, 3, 1))


async def _fx_reval_entries(session: AsyncSession, fx_setup: FxSetup) -> list[JournalEntry]:
    with tenant_context(fx_setup.tenant_id):
        return list(
            (
                await session.execute(
                    select(JournalEntry)
                    .where(JournalEntry.document_type == DocumentType.FX_REVAL.value)
                    .order_by(JournalEntry.posting_date, JournalEntry.entry_number)
                )
            ).scalars().all()
        )


async def test_revaluation_posts_adjustment_and_auto_reversal(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    await _post_eur_balance(db_session, fx_setup)
    period_id = await _march_period_id(db_session, fx_setup)

    with tenant_context(fx_setup.tenant_id):
        await run_in_uow(
            db_session,
            lambda: service.run_fx_revaluation(
                db_session, fx_setup.tenant_id, period_id, _RATE_DATE
            ),
        )

    entries = await _fx_reval_entries(db_session, fx_setup)
    # One adjustment (dated 2026-03-31) + one auto-reversal (dated 2026-04-01).
    assert len(entries) == 2
    adjustment = next(e for e in entries if e.posting_date == _RATE_DATE)
    reversal = next(e for e in entries if e.posting_date == _NEXT_PERIOD_START)
    assert adjustment.status == EntryStatus.POSTED.value
    assert reversal.status == EntryStatus.POSTED.value

    # delta = 100 EUR @ CLOSING 1.25 (125.00 USD) - carrying 120.00 USD = +5.00 USD gain.
    with tenant_context(fx_setup.tenant_id):
        adj_lines = list(
            (
                await db_session.execute(
                    select(JournalLine).where(JournalLine.journal_entry_id == adjustment.id)
                )
            ).scalars().all()
        )
    func_debit = sum((line.functional_debit_amount for line in adj_lines), Decimal(0))
    func_credit = sum((line.functional_credit_amount for line in adj_lines), Decimal(0))
    assert func_debit == func_credit == Decimal("5.00")  # balanced FX_REVAL entry
    # The gain credits the fx_unrealized_gain account (7200) and debits the adjustment (1900).
    gain_line = next(line for line in adj_lines if line.functional_credit_amount > 0)
    assert gain_line.account_id == fx_setup.accounts["7200"]


async def test_revaluation_pair_is_docflow_linked(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    await _post_eur_balance(db_session, fx_setup)
    period_id = await _march_period_id(db_session, fx_setup)
    with tenant_context(fx_setup.tenant_id):
        await run_in_uow(
            db_session,
            lambda: service.run_fx_revaluation(
                db_session, fx_setup.tenant_id, period_id, _RATE_DATE
            ),
        )
    entries = await _fx_reval_entries(db_session, fx_setup)
    adjustment = next(e for e in entries if e.posting_date == _RATE_DATE)
    with tenant_context(fx_setup.tenant_id):
        chain = await get_document_chain(
            db_session, fx_setup.tenant_id, adjustment.document_id
        )
    # The adjustment and its auto-reversal are linked with a 'revalues' docflow edge (D-019).
    assert len(chain.nodes) == 2
    assert any(edge.link_type == "revalues" for edge in chain.edges)


async def test_revaluation_tracks_run_completed(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    await _post_eur_balance(db_session, fx_setup)
    period_id = await _march_period_id(db_session, fx_setup)
    with tenant_context(fx_setup.tenant_id):
        await run_in_uow(
            db_session,
            lambda: service.run_fx_revaluation(
                db_session, fx_setup.tenant_id, period_id, _RATE_DATE
            ),
        )
        runs = list(
            (await db_session.execute(select(FxRevaluationRun))).scalars().all()
        )
    assert len(runs) == 1
    assert runs[0].status == FxRunStatus.COMPLETED.value
    assert runs[0].fiscal_period_id == period_id


async def test_next_period_not_open_raises_422_up_front(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    await _post_eur_balance(db_session, fx_setup)
    period_id = await _march_period_id(db_session, fx_setup)
    # Close April (the next period); the run must refuse before posting anything.
    with tenant_context(fx_setup.tenant_id):
        periods = (
            await service.list_fiscal_periods(
                db_session, fx_setup.tenant_id, fx_setup.fiscal_year_id
            )
        ).items
        april = next(p for p in periods if p.start_date == _NEXT_PERIOD_START)
        await service.close_period(db_session, fx_setup.tenant_id, april.id)
        await db_session.commit()
        with pytest.raises(ValidationFailedError) as exc:
            await service.run_fx_revaluation(
                db_session, fx_setup.tenant_id, period_id, _RATE_DATE
            )
    assert exc.value.code == "finance.fx_reval_next_period_not_open"
    # No FX_REVAL entry was posted (fail up front).
    assert await _fx_reval_entries(db_session, fx_setup) == []


async def test_rerun_reverses_prior_then_reposts(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    await _post_eur_balance(db_session, fx_setup)
    period_id = await _march_period_id(db_session, fx_setup)
    with tenant_context(fx_setup.tenant_id):
        await run_in_uow(
            db_session,
            lambda: service.run_fx_revaluation(
                db_session, fx_setup.tenant_id, period_id, _RATE_DATE
            ),
        )
        await run_in_uow(
            db_session,
            lambda: service.run_fx_revaluation(
                db_session, fx_setup.tenant_id, period_id, _RATE_DATE
            ),
        )
        runs = list(
            (
                await db_session.execute(
                    select(FxRevaluationRun).order_by(FxRevaluationRun.created_at)
                )
            ).scalars().all()
        )
    # Two runs: the first is REVERSED, the second is COMPLETED (append-only re-run).
    assert len(runs) == 2
    assert runs[0].status == FxRunStatus.REVERSED.value
    assert runs[1].status == FxRunStatus.COMPLETED.value
    # The fresh run's adjustment still nets the same +5.00 USD (the balance is read clean each run
    # because adjustments post to the adjustment account, not the revalued EUR bank).
    entries = await _fx_reval_entries(db_session, fx_setup)
    fresh = [e for e in entries if e.status == EntryStatus.POSTED.value]
    assert any(e.posting_date == _RATE_DATE for e in fresh)


async def test_rerun_leaves_other_periods_revaluations_untouched(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    """Regression for #71: re-running ONE period used to reverse every still-posted FX_REVAL
    entry tenant-wide, silently wiping other periods' active revaluations while their run rows
    stayed COMPLETED."""
    from app.modules.finance.constants import RateKind

    april_rate_date = date(2026, 4, 30)
    await _post_eur_balance(db_session, fx_setup)
    march_id = await _march_period_id(db_session, fx_setup)
    with tenant_context(fx_setup.tenant_id):
        await service.create_exchange_rate(
            db_session,
            fx_setup.tenant_id,
            rate_date=april_rate_date,
            from_currency_code="EUR",
            to_currency_code="USD",
            rate=Decimal("1.30"),
            rate_type=RateKind.CLOSING,
        )
        await db_session.commit()
        periods = (
            await service.list_fiscal_periods(
                db_session, fx_setup.tenant_id, fx_setup.fiscal_year_id
            )
        ).items
        april_id = next(p.id for p in periods if p.start_date == _NEXT_PERIOD_START)
        for period_id, rate_date in ((march_id, _RATE_DATE), (april_id, april_rate_date)):
            await run_in_uow(
                db_session,
                lambda pid=period_id, rd=rate_date: service.run_fx_revaluation(
                    db_session, fx_setup.tenant_id, pid, rd
                ),
            )
        # Re-run March only.
        await run_in_uow(
            db_session,
            lambda: service.run_fx_revaluation(
                db_session, fx_setup.tenant_id, march_id, _RATE_DATE
            ),
        )
        runs = list(
            (
                await db_session.execute(
                    select(FxRevaluationRun).order_by(FxRevaluationRun.created_at)
                )
            ).scalars().all()
        )
    # April's run row is still COMPLETED and — the bug — its entries must still be POSTED.
    april_runs = [r for r in runs if r.fiscal_period_id == april_id]
    assert [r.status for r in april_runs] == [FxRunStatus.COMPLETED.value]
    entries = await _fx_reval_entries(db_session, fx_setup)
    april_pair = [
        e
        for e in entries
        if e.posting_date in (april_rate_date, date(2026, 5, 1))
        and e.reverses_entry_id is None
    ]
    assert len(april_pair) == 2
    assert all(e.status == EntryStatus.POSTED.value for e in april_pair)
    # And March really was re-run: its first run row is REVERSED, its second COMPLETED.
    march_runs = [r for r in runs if r.fiscal_period_id == march_id]
    assert [r.status for r in march_runs] == [
        FxRunStatus.REVERSED.value,
        FxRunStatus.COMPLETED.value,
    ]


async def test_revaluation_with_no_foreign_balance_posts_nothing(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    # No EUR entry posted -> the EUR bank has a zero foreign balance -> no FX_REVAL entry.
    period_id = await _march_period_id(db_session, fx_setup)
    with tenant_context(fx_setup.tenant_id):
        await run_in_uow(
            db_session,
            lambda: service.run_fx_revaluation(
                db_session, fx_setup.tenant_id, period_id, _RATE_DATE
            ),
        )
    assert await _fx_reval_entries(db_session, fx_setup) == []


# --- RBAC ----------------------------------------------------------------------


async def test_fx_revalue_required_to_run(client, finance_user_factory) -> None:
    """A principal lacking finance.fx.revalue may not run a revaluation (403)."""
    import uuid

    from app.modules.finance.constants import FINANCE_FX_MANAGE

    principal = await finance_user_factory(
        slug="norev-acme", email="norev@acme.test", keys=(FINANCE_FX_MANAGE,)
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
    forbidden = await client.post(
        "/api/v1/finance/fx-revaluation-runs",
        headers={"Idempotency-Key": "reval-rbac"},
        json={"fiscal_period_id": str(uuid.uuid4()), "rate_date": _RATE_DATE.isoformat()},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "rbac.permission_denied"


async def test_run_revaluation_via_api_returns_202_and_polls_to_completion(
    finance_client,
) -> None:
    """The #26 contract end-to-end: POST /fx-revaluation-runs returns 202 {job_id, PENDING};
    a D-013 replay of the same Idempotency-Key returns the SAME job id (no second run); the
    job completes in the background and GET /api/v1/jobs/{id} returns COMPLETED with the run
    id in its result — the business outcome (one COMPLETED run row) is unchanged."""
    # Functional currency + a fiscal year (the run needs an open next period).
    assert (
        await finance_client.post(
            "/api/v1/finance/currencies",
            json={"code": "USD", "name": "US Dollar", "is_functional": True},
        )
    ).status_code == 201
    fy = await finance_client.post(
        "/api/v1/finance/fiscal-years",
        json={"code": "2026", "name": "FY2026", "start_date": "2026-01-01"},
    )
    assert fy.status_code == 201
    periods = (await finance_client.get("/api/v1/finance/fiscal-periods")).json()["items"]
    march = next(p for p in periods if p["start_date"] == "2026-03-01")

    body = {"fiscal_period_id": march["id"], "rate_date": "2026-03-31"}
    first = await finance_client.post(
        "/api/v1/finance/fx-revaluation-runs",
        headers={"Idempotency-Key": "reval-api-1"},
        json=body,
    )
    assert first.status_code == 202, first.text
    assert first.json()["status"] == JobStatus.PENDING.value
    job_id = first.json()["job_id"]
    # A retry with the SAME key replays the stored 202 — same job id, no second submission.
    replay = await finance_client.post(
        "/api/v1/finance/fx-revaluation-runs",
        headers={"Idempotency-Key": "reval-api-1"},
        json=body,
    )
    assert replay.status_code == 202
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert replay.json()["job_id"] == job_id

    await wait_for_jobs()
    job = await finance_client.get(f"/api/v1/jobs/{job_id}")
    assert job.status_code == 200, job.text
    assert job.json()["status"] == JobStatus.COMPLETED.value
    assert job.json()["result"]["status"] == FxRunStatus.COMPLETED.value

    runs = (await finance_client.get("/api/v1/finance/fx-revaluation-runs")).json()
    assert len(runs["items"]) == 1
    assert runs["items"][0]["id"] == job.json()["result"]["run_id"]
    assert runs["items"][0]["status"] == FxRunStatus.COMPLETED.value


async def test_revaluation_runs_list_query_count(finance_client, query_counter) -> None:
    """PERFORMANCE §2: the warm-path GET /fx-revaluation-runs runs ≤3 SQL statements."""
    assert (
        await finance_client.post(
            "/api/v1/finance/currencies",
            json={"code": "USD", "name": "US Dollar", "is_functional": True},
        )
    ).status_code == 201
    fy = await finance_client.post(
        "/api/v1/finance/fiscal-years",
        json={"code": "2026", "name": "FY2026", "start_date": "2026-01-01"},
    )
    assert fy.status_code == 201
    periods = (await finance_client.get("/api/v1/finance/fiscal-periods")).json()["items"]
    march = next(p for p in periods if p["start_date"] == "2026-03-01")
    run = await finance_client.post(
        "/api/v1/finance/fx-revaluation-runs",
        headers={"Idempotency-Key": "reval-qc"},
        json={"fiscal_period_id": march["id"], "rate_date": "2026-03-31"},
    )
    assert run.status_code == 202, run.text
    await wait_for_jobs()  # let the background run land so the list has a row (#26)
    await assert_query_budget(
        finance_client, query_counter, "/api/v1/finance/fx-revaluation-runs"
    )

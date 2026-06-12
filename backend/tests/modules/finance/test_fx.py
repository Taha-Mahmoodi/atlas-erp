"""Multi-currency rate lookup, posting-time translation, and posting-defaults (D-019), SQLite.

Proves: get_rate (direct/same-currency/most-recent/inverse/missing -> 422); a foreign-currency
entry translates functional amounts at the SPOT rate with functional debits == credits EXACTLY
(residual absorbed); an explicit rate override beats the looked-up rate; posting-defaults get/set +
missing -> clear error; and RBAC on finance.fx.manage. The DB balance trigger firing on the
translated functional sums is proven on both engines in test_fx_db_guards.py.
"""

from collections.abc import AsyncIterator, Callable
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import (
    FX_REVALUATION_ADJUSTMENT,
    FX_UNREALIZED_GAIN,
    RateKind,
)
from app.modules.finance.models import JournalLine
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from tests.modules.finance.conftest import FinancePrincipal, FxSetup

_PD = date(2026, 3, 15)  # inside the open 2026 fiscal year


# --- get_rate -----------------------------------------------------------------


async def test_get_rate_direct_pair(db_session: AsyncSession, fx_setup: FxSetup) -> None:
    with tenant_context(fx_setup.tenant_id):
        rate = await service.get_rate(
            db_session, fx_setup.tenant_id, "EUR", "USD", _PD, RateKind.SPOT
        )
    # Most recent SPOT rate on or before 2026-03-15 is the 2026-03-01 rate of 1.20.
    assert rate == Decimal("1.20")


async def test_get_rate_same_currency_is_one(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    with tenant_context(fx_setup.tenant_id):
        rate = await service.get_rate(db_session, fx_setup.tenant_id, "USD", "USD", _PD)
    assert rate == Decimal(1)


async def test_get_rate_most_recent_on_or_before(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    # On 2026-02-15 the latest rate is the 2026-01-01 one (1.10), not the later 2026-03-01 one.
    with tenant_context(fx_setup.tenant_id):
        rate = await service.get_rate(
            db_session, fx_setup.tenant_id, "EUR", "USD", date(2026, 2, 15), RateKind.SPOT
        )
    assert rate == Decimal("1.10")


async def test_get_rate_inverse_pair_computed(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    # No USD->EUR direct rate exists; get_rate returns 1 / (EUR->USD) rounded to 10 dp.
    with tenant_context(fx_setup.tenant_id):
        rate = await service.get_rate(
            db_session, fx_setup.tenant_id, "USD", "EUR", _PD, RateKind.SPOT
        )
    assert rate == (Decimal(1) / Decimal("1.20")).quantize(Decimal("1.0000000000"))


async def test_get_rate_missing_raises_422(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    with tenant_context(fx_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.get_rate(db_session, fx_setup.tenant_id, "EUR", "GBP", _PD)
    assert exc.value.code == "finance.exchange_rate_missing"
    assert exc.value.status_code == 422


async def test_functional_currency_resolves(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    with tenant_context(fx_setup.tenant_id):
        assert await service.functional_currency(db_session, fx_setup.tenant_id) == "USD"


# --- posting-time translation -------------------------------------------------


def _eur_payload(fx_setup: FxSetup, amount: str = "100.00") -> JournalEntryCreate:
    """A balanced EUR entry Dr EUR-bank / Cr Sales."""
    return JournalEntryCreate(
        posting_date=_PD,
        currency_code="EUR",
        description="EUR entry",
        lines=[
            JournalLineCreate(
                account_id=fx_setup.eur_bank_id, transaction_debit_amount=Decimal(amount)
            ),
            JournalLineCreate(
                account_id=fx_setup.accounts["4000"], transaction_credit_amount=Decimal(amount)
            ),
        ],
    )


async def _lines(session: AsyncSession, entry_id) -> list[JournalLine]:
    return list(
        (
            await session.execute(
                select(JournalLine)
                .where(JournalLine.journal_entry_id == entry_id)
                .order_by(JournalLine.line_number)
            )
        ).scalars().all()
    )


async def test_foreign_entry_translates_at_spot_and_balances(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    with tenant_context(fx_setup.tenant_id):
        entry = await service.create_draft_entry(
            db_session, fx_setup.tenant_id, _eur_payload(fx_setup, "100.00")
        )
        await db_session.commit()
        await run_in_uow(
            db_session,
            lambda: service.post_entry(db_session, fx_setup.tenant_id, entry.id),
        )
        lines = await _lines(db_session, entry.id)

    # SPOT rate on 2026-03-15 is 1.20: 100 EUR -> 120.00 USD functional on each side.
    debit_line = next(line for line in lines if line.transaction_debit_amount > 0)
    credit_line = next(line for line in lines if line.transaction_credit_amount > 0)
    assert debit_line.functional_debit_amount == Decimal("120.00")
    assert credit_line.functional_credit_amount == Decimal("120.00")
    # Transaction amounts are unchanged (still EUR).
    assert debit_line.transaction_debit_amount == Decimal("100.00")
    # Functional debits == functional credits exactly (the balance trigger passed at post).
    func_debit = sum((line.functional_debit_amount for line in lines), Decimal(0))
    func_credit = sum((line.functional_credit_amount for line in lines), Decimal(0))
    assert func_debit == func_credit


async def test_foreign_translation_absorbs_residual_cent(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    # A 3-line entry where the rate produces a rounding residual: 33.33 EUR three ways at 1.20.
    # Dr EUR-bank 100.00; Cr Sales 33.33 + 33.33 + 33.34 -> functional sides must still tie.
    payload = JournalEntryCreate(
        posting_date=_PD,
        currency_code="EUR",
        lines=[
            JournalLineCreate(
                account_id=fx_setup.eur_bank_id, transaction_debit_amount=Decimal("100.00")
            ),
            JournalLineCreate(
                account_id=fx_setup.accounts["4000"], transaction_credit_amount=Decimal("33.33")
            ),
            JournalLineCreate(
                account_id=fx_setup.accounts["4000"], transaction_credit_amount=Decimal("33.33")
            ),
            JournalLineCreate(
                account_id=fx_setup.accounts["4000"], transaction_credit_amount=Decimal("33.34")
            ),
        ],
    )
    with tenant_context(fx_setup.tenant_id):
        entry = await service.create_draft_entry(db_session, fx_setup.tenant_id, payload)
        await db_session.commit()
        await run_in_uow(
            db_session,
            lambda: service.post_entry(db_session, fx_setup.tenant_id, entry.id),
        )
        lines = await _lines(db_session, entry.id)
    func_debit = sum((line.functional_debit_amount for line in lines), Decimal(0))
    func_credit = sum((line.functional_credit_amount for line in lines), Decimal(0))
    assert func_debit == func_credit  # residual cent absorbed; no separate line, no imbalance
    assert func_debit == Decimal("120.00")  # 100 EUR @ 1.20


async def test_explicit_rate_override_beats_lookup(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    with tenant_context(fx_setup.tenant_id):
        entry = await service.create_draft_entry(
            db_session, fx_setup.tenant_id, _eur_payload(fx_setup, "100.00")
        )
        await db_session.commit()
        await run_in_uow(
            db_session,
            lambda: service.post_entry(
                db_session, fx_setup.tenant_id, entry.id, rate_override=Decimal("1.50")
            ),
        )
        lines = await _lines(db_session, entry.id)
    # The override 1.50 is used instead of the looked-up SPOT 1.20: 100 EUR -> 150.00 USD.
    debit_line = next(line for line in lines if line.transaction_debit_amount > 0)
    assert debit_line.functional_debit_amount == Decimal("150.00")


# --- posting defaults ---------------------------------------------------------


async def test_get_posting_default_resolves(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    with tenant_context(fx_setup.tenant_id):
        account_id = await service.get_posting_default(
            db_session, fx_setup.tenant_id, FX_UNREALIZED_GAIN
        )
    assert account_id == fx_setup.accounts["7200"]


async def test_get_posting_default_unmapped_raises(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    # The realized-gain default is mapped, but a never-set purpose is missing here: remove one.
    with tenant_context(fx_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.get_posting_default(db_session, fx_setup.tenant_id, "fx_does_not_exist")
    assert exc.value.code == "finance.posting_default_unmapped"


async def test_set_posting_default_rejects_unknown_purpose(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    with tenant_context(fx_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.set_posting_default(
            db_session, fx_setup.tenant_id, "made_up", fx_setup.accounts["1000"]
        )
    assert exc.value.code == "finance.posting_default_unknown_purpose"


async def test_set_posting_default_remaps(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    with tenant_context(fx_setup.tenant_id):
        await service.set_posting_default(
            db_session, fx_setup.tenant_id, FX_REVALUATION_ADJUSTMENT, fx_setup.accounts["1000"]
        )
        await db_session.commit()
        remapped = await service.get_posting_default(
            db_session, fx_setup.tenant_id, FX_REVALUATION_ADJUSTMENT
        )
    assert remapped == fx_setup.accounts["1000"]


# --- one-functional-currency invariant ----------------------------------------


async def test_second_functional_currency_refused(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    from app.core.exceptions import ConflictError

    with tenant_context(fx_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.create_currency(
            db_session, fx_setup.tenant_id, code="GBP", name="Pound", is_functional=True
        )
    assert exc.value.code == "finance.functional_currency_exists"


# --- RBAC ---------------------------------------------------------------------


async def test_fx_manage_required_to_create_currency(
    client: AsyncClient,
    finance_user_factory: Callable[..., "AsyncIterator[FinancePrincipal]"],
) -> None:
    from app.modules.finance.constants import FINANCE_ACCOUNT_READ

    principal = await finance_user_factory(
        slug="fxro-acme", email="fxro@acme.test", keys=(FINANCE_ACCOUNT_READ,)
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
        "/api/v1/finance/currencies", json={"code": "USD", "name": "US Dollar"}
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "rbac.permission_denied"


async def test_fx_create_currency_and_rate_via_api(
    finance_client: AsyncClient,
) -> None:
    created = await finance_client.post(
        "/api/v1/finance/currencies",
        json={"code": "USD", "name": "US Dollar", "is_functional": True},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_functional"] is True
    rate = await finance_client.post(
        "/api/v1/finance/exchange-rates",
        json={
            "rate_date": "2026-03-01",
            "from_currency_code": "EUR",
            "to_currency_code": "USD",
            "rate_type": "SPOT",
            "rate": "1.20",
        },
    )
    assert rate.status_code == 201, rate.text
    listed = await finance_client.get("/api/v1/finance/exchange-rates")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

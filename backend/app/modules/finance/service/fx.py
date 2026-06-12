"""FX rate lookup, currency management, posting-default wiring, and translation (D-019).

The contract is strict: postings NEVER guess a rate. ``get_rate`` returns the most recent rate
with ``rate_date <= on_date`` for the exact (from, to, rate_type) pair; same-currency is 1; a
missing rate is a hard 422 (``finance.exchange_rate_missing``). Inverse handling is documented and
deterministic: if the direct pair has no rate but the INVERSE pair does, ``get_rate`` returns
``1 / inverse_rate`` rounded to 10 dp (the RateType scale) — direct-or-inverse, never triangulated
through a third currency (v1 has one functional currency; direct/inverse pairs suffice, D-019).

``translate`` is the single posting-boundary conversion: ``quantize(amount × rate, to_decimals)``
HALF_UP via core/money — the same rounding the journal uses, so functional amounts are exact and
the balance trigger's SUM holds on both engines.

``get_posting_default`` resolves a purpose string (e.g. ``'fx_unrealized_gain'``) to a configured
account, raising a clear 422 when unmapped — the data-driven account wiring D-019 references
(reused later by AP/AR and inventory COGS). ``set_functional_currency`` enforces the
one-functional-currency-per-tenant invariant at the service layer (the partial unique index
backstops it at the DB).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.money import quantize_money
from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.finance.constants import RateKind
from app.modules.finance.models import Currency, ExchangeRate

# RateType stores 10 fractional digits (D-015); an inverse rate is rounded to that scale.
_RATE_DECIMALS = 10
_RATE_QUANTUM = Decimal(1).scaleb(-_RATE_DECIMALS)


async def functional_currency_or_none(
    session: AsyncSession, tenant_id: uuid.UUID
) -> str | None:
    """The tenant's functional currency code, or None when unconfigured (D-019). The journal's
    posting-time translation uses this: a tenant with no functional currency is the v1
    single-currency default (functional == transaction), so translation is skipped rather than
    failing — multi-currency is opt-in by configuring a functional currency."""
    return (
        await session.execute(
            select(Currency.code).where(
                Currency.tenant_id == tenant_id, Currency.is_functional.is_(True)
            )
        )
    ).scalar_one_or_none()


async def functional_currency(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    """The tenant's functional (reporting) currency code (D-019). Raises a clear 422 if the
    tenant has no functional currency configured — the revaluation run and explicit FX flows
    cannot proceed without one, and fail-loud is the D-019 stance (postings never guess)."""
    code = await functional_currency_or_none(session, tenant_id)
    if code is None:
        raise ValidationFailedError(
            message="No functional currency is configured for this tenant",
            code="finance.functional_currency_missing",
        )
    return code


async def _latest_rate(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    from_code: str,
    to_code: str,
    on_date: date,
    rate_type: RateKind,
) -> Decimal | None:
    """The most recent ``rate`` for the exact (from, to, rate_type) pair with
    ``rate_date <= on_date``, or None if none exists. One indexed query (the lookup index)."""
    stmt = (
        select(ExchangeRate.rate)
        .where(
            ExchangeRate.tenant_id == tenant_id,
            ExchangeRate.from_currency_code == from_code,
            ExchangeRate.to_currency_code == to_code,
            ExchangeRate.rate_type == rate_type.value,
            ExchangeRate.rate_date <= on_date,
        )
        .order_by(ExchangeRate.rate_date.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_rate(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    from_code: str,
    to_code: str,
    on_date: date,
    rate_type: RateKind = RateKind.SPOT,
) -> Decimal:
    """The rate to convert one unit of ``from_code`` into ``to_code`` on ``on_date`` (D-019).

    - ``from == to`` -> ``Decimal(1)`` (no rate row needed).
    - else the most recent DIRECT rate with ``rate_date <= on_date`` for the pair + type.
    - else, if only the INVERSE pair is stored, ``1 / inverse_rate`` rounded to 10 dp (documented
      inverse handling — direct-or-inverse, never triangulated).
    - else MissingExchangeRateError (``finance.exchange_rate_missing``, 422): postings never guess.

    ``rate_type`` accepts a RateKind or its string value (ApiModel serializes enums to strings).
    """
    rate_type = RateKind(rate_type)
    if from_code == to_code:
        return Decimal(1)

    direct = await _latest_rate(session, tenant_id, from_code, to_code, on_date, rate_type)
    if direct is not None:
        return direct

    inverse = await _latest_rate(session, tenant_id, to_code, from_code, on_date, rate_type)
    if inverse is not None and inverse != 0:
        return (Decimal(1) / inverse).quantize(_RATE_QUANTUM, rounding=ROUND_HALF_UP)

    raise ValidationFailedError(
        message=(
            f"No {rate_type.value} exchange rate from {from_code} to {to_code} "
            f"on or before {on_date.isoformat()}"
        ),
        code="finance.exchange_rate_missing",
        details={
            "from_currency_code": from_code,
            "to_currency_code": to_code,
            "rate_type": rate_type.value,
            "on_date": on_date.isoformat(),
        },
    )


def translate(amount: Decimal, rate: Decimal, to_decimals: int) -> Decimal:
    """Convert ``amount`` at ``rate`` and quantize to ``to_decimals`` HALF_UP (D-019). This is the
    posting-boundary conversion — same rounding as the journal, so functional amounts are exact."""
    return quantize_money(amount * rate, to_decimals)


# --- Exchange-rate management (D-019) -----------------------------------------


async def create_exchange_rate(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    rate_date: date,
    from_currency_code: str,
    to_currency_code: str,
    rate: Decimal,
    rate_type: RateKind = RateKind.SPOT,
) -> ExchangeRate:
    """Insert an exchange rate (D-019). A duplicate (date, from, to, type) is a ConflictError (the
    DB UNIQUE backstops). Rates keep full RateType precision; no quantization. ``rate_type`` accepts
    a RateKind or its string value (ApiModel serializes enums to strings)."""
    rate_type = RateKind(rate_type)
    existing = (
        await session.execute(
            select(ExchangeRate).where(
                ExchangeRate.tenant_id == tenant_id,
                ExchangeRate.rate_date == rate_date,
                ExchangeRate.from_currency_code == from_currency_code,
                ExchangeRate.to_currency_code == to_currency_code,
                ExchangeRate.rate_type == rate_type.value,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            message="An exchange rate for this pair, type and date already exists",
            code="finance.exchange_rate_conflict",
        )
    row = ExchangeRate(
        tenant_id=tenant_id,
        rate_date=rate_date,
        from_currency_code=from_currency_code,
        to_currency_code=to_currency_code,
        rate_type=rate_type.value,
        rate=rate,
    )
    session.add(row)
    await session.flush()
    return row


async def list_exchange_rates(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
    from_currency_code: str | None = None,
    to_currency_code: str | None = None,
    rate_type: RateKind | None = None,
) -> Page[ExchangeRate]:
    """Keyset-paginated rate list, newest rate_date first (D-014). Filters fold into the cursor
    fingerprint so a cursor cannot cross filtered views."""
    stmt = select(ExchangeRate).where(ExchangeRate.tenant_id == tenant_id)
    if from_currency_code is not None:
        stmt = stmt.where(ExchangeRate.from_currency_code == from_currency_code)
    if to_currency_code is not None:
        stmt = stmt.where(ExchangeRate.to_currency_code == to_currency_code)
    if rate_type is not None:
        stmt = stmt.where(ExchangeRate.rate_type == RateKind(rate_type).value)
    return await paginate(
        session,
        stmt,
        order_by=[
            OrderKey(ExchangeRate.rate_date, SortDirection.DESC),
            OrderKey(ExchangeRate.created_at, SortDirection.DESC),
        ],
        pk=ExchangeRate.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(from_currency_code, to_currency_code, rate_type),
    )


# --- Currency management (D-019) ----------------------------------------------


async def get_currency(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> Currency:
    currency = (
        await session.execute(
            select(Currency).where(Currency.tenant_id == tenant_id, Currency.code == code)
        )
    ).scalar_one_or_none()
    if currency is None:
        raise NotFoundError(message="Currency not found", code="finance.currency_not_found")
    return currency


async def list_currencies(session: AsyncSession, tenant_id: uuid.UUID) -> list[Currency]:
    stmt = (
        select(Currency).where(Currency.tenant_id == tenant_id).order_by(Currency.code)
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_currency(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str,
    name: str,
    decimal_places: int = 2,
    is_functional: bool = False,
) -> Currency:
    """Create a currency (D-019). A duplicate code is a ConflictError (the DB UNIQUE backstops).
    Creating a second functional currency is refused — exactly one functional currency per tenant
    (the partial unique index backstops it); use ``set_functional_currency`` to switch."""
    existing = (
        await session.execute(
            select(Currency).where(Currency.tenant_id == tenant_id, Currency.code == code)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            message=f"A currency with code {code} already exists",
            code="finance.currency_code_conflict",
            details={"code": code},
        )
    if is_functional:
        await _assert_no_functional_currency(session, tenant_id)
    currency = Currency(
        tenant_id=tenant_id,
        code=code,
        name=name,
        decimal_places=decimal_places,
        is_functional=is_functional,
    )
    session.add(currency)
    await session.flush()
    return currency


async def _assert_no_functional_currency(
    session: AsyncSession, tenant_id: uuid.UUID
) -> None:
    existing = (
        await session.execute(
            select(Currency.id).where(
                Currency.tenant_id == tenant_id, Currency.is_functional.is_(True)
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message="This tenant already has a functional currency",
            code="finance.functional_currency_exists",
        )


async def set_functional_currency(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> Currency:
    """Make ``code`` the tenant's single functional currency (D-019). Clears the flag on any
    other currency first (loaded-object mutation so audit captures the demotion), so the
    one-functional invariant holds even mid-switch; the partial unique index is the DB backstop."""
    target = await get_currency(session, tenant_id, code)
    current = (
        await session.execute(
            select(Currency).where(
                Currency.tenant_id == tenant_id, Currency.is_functional.is_(True)
            )
        )
    ).scalars().all()
    for currency in current:
        if currency.id != target.id:
            currency.is_functional = False
    await session.flush()  # demote others before promoting, so the unique index never collides
    target.is_functional = True
    await session.flush()
    return target



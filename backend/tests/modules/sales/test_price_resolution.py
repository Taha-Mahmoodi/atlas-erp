"""The price-resolution engine tests (PLAN 7.1, D-043) — the key behavioural tests.

Cover: a clean match; no-match returns matched=False; exclusion by wrong currency / expired window /
INACTIVE status / wrong group / unmet min_quantity; group-specific beats general; and the priority →
specificity → latest-valid-from tie-break order. The resolver is also asserted BOUNDED (two queries)
via query_counter.
"""

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.sales import queries
from tests.conftest import QueryCounter
from tests.modules.sales.factories import (
    build_customer,
    build_customer_group,
    build_price_list,
    build_price_list_item,
    build_sales_setup,
)

_ON_DATE = date(2026, 6, 15)


async def _resolve(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    customer_id: uuid.UUID,
    quantity: str = "1",
    currency: str = "USD",
    on_date: date = _ON_DATE,
):
    with tenant_context(tenant_id):
        return await queries.resolve_price(
            session,
            tenant_id,
            item_id=item_id,
            customer_id=customer_id,
            on_date=on_date,
            quantity=Decimal(quantity),
            currency=currency,
        )


async def test_resolves_general_list(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a, valid_from=date(2026, 1, 1))
    await build_price_list_item(db_session, tenant_a, pl.id, setup.item_id, unit_price="10")
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id
    )
    assert resolved.matched is True
    assert resolved.unit_price == Decimal("10")
    assert resolved.price_list_id == pl.id
    assert resolved.currency_code == "USD"


async def test_no_match_returns_unmatched(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    # No price list at all.
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id
    )
    assert resolved.matched is False
    assert resolved.unit_price is None
    assert resolved.price_list_id is None


async def test_wrong_currency_excluded(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a, currency_code="USD")
    await build_price_list_item(db_session, tenant_a, pl.id, setup.item_id, unit_price="10")
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id, currency="EUR"
    )
    assert resolved.matched is False


async def test_expired_window_excluded(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    pl = await build_price_list(
        db_session, tenant_a, valid_from=date(2026, 1, 1), valid_to=date(2026, 3, 31)
    )
    await build_price_list_item(db_session, tenant_a, pl.id, setup.item_id, unit_price="10")
    # _ON_DATE (June) is past the March expiry.
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id
    )
    assert resolved.matched is False


async def test_future_window_excluded(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a, valid_from=date(2026, 12, 1))
    await build_price_list_item(db_session, tenant_a, pl.id, setup.item_id, unit_price="10")
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id
    )
    assert resolved.matched is False


async def test_inactive_list_excluded(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a, status="INACTIVE")
    await build_price_list_item(db_session, tenant_a, pl.id, setup.item_id, unit_price="10")
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id
    )
    assert resolved.matched is False


async def test_wrong_group_excluded(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    group_a = await build_customer_group(db_session, tenant_a, code="GA")
    group_b = await build_customer_group(db_session, tenant_a, code="GB")
    customer = await build_customer(db_session, tenant_a, customer_group_id=group_a.id)
    # A list targeting group B does not apply to a group-A customer.
    pl = await build_price_list(db_session, tenant_a, customer_group_id=group_b.id)
    await build_price_list_item(db_session, tenant_a, pl.id, setup.item_id, unit_price="10")
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id
    )
    assert resolved.matched is False


async def test_grouped_list_excluded_for_ungrouped_customer(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    group = await build_customer_group(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)  # no group
    pl = await build_price_list(db_session, tenant_a, customer_group_id=group.id)
    await build_price_list_item(db_session, tenant_a, pl.id, setup.item_id, unit_price="10")
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id
    )
    assert resolved.matched is False


async def test_min_quantity_floor(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    pl = await build_price_list(db_session, tenant_a)
    await build_price_list_item(
        db_session, tenant_a, pl.id, setup.item_id, unit_price="8", min_quantity="10"
    )
    # qty below the floor: no match.
    below = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id, quantity="5"
    )
    assert below.matched is False
    # qty at/above the floor: matches.
    at = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id, quantity="10"
    )
    assert at.matched is True and at.unit_price == Decimal("8")


async def test_group_specific_beats_general(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    group = await build_customer_group(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a, customer_group_id=group.id)
    general = await build_price_list(
        db_session, tenant_a, code="GEN", valid_from=date(2026, 1, 1)
    )
    await build_price_list_item(db_session, tenant_a, general.id, setup.item_id, unit_price="10")
    targeted = await build_price_list(
        db_session, tenant_a, code="GRP", customer_group_id=group.id, valid_from=date(2026, 1, 1)
    )
    await build_price_list_item(db_session, tenant_a, targeted.id, setup.item_id, unit_price="9")
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id
    )
    # Both apply at equal priority; the group-targeted list wins on specificity.
    assert resolved.price_list_id == targeted.id
    assert resolved.unit_price == Decimal("9")


async def test_priority_beats_specificity(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    group = await build_customer_group(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a, customer_group_id=group.id)
    # A general list with HIGHER priority beats a group-targeted list at default priority.
    general = await build_price_list(
        db_session, tenant_a, code="GEN", priority=5, valid_from=date(2026, 1, 1)
    )
    await build_price_list_item(db_session, tenant_a, general.id, setup.item_id, unit_price="7")
    targeted = await build_price_list(
        db_session, tenant_a, code="GRP", customer_group_id=group.id, valid_from=date(2026, 1, 1)
    )
    await build_price_list_item(db_session, tenant_a, targeted.id, setup.item_id, unit_price="9")
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id
    )
    assert resolved.price_list_id == general.id
    assert resolved.unit_price == Decimal("7")


async def test_latest_valid_from_breaks_tie(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_sales_setup(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    # Two general lists, equal priority + specificity: the later valid_from wins.
    older = await build_price_list(
        db_session, tenant_a, code="OLD", valid_from=date(2026, 1, 1)
    )
    await build_price_list_item(db_session, tenant_a, older.id, setup.item_id, unit_price="10")
    newer = await build_price_list(
        db_session, tenant_a, code="NEW", valid_from=date(2026, 5, 1)
    )
    await build_price_list_item(db_session, tenant_a, newer.id, setup.item_id, unit_price="8")
    resolved = await _resolve(
        db_session, tenant_a, item_id=setup.item_id, customer_id=customer.id
    )
    assert resolved.price_list_id == newer.id
    assert resolved.unit_price == Decimal("8")


async def test_resolver_is_bounded(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The resolver runs two queries (candidate lists + their items), regardless of how many lists
    exist (PERFORMANCE §6 — no per-list N+1)."""
    setup = await build_sales_setup(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    # Several competing general lists.
    for i in range(5):
        pl = await build_price_list(
            db_session, tenant_a, code=f"PL-{i}", priority=i, valid_from=date(2026, 1, 1)
        )
        await build_price_list_item(
            db_session, tenant_a, pl.id, setup.item_id, unit_price=str(10 + i)
        )
    with query_counter() as qc, tenant_context(tenant_a):
        resolved = await queries.resolve_price(
            db_session,
            tenant_a,
            item_id=setup.item_id,
            customer_id=customer.id,
            on_date=_ON_DATE,
            quantity=Decimal("1"),
            currency="USD",
        )
    # The customer-group lookup + the two resolver queries = 3 statements; never grows with list
    # count.
    assert qc.count <= 3, "\n".join(qc.statements)
    # Highest priority (4) wins.
    assert resolved.unit_price == Decimal("14")

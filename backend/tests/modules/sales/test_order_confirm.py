"""The confirm-gate tests (PLAN 7.2, D-044) — the heart of 7.2.

ATP: available → confirm PASSED with no backorder; short → confirm STILL succeeds (CONFIRMED) with
the line flagged backordered (ATP is informational, never blocks). A confirmed order's undelivered
quantity reduces ATP for the next order (the committed-quantity reservation).

Credit: within limit → CONFIRMED / PASSED; exposure (open AR + open confirmed orders + this order) >
limit → CREDIT_BLOCKED / BLOCKED (the HARD block); a credit-release by an authorised user → RELEASED
then CONFIRMED.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.tenancy import tenant_context
from app.modules.sales import queries, service
from app.modules.sales.constants import CreditCheckStatus, SalesOrderStatus
from tests.modules.sales.factories import (
    OrderSetup,
    build_order_setup,
    build_sales_order,
    seed_on_hand,
    seed_on_order,
    seed_open_ar,
)


async def _order(
    session: AsyncSession, setup: OrderSetup, *, quantity: str, unit_price: str = "10"
):
    return await build_sales_order(
        session,
        setup.tenant_id,
        customer_id=setup.customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity=quantity,
        unit_price=unit_price,
    )


# --- ATP ----------------------------------------------------------------------


async def test_atp_available_confirms_passed(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_order_setup(db_session, tenant_a)
    await seed_on_hand(db_session, setup, "100")
    order = await _order(db_session, setup, quantity="10")
    with tenant_context(tenant_a):
        result = await service.confirm_order(db_session, tenant_a, order.id)
    assert result.confirmed is True
    assert result.credit_status == CreditCheckStatus.PASSED
    assert result.order.status == SalesOrderStatus.CONFIRMED.value
    assert all(not line.backordered for line in result.backordered_lines)


async def test_atp_short_still_confirms_backordered(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_order_setup(db_session, tenant_a)
    await seed_on_hand(db_session, setup, "3")  # less than ordered
    order = await _order(db_session, setup, quantity="10")
    with tenant_context(tenant_a):
        result = await service.confirm_order(db_session, tenant_a, order.id)
    # ATP shortfall does NOT block — the order still confirms, the line is flagged backordered.
    assert result.confirmed is True
    assert result.order.status == SalesOrderStatus.CONFIRMED.value
    assert any(line.backordered for line in result.backordered_lines)


async def test_on_order_counts_toward_availability(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_order_setup(db_session, tenant_a)
    await seed_on_hand(db_session, setup, "2")
    await seed_on_order(db_session, setup, "20")  # open PO incoming
    with tenant_context(tenant_a):
        atp = await queries.atp_check(
            db_session,
            tenant_a,
            item_id=setup.item_id,
            quantity=Decimal("10"),
            on_date=date.today(),
        )
    # available = on_hand(2) − committed(0) + on_order(20) = 22 >= 10
    assert atp.on_order == Decimal("20")
    assert atp.available == Decimal("22")
    assert atp.atp_ok is True


async def test_committed_quantity_reduces_next_atp(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_order_setup(db_session, tenant_a)
    await seed_on_hand(db_session, setup, "12")
    first = await _order(db_session, setup, quantity="10")
    with tenant_context(tenant_a):
        await service.confirm_order(db_session, tenant_a, first.id)
        # The first confirmed order committed 10 of the 12 on-hand. A fresh ATP for 5 now short:
        atp = await queries.atp_check(
            db_session, tenant_a, item_id=setup.item_id, quantity=Decimal("5"), on_date=date.today()
        )
    assert atp.committed == Decimal("10")
    assert atp.available == Decimal("2")  # 12 − 10 committed
    assert atp.atp_ok is False


# --- Credit -------------------------------------------------------------------


async def test_credit_within_limit_confirms(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_order_setup(db_session, tenant_a, credit_limit="1000")
    await seed_on_hand(db_session, setup, "100")
    order = await _order(db_session, setup, quantity="10", unit_price="10")  # total 100 <= 1000
    with tenant_context(tenant_a):
        result = await service.confirm_order(db_session, tenant_a, order.id)
    assert result.confirmed is True
    assert result.credit_status == CreditCheckStatus.PASSED


async def test_credit_exceeded_blocks(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_order_setup(db_session, tenant_a, credit_limit="100")
    await seed_on_hand(db_session, setup, "100")
    await seed_open_ar(db_session, setup, "80")  # open AR already 80
    # order +50 → exposure 80 + 50 = 130 > 100
    order = await _order(db_session, setup, quantity="5", unit_price="10")
    with tenant_context(tenant_a):
        result = await service.confirm_order(db_session, tenant_a, order.id)
    assert result.confirmed is False
    assert result.credit_status == CreditCheckStatus.BLOCKED
    assert result.order.status == SalesOrderStatus.CREDIT_BLOCKED.value
    assert result.exposure == Decimal("130")
    assert result.credit_limit == Decimal("100")


async def test_credit_release_then_confirms(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_order_setup(db_session, tenant_a, credit_limit="100")
    await seed_on_hand(db_session, setup, "100")
    await seed_open_ar(db_session, setup, "120")  # already over the limit
    order = await _order(db_session, setup, quantity="1", unit_price="10")
    with tenant_context(tenant_a):
        blocked = await service.confirm_order(db_session, tenant_a, order.id)
        assert blocked.order.status == SalesOrderStatus.CREDIT_BLOCKED.value
        released = await service.release_credit(db_session, tenant_a, order.id)
    assert released.confirmed is True
    assert released.credit_status == CreditCheckStatus.RELEASED
    assert released.order.status == SalesOrderStatus.CONFIRMED.value


async def test_release_requires_blocked(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_order_setup(db_session, tenant_a, credit_limit="1000")
    await seed_on_hand(db_session, setup, "100")
    order = await _order(db_session, setup, quantity="1")
    with tenant_context(tenant_a):
        await service.confirm_order(db_session, tenant_a, order.id)  # PASSED, not blocked
        with pytest.raises(ConflictError):
            await service.release_credit(db_session, tenant_a, order.id)


async def test_confirm_is_idempotent(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_order_setup(db_session, tenant_a, credit_limit="1000")
    await seed_on_hand(db_session, setup, "100")
    order = await _order(db_session, setup, quantity="2")
    with tenant_context(tenant_a):
        first = await service.confirm_order(db_session, tenant_a, order.id)
        second = await service.confirm_order(db_session, tenant_a, order.id)
    assert first.order.status == second.order.status == SalesOrderStatus.CONFIRMED.value

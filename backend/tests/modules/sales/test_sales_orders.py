"""Sales-order service tests (PLAN 7.2): create from scratch, the customer-ACTIVE gate, amount
computation with discounts, the payment-terms snapshot, update/cancel + the queries read surface
(committed_quantity, so_line_open_to_deliver)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.sales import queries, service
from app.modules.sales.constants import CustomerStatus, DiscountType, SalesOrderStatus
from app.modules.sales.schemas import SalesOrderCreate, SalesOrderLineCreate, SalesOrderUpdate
from tests.modules.sales.factories import (
    SalesSetup,
    build_customer,
    build_sales_order,
    build_sales_setup,
)


async def _setup(
    session: AsyncSession, tenant_id: uuid.UUID, *, status: CustomerStatus = CustomerStatus.ACTIVE
) -> tuple[SalesSetup, uuid.UUID]:
    setup = await build_sales_setup(session, tenant_id)
    customer = await build_customer(
        session,
        tenant_id,
        customer_code="OC-1",
        status=status,
        payment_terms_days=45,
        credit_limit=Decimal("100000"),
    )
    return setup, customer.id


async def test_create_order_numbers_terms_total(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    order = await build_sales_order(
        db_session,
        tenant_a,
        customer_id=customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity="3",
        unit_price="20",
    )
    assert order.status == SalesOrderStatus.DRAFT.value
    assert order.order_number.startswith("SO-")
    assert order.payment_terms_days == 45  # snapshot from the customer
    assert order.credit_check_status is None
    assert Decimal(str(order.total_amount)) == Decimal("60")  # 3 × 20


async def test_blocked_customer_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup, customer_id = await _setup(db_session, tenant_a, status=CustomerStatus.BLOCKED)
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_sales_order(
            db_session,
            tenant_a,
            SalesOrderCreate(
                customer_id=customer_id,
                lines=[
                    SalesOrderLineCreate(
                        item_id=setup.item_id,
                        quantity=Decimal("1"),
                        uom_id=setup.uom_id,
                        unit_price=Decimal("10"),
                    )
                ],
            ),
        )
    assert exc.value.code == "sales.customer_not_active"


async def test_discount_amount(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    order = await build_sales_order(
        db_session,
        tenant_a,
        customer_id=customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity="10",
        unit_price="10",
        discount_type=DiscountType.PERCENT,
        discount_value=Decimal("25"),
    )
    # 10 × 10 = 100, less 25% = 75
    assert Decimal(str(order.total_amount)) == Decimal("75")


async def test_update_draft_replaces_lines(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    order = await build_sales_order(
        db_session,
        tenant_a,
        customer_id=customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity="2",
        unit_price="10",
    )
    with tenant_context(tenant_a):
        updated = await service.update_sales_order(
            db_session,
            tenant_a,
            order.id,
            SalesOrderUpdate(
                lines=[
                    SalesOrderLineCreate(
                        item_id=setup.item_id,
                        quantity=Decimal("5"),
                        uom_id=setup.uom_id,
                        unit_price=Decimal("4"),
                    )
                ]
            ),
        )
    assert Decimal(str(updated.total_amount)) == Decimal("20")  # 5 × 4


async def test_cancel_draft(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    order = await build_sales_order(
        db_session, tenant_a, customer_id=customer_id, item_id=setup.item_id, uom_id=setup.uom_id
    )
    with tenant_context(tenant_a):
        cancelled = await service.cancel_sales_order(db_session, tenant_a, order.id)
    assert cancelled.status == SalesOrderStatus.CANCELLED.value


async def test_so_line_open_to_deliver(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    order = await build_sales_order(
        db_session,
        tenant_a,
        customer_id=customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity="7",
        unit_price="10",
    )
    with tenant_context(tenant_a):
        lines = await service.get_sales_order_lines(db_session, tenant_a, order.id)
        open_qty = await queries.so_line_open_to_deliver(db_session, tenant_a, lines[0].id)
    assert open_qty == Decimal("7")  # ordered − delivered (0)


async def test_committed_quantity_only_counts_confirmed(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    # A DRAFT order commits nothing.
    await build_sales_order(
        db_session,
        tenant_a,
        customer_id=customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity="4",
        unit_price="10",
    )
    with tenant_context(tenant_a):
        committed = await queries.committed_quantity(db_session, tenant_a, setup.item_id)
    assert committed == Decimal("0")  # nothing CONFIRMED yet


async def test_update_non_draft_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    order = await build_sales_order(
        db_session, tenant_a, customer_id=customer_id, item_id=setup.item_id, uom_id=setup.uom_id
    )
    with tenant_context(tenant_a):
        # Confirm it (generous credit limit by default), then editing must conflict.
        await service.confirm_order(db_session, tenant_a, order.id)
        with pytest.raises(ConflictError):
            await service.update_sales_order(
                db_session, tenant_a, order.id, SalesOrderUpdate(notes="x")
            )

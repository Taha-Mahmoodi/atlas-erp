"""The sales-order confirm gate (PLAN 7.2, D-044): the ATP evaluation + the credit-limit HARD block,
and the credit-release override. Kept focused — this is the one piece of 7.2 with cross-module
arithmetic.

**ATP (informational, backorder-flag-NOT-block).** For each order line, availability =
inventory on-hand (``total_on_hand``) − committed (the undelivered demand of OTHER confirmed orders,
``committed_quantity`` excluding this order) + on-order (procurement ``open_incoming_quantity``). A
line whose requested quantity exceeds availability is a BACKORDER — but ATP does NOT block: parity
scopes v1 to "simple ATP = an availability check with manual backorders", so confirm records which
lines are backordered (the ATP snapshot) and proceeds. The HARD block is credit, below.

**Credit (HARD block).** Exposure = the customer's open AR (``customer_open_ar`` — open_amount on
POSTED customer invoices, finance) + the value of the customer's OTHER open confirmed orders
(``open_confirmed_order_value`` excluding this order) + THIS order's total. If exposure exceeds the
customer's ``credit_limit`` the order is set CREDIT_BLOCKED / credit_check_status BLOCKED and NOT
confirmed (the static credit-limit block at order confirmation per parity; 0 = cash-only). A user
with ``sales.order.credit_release`` calls ``release_credit`` → credit_check_status RELEASED, which
lets the next confirm proceed (a RELEASED order skips the credit gate). Within the limit → status
CONFIRMED / credit_check_status PASSED, and the order's undelivered quantity now COMMITS stock
against ATP for subsequent orders.

Idempotency (D-013) is owned by the confirm/release endpoints. Once CONFIRMED, re-confirming is a
no-op return (so a duplicate confirm is safe).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError
from app.modules.sales import queries as sales_queries
from app.modules.sales.constants import (
    CreditCheckStatus,
    SalesOrderStatus,
)
from app.modules.sales.models import SalesOrder
from app.modules.sales.service.orders import get_sales_order, get_sales_order_lines


@dataclass(frozen=True)
class LineAtp:
    """The ATP snapshot for one order line at confirm: the requested quantity, the computed
    availability components, and the ``backordered`` flag (requested > available). Recorded so the
    confirm response can show which lines are backordered (D-044: ATP is informational)."""

    item_id: uuid.UUID
    line_number: int
    requested_quantity: Decimal
    available: Decimal
    backordered: bool


@dataclass(frozen=True)
class ConfirmResult:
    """The outcome of a confirm attempt (D-044). ``confirmed`` False means the credit gate blocked
    (the order is CREDIT_BLOCKED); ``credit_status`` carries PASSED/BLOCKED/RELEASED. ``exposure`` +
    ``credit_limit`` explain the credit decision; ``backordered_lines`` lists the per-line ATP
    snapshot (informational — a backorder never blocks)."""

    order: SalesOrder
    confirmed: bool
    credit_status: CreditCheckStatus
    exposure: Decimal
    credit_limit: Decimal
    backordered_lines: list[LineAtp]


async def _evaluate_atp(
    session: AsyncSession, tenant_id: uuid.UUID, order: SalesOrder
) -> list[LineAtp]:
    """The ATP snapshot for every line of ``order`` (D-044). Availability EXCLUDES this order's own
    commitment (``exclude_order_id=order.id``) so a line is checked against stock net of OTHER
    confirmed orders — the order is about to commit its own demand. Backordered lines are flagged;
    ATP never blocks here."""
    on_date = order.order_date if order.order_date is not None else date.today()
    snapshot: list[LineAtp] = []
    for line in await get_sales_order_lines(session, tenant_id, order.id):
        result = await sales_queries.atp_check(
            session,
            tenant_id,
            item_id=line.item_id,
            quantity=Decimal(str(line.ordered_quantity)),
            on_date=on_date,
            exclude_order_id=order.id,
        )
        snapshot.append(
            LineAtp(
                item_id=line.item_id,
                line_number=line.line_number,
                requested_quantity=result.requested_quantity,
                available=result.available,
                backordered=not result.atp_ok,
            )
        )
    return snapshot


async def _credit_exposure(
    session: AsyncSession, tenant_id: uuid.UUID, order: SalesOrder
) -> Decimal:
    """The customer's credit exposure if THIS order confirms (D-044): open AR (POSTED customer
    invoices' open_amount, finance) + OTHER open confirmed orders' value + this order's total.
    Excludes this order from the open-order sum so it is counted exactly once (via its own
    total)."""
    open_ar = await sales_queries.customer_open_ar(session, tenant_id, order.customer_id)
    other_orders = await sales_queries.open_confirmed_order_value(
        session, tenant_id, order.customer_id, exclude_order_id=order.id
    )
    return open_ar + other_orders + Decimal(str(order.total_amount))


async def _do_confirm(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: SalesOrder,
    *,
    credit_status: CreditCheckStatus,
    backordered: list[LineAtp],
    exposure: Decimal,
    credit_limit: Decimal,
) -> ConfirmResult:
    """Flip the order to CONFIRMED with the given (PASSED/RELEASED) credit status, in the caller's
    transaction (docflow status synced). The committed quantities now count against ATP for
    subsequent orders."""
    order.status = SalesOrderStatus.CONFIRMED.value
    order.credit_check_status = credit_status.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, order.document_id, status=SalesOrderStatus.CONFIRMED.value
    )
    return ConfirmResult(
        order=order,
        confirmed=True,
        credit_status=credit_status,
        exposure=exposure,
        credit_limit=credit_limit,
        backordered_lines=backordered,
    )


async def confirm_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> ConfirmResult:
    """Confirm a DRAFT (or CREDIT_BLOCKED) order — THE gate (PLAN 7.2, D-044). Runs the ATP snapshot
    (informational), then the credit gate: exposure > credit_limit ⇒ CREDIT_BLOCKED (no confirm);
    within ⇒ CONFIRMED. A RELEASED order (a prior credit override) skips the credit gate and
    confirms. Re-confirming an already-CONFIRMED order is a no-op return (idempotent)."""
    order = await get_sales_order(session, tenant_id, order_id)
    status = SalesOrderStatus(order.status)

    if status == SalesOrderStatus.CONFIRMED:
        # Idempotent: already confirmed. Return its current ATP + exposure snapshot for the
        # response.
        backordered = await _evaluate_atp(session, tenant_id, order)
        exposure = await _credit_exposure(session, tenant_id, order)
        credit_limit = await sales_queries.customer_credit_limit(
            session, tenant_id, order.customer_id
        ) or Decimal(0)
        return ConfirmResult(
            order=order,
            confirmed=True,
            credit_status=CreditCheckStatus(order.credit_check_status or CreditCheckStatus.PASSED),
            exposure=exposure,
            credit_limit=credit_limit,
            backordered_lines=backordered,
        )

    if status not in (SalesOrderStatus.DRAFT, SalesOrderStatus.CREDIT_BLOCKED):
        raise ConflictError(
            message=f"A {order.status} sales order cannot be confirmed",
            code="sales.order_not_confirmable",
            details={"status": order.status},
        )

    backordered = await _evaluate_atp(session, tenant_id, order)
    exposure = await _credit_exposure(session, tenant_id, order)
    credit_limit = await sales_queries.customer_credit_limit(
        session, tenant_id, order.customer_id
    ) or Decimal(0)

    # A prior credit RELEASE overrides the limit: the order confirms regardless of exposure.
    if order.credit_check_status == CreditCheckStatus.RELEASED.value:
        return await _do_confirm(
            session,
            tenant_id,
            order,
            credit_status=CreditCheckStatus.RELEASED,
            backordered=backordered,
            exposure=exposure,
            credit_limit=credit_limit,
        )

    if exposure > credit_limit:
        order.status = SalesOrderStatus.CREDIT_BLOCKED.value
        order.credit_check_status = CreditCheckStatus.BLOCKED.value
        await session.flush()
        await docflow.set_document_status(
            session, tenant_id, order.document_id, status=SalesOrderStatus.CREDIT_BLOCKED.value
        )
        return ConfirmResult(
            order=order,
            confirmed=False,
            credit_status=CreditCheckStatus.BLOCKED,
            exposure=exposure,
            credit_limit=credit_limit,
            backordered_lines=backordered,
        )

    return await _do_confirm(
        session,
        tenant_id,
        order,
        credit_status=CreditCheckStatus.PASSED,
        backordered=backordered,
        exposure=exposure,
        credit_limit=credit_limit,
    )


async def release_credit(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> ConfirmResult:
    """Release a CREDIT_BLOCKED order past the credit limit (PLAN 7.2, the
    sales.order.credit_release
    action, D-044). Sets credit_check_status RELEASED and immediately confirms (the release is the
    authorisation to commit the order despite exposure). Only a CREDIT_BLOCKED order can be released
    — a DRAFT order has not yet hit the gate, a CONFIRMED order is already through it."""
    order = await get_sales_order(session, tenant_id, order_id)
    if SalesOrderStatus(order.status) != SalesOrderStatus.CREDIT_BLOCKED:
        raise ConflictError(
            message="Only a credit-blocked order can be credit-released",
            code="sales.order_not_credit_blocked",
            details={"status": order.status},
        )
    order.credit_check_status = CreditCheckStatus.RELEASED.value
    await session.flush()
    # Re-confirm: the RELEASED status makes confirm_order skip the credit gate.
    return await confirm_order(session, tenant_id, order_id)

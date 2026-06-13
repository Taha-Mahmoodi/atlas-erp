"""Production-order lifecycle + rollback service tests (PLAN 8.2, D-048): over-issue, closed-period
rollback, insufficient-stock rollback, WIP-unmapped, cancel terminality, tenant isolation.

Handler-raised failures (closed period, insufficient stock) follow issue #53: the assertion checks
the rolled-back state via a FRESH scalar read after the error, never the post-failure ORM state on
the same session. Shared helpers in _production_shared.py.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import queries as finance_queries
from app.modules.finance import service as finance_service
from app.modules.manufacturing import service
from app.modules.manufacturing.constants import ProductionOrderStatus
from app.modules.manufacturing.schemas import ComponentIssueLine, IssueComponentsRequest
from tests.modules.manufacturing._production_shared import (
    components,
    count_moves,
    create_order,
    get_order,
    order_status_and_wip,
    run,
)
from tests.modules.manufacturing.production_factories import build_production_order_setup

pytestmark = pytest.mark.asyncio


async def test_over_issue_is_422(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Issuing more than a component's required quantity → manufacturing.over_issue."""
    setup = await build_production_order_setup(db_session, tenant_a)
    order = await create_order(db_session, setup, quantity=Decimal(5))
    rows = await components(db_session, tenant_a, order.id)
    line = rows[0].line_number
    await run(db_session, tenant_a, lambda: service.release_order(db_session, tenant_a, order.id))
    with pytest.raises(ValidationFailedError) as exc:
        await run(
            db_session,
            tenant_a,
            lambda: service.issue_components(
                db_session,
                tenant_a,
                order.id,
                IssueComponentsRequest(
                    lines=[ComponentIssueLine(component_line_number=line, quantity=Decimal(999))]
                ),
            ),
        )
    assert exc.value.code == "manufacturing.over_issue"


async def test_issue_into_closed_period_rolls_back(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An issue whose WIP journal would land in a CLOSED period fails (the period trigger fires in
    the same transaction) and the whole issue rolls back — no move, no WIP debit (issue #53)."""
    setup = await build_production_order_setup(db_session, tenant_a)
    order = await create_order(db_session, setup, quantity=Decimal(5))
    order_id = order.id  # plain id so a post-rollback access never lazy-loads
    await run(db_session, tenant_a, lambda: service.release_order(db_session, tenant_a, order_id))
    with tenant_context(tenant_a):
        period = await finance_queries.find_period_for_date(
            db_session, tenant_a, date(2026, 6, 15)
        )
        await finance_service.close_period(db_session, tenant_a, period.id)
        await db_session.commit()
    moves_before = await count_moves(db_session, tenant_a)

    with pytest.raises(Exception):  # noqa: B017, PT011 - period trigger / service error
        await run(
            db_session,
            tenant_a,
            lambda: service.issue_components(
                db_session,
                tenant_a,
                order_id,
                IssueComponentsRequest(move_date=date(2026, 6, 15)),
            ),
        )
    assert await count_moves(db_session, tenant_a) == moves_before
    db_session.expire_all()
    status, wip = await order_status_and_wip(db_session, tenant_a, order_id)
    assert status == ProductionOrderStatus.RELEASED.value
    assert wip == 0


async def test_issue_insufficient_stock_rolls_back(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Issuing more component than is on hand trips the inventory move guard and rolls the whole
    issue back — no move, no WIP debit (issue #53: fresh read after the error)."""
    setup = await build_production_order_setup(
        db_session, tenant_a, component_on_hand=Decimal(4), quantity_per=Decimal(2)
    )
    # Order qty 5 → required 10 component units, but only 4 on hand.
    order = await create_order(db_session, setup, quantity=Decimal(5))
    order_id = order.id
    await run(db_session, tenant_a, lambda: service.release_order(db_session, tenant_a, order_id))
    moves_before = await count_moves(db_session, tenant_a)
    with pytest.raises(Exception):  # noqa: B017, PT011 - inventory move guard
        await run(
            db_session,
            tenant_a,
            lambda: service.issue_components(
                db_session, tenant_a, order_id, IssueComponentsRequest()
            ),
        )
    assert await count_moves(db_session, tenant_a) == moves_before
    db_session.expire_all()
    status, wip = await order_status_and_wip(db_session, tenant_a, order_id)
    assert status == ProductionOrderStatus.RELEASED.value
    assert wip == 0


async def test_issue_without_wip_default_is_422(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A tenant that has not mapped the WIP clearing posting default cannot issue components."""
    setup = await build_production_order_setup(db_session, tenant_a, map_wip=False)
    order = await create_order(db_session, setup, quantity=Decimal(5))
    await run(db_session, tenant_a, lambda: service.release_order(db_session, tenant_a, order.id))
    with pytest.raises(ValidationFailedError) as exc:
        await run(
            db_session,
            tenant_a,
            lambda: service.issue_components(
                db_session, tenant_a, order.id, IssueComponentsRequest()
            ),
        )
    assert exc.value.code == "finance.posting_default_unmapped"


async def test_cancel_draft_then_issued_terminal(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A DRAFT order cancels; once components are issued (IN_PROGRESS) it can no longer be
    cancelled."""
    setup = await build_production_order_setup(db_session, tenant_a)
    draft = await create_order(db_session, setup, quantity=Decimal(5))
    await run(db_session, tenant_a, lambda: service.cancel_order(db_session, tenant_a, draft.id))
    cancelled = await get_order(db_session, tenant_a, draft.id)
    assert cancelled.status == ProductionOrderStatus.CANCELLED.value

    issued_order = await create_order(db_session, setup, quantity=Decimal(5))
    await run(
        db_session, tenant_a, lambda: service.release_order(db_session, tenant_a, issued_order.id)
    )
    await run(
        db_session,
        tenant_a,
        lambda: service.issue_components(
            db_session, tenant_a, issued_order.id, IssueComponentsRequest()
        ),
    )
    with pytest.raises(ConflictError) as exc:
        await run(
            db_session,
            tenant_a,
            lambda: service.cancel_order(db_session, tenant_a, issued_order.id),
        )
    assert exc.value.code == "manufacturing.production_order_not_cancellable"


async def test_isolation_other_tenant_cannot_read(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A production order in tenant A is not visible to tenant B (D-007)."""
    setup = await build_production_order_setup(db_session, tenant_a)
    order = await create_order(db_session, setup, quantity=Decimal(5))
    with tenant_context(tenant_b), pytest.raises(NotFoundError):
        await service.get_production_order(db_session, tenant_b, order.id)

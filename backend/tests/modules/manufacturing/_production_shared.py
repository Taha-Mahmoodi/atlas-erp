"""Shared helpers for the production-order service tests (PLAN 8.2), split out so the create/issue/
finish proofs and the lifecycle/rollback tests each stay under the 400-line file cap (STRUCTURE
§8.4). All helpers wrap reads in a tenant context and never lazy-load a post-failure ORM object
(issue #53)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.inventory.models import StockMove
from app.modules.manufacturing import service
from app.modules.manufacturing.models import ProductionOrder
from app.modules.manufacturing.schemas import ProductionOrderCreate
from tests.modules.manufacturing.production_factories import build_production_order


async def balance(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> Decimal:
    """Signed (debit-positive) balance of one account over the posted journal — the trial-balance
    figure for the WIP-nets-to-zero proof."""
    with tenant_context(tenant_id):
        balances = await finance_queries.account_balances(
            session, tenant_id, date_to=date(2099, 1, 1)
        )
    return balances.get(account_id, Decimal(0))


async def run(session: AsyncSession, tenant_id: uuid.UUID, coro_factory) -> None:
    async def work() -> None:
        with tenant_context(tenant_id):
            await coro_factory()

    with tenant_context(tenant_id):
        await run_in_uow(session, work)


async def get_order(session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID):
    with tenant_context(tenant_id):
        return await service.get_production_order(session, tenant_id, order_id)


async def components(session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID):
    with tenant_context(tenant_id):
        return await service.production_order_components(session, tenant_id, order_id)


async def on_hand(session: AsyncSession, tenant_id: uuid.UUID, item_id, bin_id):
    with tenant_context(tenant_id):
        return await inventory_queries.on_hand(session, tenant_id, item_id, bin_id=bin_id)


async def item_value(session: AsyncSession, tenant_id: uuid.UUID, item_id):
    with tenant_context(tenant_id):
        return await inventory_queries.item_value(session, tenant_id, item_id)


async def count_moves(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    with tenant_context(tenant_id):
        return (
            await session.execute(
                select(func.count()).select_from(StockMove).where(
                    StockMove.tenant_id == tenant_id
                )
            )
        ).scalar_one()


async def order_status_and_wip(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> tuple[str, Decimal]:
    """A FRESH (status, accumulated_wip_cost) scalar read — used after a rolled-back handler error
    so the assertion never lazy-loads an expired ORM object (issue #53)."""
    with tenant_context(tenant_id):
        row = (
            await session.execute(
                select(
                    ProductionOrder.status, ProductionOrder.accumulated_wip_cost
                ).where(ProductionOrder.id == order_id)
            )
        ).one()
    return row[0], Decimal(row[1])


async def create_order(session: AsyncSession, setup, *, quantity: Decimal = Decimal(5)):
    return await build_production_order(
        session,
        setup.tenant_id,
        ProductionOrderCreate(
            item_id=setup.parent_item_id,
            quantity=quantity,
            warehouse_id=setup.warehouse_id,
        ),
    )

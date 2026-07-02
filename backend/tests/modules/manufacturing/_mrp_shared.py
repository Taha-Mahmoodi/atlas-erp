"""Shared helpers for the MRP service tests (PLAN 8.3), split out so the engine proofs (test_mrp.py)
and the planning/conversion/capacity proofs (test_mrp_planning.py) each stay under the 400-line file
cap (STRUCTURE §8.4). All helpers wrap reads in a tenant context and never lazy-load a post-failure
ORM object (issue #53).
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.modules.manufacturing import service
from app.modules.manufacturing.models import MrpRun, PlannedOrder

RUN_DATE = date(2026, 6, 1)


async def run_mrp(session: AsyncSession, tenant_id: uuid.UUID) -> MrpRun:
    """Drive one MRP run through the real service inside a uow (D-025); re-read the run header."""
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(tenant_id):
            run = await service.run_mrp(session, tenant_id, RUN_DATE)
            holder["id"] = run.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_mrp_run(session, tenant_id, holder["id"])


async def planned_by_item(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> dict[uuid.UUID, PlannedOrder]:
    """A run's planned orders keyed by item id (each item is planned at most once per run)."""
    with tenant_context(tenant_id):
        rows = (
            await session.execute(
                select(PlannedOrder).where(
                    PlannedOrder.tenant_id == tenant_id, PlannedOrder.mrp_run_id == run_id
                )
            )
        ).scalars().all()
    return {row.item_id: row for row in rows}

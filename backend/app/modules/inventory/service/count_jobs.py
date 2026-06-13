"""Background-job handler for a large stock-count post (PLAN 5.4, PERFORMANCE §3).

Split from ``counts.py`` so that file stays under the STRUCTURE §3 400-line cap (the depreciation
handler lives inline only because its service file had room; here it does not). A count whose post
would generate more than ``COUNT_POST_SYNC_MAX_VARIANCES`` variance lines is submitted as an
``inventory.count_post`` job by the router (202 {job_id}); the runner (core/jobs.py) executes THIS
handler inside ``run_in_uow`` under the submitting tenant context, so the post — including every
variance ADJUSTMENT move's costing journal — behaves exactly as the inline path, just off the
request. The handler is a thin delegation to :func:`post_count`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs import register_job
from app.modules.inventory.constants import COUNT_POST_JOB
from app.modules.inventory.models import StockCountLine
from app.modules.inventory.service.counts import post_count


@register_job(COUNT_POST_JOB)
async def count_post_job(
    session: AsyncSession, tenant_id: uuid.UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    """Post a large count's variances as ADJUSTMENT moves off-request (PERFORMANCE §3). Delegates to
    :func:`post_count` (the same engine the inline path uses), so the re-validation against live
    on-hand, the per-variance adjustment moves + their journals and the one-transaction guarantee
    all hold. Returns the count id/number/status + how many variance moves it generated."""
    count = await post_count(session, tenant_id, uuid.UUID(payload["count_id"]))
    await session.refresh(count)
    adjustment_moves = await _count_adjustment_moves(
        session, tenant_id, uuid.UUID(payload["count_id"])
    )
    return {
        "count_id": str(count.id),
        "count_number": count.count_number,
        "status": count.status,
        "adjustment_move_count": adjustment_moves,
    }


async def _count_adjustment_moves(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID
) -> int:
    """How many lines posted a non-zero-variance ADJUSTMENT move (adjustment_move_id NOT NULL)."""
    return (
        await session.execute(
            select(func.count(StockCountLine.id)).where(
                StockCountLine.tenant_id == tenant_id,
                StockCountLine.count_id == count_id,
                StockCountLine.adjustment_move_id.is_not(None),
            )
        )
    ).scalar_one()

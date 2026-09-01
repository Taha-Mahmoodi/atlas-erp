"""The manual nightly rate a room type is sold at (PLAN 20.1).

Its own file, moved out of ``rooms.py`` unchanged when PLAN 20.2's allotment hook took that file
to the STRUCTURE §8.4 cap. It is its own aggregate under STRUCTURE §3 and the only hotel master
that carries money, so the seam is real rather than arithmetic: the two functions with a rule of
their own here are about a validity WINDOW, which neither of the other masters has.

The shared master-CRUD plumbing — the friendly ``*_code_conflict`` before the DB UNIQUE, the
PATCH's ``exclude_unset`` handling, and the room-type getter every rate plan is validated against
— stays in ``rooms.py`` and is imported. One copy of each, which is the whole reason they exist.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.hospitality.models import RatePlan
from app.modules.hospitality.rooms_schemas import RatePlanCreate, RatePlanUpdate
from app.modules.hospitality.service.rooms import (
    get_room_type,
    require_code_free,
    sent_fields,
)


async def get_rate_plan(
    session: AsyncSession, tenant_id: uuid.UUID, rate_plan_id: uuid.UUID
) -> RatePlan:
    """The plan, or 404 ``hospitality.rate_plan_not_found``."""
    plan = await session.get(RatePlan, rate_plan_id)
    if plan is None or plan.tenant_id != tenant_id:
        raise NotFoundError(message="Rate plan not found", code="hospitality.rate_plan_not_found")
    return plan


def _require_window(valid_from: date, valid_to: date | None) -> None:
    """A validity window is the whole of v1's rate calendar, so the one thing it must not be is
    backwards — a window covering no night is a rate nothing can ever resolve. The DB CHECK is the
    backstop; this is the readable refusal."""
    if valid_to is not None and valid_to < valid_from:
        raise ValidationFailedError(
            message="A rate plan cannot end before it starts",
            code="hospitality.rate_plan_window_invalid",
            details={"valid_from": str(valid_from), "valid_to": str(valid_to)},
        )


async def create_rate_plan(
    session: AsyncSession, tenant_id: uuid.UUID, payload: RatePlanCreate
) -> RatePlan:
    await require_code_free(
        session,
        tenant_id,
        RatePlan,
        payload.code,
        label="rate plan",
        error_code="hospitality.rate_plan_code_conflict",
    )
    _require_window(payload.valid_from, payload.valid_to)
    await get_room_type(session, tenant_id, payload.room_type_id)
    plan = RatePlan(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        room_type_id=payload.room_type_id,
        nightly_amount=payload.nightly_amount,
        currency_code=payload.currency_code.upper(),
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    session.add(plan)
    await session.flush()
    return plan


async def update_rate_plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rate_plan_id: uuid.UUID,
    payload: RatePlanUpdate,
) -> RatePlan:
    """Re-price or re-window. The window is re-checked against whichever half is NOT being sent,
    so shortening a plan cannot leave it backwards."""
    plan = await get_rate_plan(session, tenant_id, rate_plan_id)
    # valid_to is the one nullable column: sending null OPENS the window (see RatePlanUpdate).
    data = sent_fields(payload, nullable=frozenset({"valid_to"}))
    _require_window(
        data.get("valid_from", plan.valid_from), data.get("valid_to", plan.valid_to)
    )
    for field, value in data.items():
        setattr(plan, field, value)
    await session.flush()
    return plan


async def list_rate_plans(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    room_type_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[RatePlan]:
    """The property's rates in code order, optionally for one room type."""
    stmt = select(RatePlan).where(RatePlan.tenant_id == tenant_id)
    if room_type_id is not None:
        stmt = stmt.where(RatePlan.room_type_id == room_type_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(RatePlan.code, SortDirection.ASC)],
        pk=RatePlan.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(room_type_id),
    )

"""Allocation-rule + target CRUD (PLAN 4.7), split out of ``service/controlling.py``.

Split so both files stay under the STRUCTURE §3 cap: ``controlling.py`` owns the cost/profit centre
master data, this file owns allocation rules + their targets, and ``allocation.py`` owns the run
engine. A rule names a SOURCE cost centre whose net period cost is redistributed; its targets carry
weights validated against the basis: PERCENT weights must sum to 100, FIXED_WEIGHT weights are
arbitrary positive numbers distributed proportionally by ``run_allocation``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import OrderKey, SortDirection, paginate
from app.core.schemas import Page
from app.modules.finance.constants import AllocationBasis
from app.modules.finance.controlling_schemas import (
    AllocationRuleCreate,
    AllocationRuleUpdate,
    AllocationTargetCreate,
)
from app.modules.finance.models import AllocationRule, AllocationRuleTarget, CostCenter
from app.modules.finance.service.controlling import get_cost_center

# PERCENT-basis target weights must sum to exactly this (a full redistribution of the source).
_PERCENT_TOTAL = Decimal(100)


def _validate_targets(
    basis: AllocationBasis,
    source_cost_center_id: uuid.UUID,
    targets: list[AllocationTargetCreate],
) -> None:
    """Validate a rule's targets against its basis (PLAN 4.7). At least one target; no target is the
    source (a centre cannot allocate to itself); no duplicate target; every weight positive; PERCENT
    weights sum to exactly 100. Raises ValidationFailedError on any breach."""
    if not targets:
        raise ValidationFailedError(
            message="An allocation rule needs at least one target",
            code="finance.allocation_no_targets",
        )
    seen: set[uuid.UUID] = set()
    for target in targets:
        if target.target_cost_center_id == source_cost_center_id:
            raise ValidationFailedError(
                message="A cost centre cannot allocate to itself",
                code="finance.allocation_target_is_source",
            )
        if target.target_cost_center_id in seen:
            raise ValidationFailedError(
                message="An allocation rule lists each target cost centre at most once",
                code="finance.allocation_duplicate_target",
                details={"target_cost_center_id": str(target.target_cost_center_id)},
            )
        seen.add(target.target_cost_center_id)
        if target.weight <= 0:
            raise ValidationFailedError(
                message="Allocation target weights must be positive",
                code="finance.allocation_weight_not_positive",
            )
    if basis == AllocationBasis.PERCENT:
        total = sum((t.weight for t in targets), Decimal(0))
        if total != _PERCENT_TOTAL:
            raise ValidationFailedError(
                message="PERCENT allocation target weights must sum to 100",
                code="finance.allocation_percent_not_100",
                details={"total": str(total)},
            )


async def get_allocation_rule(
    session: AsyncSession, tenant_id: uuid.UUID, rule_id: uuid.UUID
) -> AllocationRule:
    rule = await session.get(AllocationRule, rule_id)
    if rule is None or rule.tenant_id != tenant_id:
        raise NotFoundError(
            message="Allocation rule not found", code="finance.allocation_rule_not_found"
        )
    return rule


async def get_rule_targets(
    session: AsyncSession, tenant_id: uuid.UUID, rule_id: uuid.UUID
) -> list[AllocationRuleTarget]:
    """A rule's targets ordered by id (a stable, bounded set)."""
    stmt = (
        select(AllocationRuleTarget)
        .where(
            AllocationRuleTarget.tenant_id == tenant_id,
            AllocationRuleTarget.allocation_rule_id == rule_id,
        )
        .order_by(AllocationRuleTarget.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _require_target_centers(
    session: AsyncSession, tenant_id: uuid.UUID, targets: list[AllocationTargetCreate]
) -> None:
    """Every target cost centre must exist in the tenant (one query)."""
    ids = {t.target_cost_center_id for t in targets}
    rows = (
        await session.execute(
            select(CostCenter.id).where(
                CostCenter.tenant_id == tenant_id, CostCenter.id.in_(ids)
            )
        )
    ).scalars().all()
    missing = [str(cid) for cid in ids if cid not in set(rows)]
    if missing:
        raise ValidationFailedError(
            message="One or more allocation targets reference an unknown cost centre",
            code="finance.allocation_target_not_found",
            details={"cost_center_ids": missing},
        )


async def create_allocation_rule(
    session: AsyncSession, tenant_id: uuid.UUID, payload: AllocationRuleCreate
) -> AllocationRule:
    """Create an allocation rule + its targets (PLAN 4.7). Rejects a duplicate code; validates the
    source + every target cost centre exist; validates the targets against the basis (PERCENT sums
    to 100, FIXED_WEIGHT all positive)."""
    existing = (
        await session.execute(
            select(AllocationRule).where(
                AllocationRule.tenant_id == tenant_id, AllocationRule.code == payload.code
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            message=f"An allocation rule with code {payload.code} already exists",
            code="finance.allocation_rule_code_conflict",
            details={"code": payload.code},
        )
    basis = AllocationBasis(payload.basis)
    await get_cost_center(session, tenant_id, payload.source_cost_center_id)
    _validate_targets(basis, payload.source_cost_center_id, payload.targets)
    await _require_target_centers(session, tenant_id, payload.targets)

    rule = AllocationRule(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        source_cost_center_id=payload.source_cost_center_id,
        basis=basis.value,
        is_active=payload.is_active,
    )
    session.add(rule)
    await session.flush()
    for target in payload.targets:
        session.add(
            AllocationRuleTarget(
                tenant_id=tenant_id,
                allocation_rule_id=rule.id,
                target_cost_center_id=target.target_cost_center_id,
                weight=target.weight,
            )
        )
    await session.flush()
    return rule


async def update_allocation_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule_id: uuid.UUID,
    payload: AllocationRuleUpdate,
) -> AllocationRule:
    """Partial update of a rule's header and, when ``targets`` is supplied, its FULL target set
    (replaced atomically and re-validated against the resulting basis)."""
    rule = await get_allocation_rule(session, tenant_id, rule_id)
    data = payload.model_dump(exclude_unset=True)
    new_basis = (
        AllocationBasis(data["basis"])
        if data.get("basis") is not None
        else AllocationBasis(rule.basis)
    )
    if payload.targets is not None:
        _validate_targets(new_basis, rule.source_cost_center_id, payload.targets)
        await _require_target_centers(session, tenant_id, payload.targets)
        for existing in await get_rule_targets(session, tenant_id, rule_id):
            await session.delete(existing)
        await session.flush()
        for target in payload.targets:
            session.add(
                AllocationRuleTarget(
                    tenant_id=tenant_id,
                    allocation_rule_id=rule_id,
                    target_cost_center_id=target.target_cost_center_id,
                    weight=target.weight,
                )
            )
    for field in ("name", "is_active"):
        if field in data:
            setattr(rule, field, data[field])
    if data.get("basis") is not None:
        rule.basis = new_basis.value
    await session.flush()
    return rule


async def list_allocation_rules(
    session: AsyncSession, tenant_id: uuid.UUID, *, cursor: str | None, limit: int
) -> Page[AllocationRule]:
    """Keyset-paginated allocation-rule list ordered by code (D-014)."""
    stmt = select(AllocationRule).where(AllocationRule.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(AllocationRule.code, SortDirection.ASC)],
        pk=AllocationRule.id,
        cursor=cursor,
        limit=limit,
    )

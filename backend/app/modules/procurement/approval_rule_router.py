"""Approval-rule HTTP layer (PLAN 6.2), included into the procurement router.

CRUD for the value-threshold rules that gate requisition submit + PO send (D-040). Reads and writes
are both guarded by the single ``procurement.approval_rule.manage`` key — a rule is privileged
config
visible only to the role that maintains it (there is no separate read key; the gate lives in the
documents, not in browsing the rules). Writes commit through ``run_in_uow`` (D-011) so audit rows
ride the transaction.
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.procurement import service
from app.modules.procurement.constants import PROCUREMENT_APPROVAL_RULE_MANAGE
from app.modules.procurement.schemas import (
    ApprovalRuleCreate,
    ApprovalRuleFilter,
    ApprovalRuleRead,
    ApprovalRuleUpdate,
)

approval_rule_router = APIRouter(tags=["procurement-approval-rules"])

CursorParamsDep = Depends(cursor_params)


@approval_rule_router.post(
    "/approval-rules",
    response_model=ApprovalRuleRead,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_APPROVAL_RULE_MANAGE))],
)
async def create_approval_rule(
    payload: ApprovalRuleCreate, current: CurrentUserDep, session: SessionDep
) -> ApprovalRuleRead:
    holder: dict[str, ApprovalRuleRead] = {}

    async def work() -> None:
        rule = await service.create_approval_rule(session, current.tenant_id, payload)
        await session.refresh(rule)
        holder["read"] = ApprovalRuleRead.model_validate(rule)

    await run_in_uow(session, work)
    return holder["read"]


@approval_rule_router.get(
    "/approval-rules",
    response_model=Page[ApprovalRuleRead],
    dependencies=[Depends(require_permission(PROCUREMENT_APPROVAL_RULE_MANAGE))],
)
async def list_approval_rules(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    document_type: str | None = None,
    is_active: bool | None = None,
) -> Page[ApprovalRuleRead]:
    filters = ApprovalRuleFilter(document_type=document_type, is_active=is_active)
    page = await service.list_approval_rules(
        session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, ApprovalRuleRead)


@approval_rule_router.get(
    "/approval-rules/{rule_id}",
    response_model=ApprovalRuleRead,
    dependencies=[Depends(require_permission(PROCUREMENT_APPROVAL_RULE_MANAGE))],
)
async def get_approval_rule(
    rule_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ApprovalRuleRead:
    rule = await service.get_approval_rule(session, current.tenant_id, rule_id)
    return ApprovalRuleRead.model_validate(rule)


@approval_rule_router.patch(
    "/approval-rules/{rule_id}",
    response_model=ApprovalRuleRead,
    dependencies=[Depends(require_permission(PROCUREMENT_APPROVAL_RULE_MANAGE))],
)
async def update_approval_rule(
    rule_id: uuid.UUID,
    payload: ApprovalRuleUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> ApprovalRuleRead:
    holder: dict[str, ApprovalRuleRead] = {}

    async def work() -> None:
        rule = await service.update_approval_rule(session, current.tenant_id, rule_id, payload)
        await session.refresh(rule)
        holder["read"] = ApprovalRuleRead.model_validate(rule)

    await run_in_uow(session, work)
    return holder["read"]

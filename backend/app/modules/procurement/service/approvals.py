"""Approval-rule business logic (PLAN 6.2, D-040): rule CRUD + the value-threshold evaluator.

The DATA-DRIVEN release rule lives here: ``requires_approval(document_type, amount, currency)``
reads the single active rule for the document type and returns whether the amount is AT OR ABOVE the
threshold. No active rule (none configured, or the configured one is inactive) ⇒ no approval needed
(documented: a tenant that has not set up approval thresholds runs without a gate). A rule whose
currency differs from the document's currency does NOT apply — v1 is single-currency per rule and
matching the currency is the conservative choice (a cross-currency threshold would need FX, deferred
per parity); a mismatch reads as "no applicable rule", so the document auto-approves rather than
silently comparing across currencies.

ONE rule per (tenant, document_type) — ``UNIQUE`` at the DB; the create path rejects a second rule
for the same type with a friendly ConflictError before the backstop fires.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.procurement.constants import ApprovalDocumentType
from app.modules.procurement.models import ApprovalRule
from app.modules.procurement.schemas import (
    ApprovalRuleCreate,
    ApprovalRuleFilter,
    ApprovalRuleUpdate,
)


async def _validate_currency(
    session: AsyncSession, tenant_id: uuid.UUID, currency_code: str
) -> None:
    if not await finance_queries.currency_exists(session, tenant_id, currency_code):
        raise ValidationFailedError(
            message=f"Currency {currency_code} does not exist in the finance catalog",
            code="procurement.currency_not_found",
            details={"currency_code": currency_code},
        )


async def get_approval_rule(
    session: AsyncSession, tenant_id: uuid.UUID, rule_id: uuid.UUID
) -> ApprovalRule:
    rule = await session.get(ApprovalRule, rule_id)
    if rule is None or rule.tenant_id != tenant_id:
        raise NotFoundError(
            message="Approval rule not found", code="procurement.approval_rule_not_found"
        )
    return rule


async def create_approval_rule(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ApprovalRuleCreate
) -> ApprovalRule:
    """Create a value-threshold rule (PLAN 6.2). Validates the currency exists in finance; rejects a
    second rule for the same document_type (one rule per type — friendly ConflictError before the
    UNIQUE backstop)."""
    await _validate_currency(session, tenant_id, payload.currency_code)
    existing = (
        await session.execute(
            select(ApprovalRule.id).where(
                ApprovalRule.tenant_id == tenant_id,
                ApprovalRule.document_type
                == ApprovalDocumentType(payload.document_type).value,
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"An approval rule for {payload.document_type} already exists",
            code="procurement.approval_rule_conflict",
            details={"document_type": ApprovalDocumentType(payload.document_type).value},
        )
    rule = ApprovalRule(
        tenant_id=tenant_id,
        document_type=ApprovalDocumentType(payload.document_type).value,
        threshold_amount=Decimal(str(payload.threshold_amount)),
        currency_code=payload.currency_code,
        is_active=payload.is_active,
        description=payload.description,
    )
    session.add(rule)
    await session.flush()
    return rule


async def update_approval_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule_id: uuid.UUID,
    payload: ApprovalRuleUpdate,
) -> ApprovalRule:
    """Partial update of a rule (D-010: mutate the loaded object so the audit diff is captured).
    ``document_type`` is immutable (it keys the rule). A changed currency is re-validated."""
    rule = await get_approval_rule(session, tenant_id, rule_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("currency_code") is not None:
        await _validate_currency(session, tenant_id, data["currency_code"])
    if data.get("threshold_amount") is not None:
        data["threshold_amount"] = Decimal(str(data["threshold_amount"]))
    for field, value in data.items():
        setattr(rule, field, value)
    await session.flush()
    return rule


async def list_approval_rules(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: ApprovalRuleFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[ApprovalRule]:
    """Keyset-paginated rule list ordered by document_type (D-014). The optional document_type /
    is_active filters fold into the cursor fingerprint."""
    stmt = select(ApprovalRule).where(ApprovalRule.tenant_id == tenant_id)
    if filters.document_type is not None:
        stmt = stmt.where(
            ApprovalRule.document_type == ApprovalDocumentType(filters.document_type).value
        )
    if filters.is_active is not None:
        stmt = stmt.where(ApprovalRule.is_active.is_(filters.is_active))
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(ApprovalRule.document_type, SortDirection.ASC)],
        pk=ApprovalRule.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(filters.document_type, filters.is_active),
    )


async def requires_approval(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document_type: ApprovalDocumentType,
    amount: Decimal,
    currency_code: str,
) -> bool:
    """Whether a document of ``document_type`` at ``amount`` in ``currency_code`` needs approval
    (PLAN 6.2, D-040). Reads the single ACTIVE rule for the type: returns True iff the amount is AT
    OR ABOVE its threshold AND the rule's currency matches the document's. No active rule, or a
    currency mismatch, ⇒ False (no gate — documented in the module docstring)."""
    rule = (
        await session.execute(
            select(ApprovalRule).where(
                ApprovalRule.tenant_id == tenant_id,
                ApprovalRule.document_type == ApprovalDocumentType(document_type).value,
                ApprovalRule.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if rule is None or rule.currency_code != currency_code:
        return False
    return Decimal(str(amount)) >= Decimal(str(rule.threshold_amount))

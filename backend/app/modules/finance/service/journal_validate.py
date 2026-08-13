"""Draft-entry validation helpers (D-017/D-022), split out of ``service/journal.py``.

Kept separate so the posting engine stays under the STRUCTURE §3 400-line cap. These are the
pre-write checks ``create_draft_entry`` runs before a line is persisted: each line is one-sided
(mirrors the DB one-side CHECK), every referenced account exists + is postable, and every cost-/
profit-centre dimension exists for the tenant. The dimension check IS the service-level integrity
the absent FK on the trigger-bearing journal-lines table would give (D-022).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.modules.finance import queries
from app.modules.finance.models import Account
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate


def assert_line_one_sided(payload: JournalLineCreate, line_number: int) -> None:
    """Reject a line with both (or neither) of debit/credit positive — mirrors the DB one-side
    CHECK so the service gives a clean 422 before the insert (D-017)."""
    debit = payload.transaction_debit_amount
    credit = payload.transaction_credit_amount
    one_sided = (debit > 0 and credit == 0) or (credit > 0 and debit == 0)
    if not one_sided:
        raise ValidationFailedError(
            message=(
                f"Line {line_number} must have exactly one of debit/credit positive "
                "(the other zero)"
            ),
            code="finance.journal_line_not_one_sided",
            details={"line_number": line_number},
        )


async def require_postable_accounts(
    session: AsyncSession, tenant_id: uuid.UUID, account_ids: set[uuid.UUID]
) -> None:
    """Every referenced account must exist in this tenant AND be postable (leaf). One query."""
    rows = (
        await session.execute(
            select(Account.id, Account.is_postable).where(
                Account.tenant_id == tenant_id, Account.id.in_(account_ids)
            )
        )
    ).all()
    found = {row[0]: row[1] for row in rows}
    missing = [str(aid) for aid in account_ids if aid not in found]
    if missing:
        raise ValidationFailedError(
            message="One or more lines reference an unknown account",
            code="finance.journal_account_not_found",
            details={"account_ids": missing},
        )
    not_postable = [str(aid) for aid, postable in found.items() if not postable]
    if not_postable:
        raise ValidationFailedError(
            message="One or more lines reference a non-postable account",
            code="finance.journal_account_not_postable",
            details={"account_ids": not_postable},
        )


async def require_dimensions(
    session: AsyncSession, tenant_id: uuid.UUID, payload: JournalEntryCreate
) -> None:
    """Validate every line's cost-centre / profit-centre dimension exists in the tenant (PLAN 4.7).

    The journal-lines table is trigger-bearing and carries these dimensions as OPAQUE ``sa.Uuid``
    with NO FK (D-022), so this service-level check IS the dimension integrity backstop the absent
    FK would otherwise give. ONE bulk query per dimension TYPE over the distinct referenced ids
    (#81 — the require_postable_accounts pattern); a missing id is a 422 before any line is
    written."""
    cost_center_ids = {
        line.cost_center_id for line in payload.lines if line.cost_center_id is not None
    }
    missing_cost_centers = cost_center_ids - await queries.existing_cost_center_ids(
        session, tenant_id, cost_center_ids
    )
    if missing_cost_centers:
        raise ValidationFailedError(
            message="A journal line references an unknown cost centre",
            code="finance.journal_cost_center_not_found",
            details={"cost_center_ids": sorted(str(c) for c in missing_cost_centers)},
        )
    profit_center_ids = {
        line.profit_center_id for line in payload.lines if line.profit_center_id is not None
    }
    missing_profit_centers = profit_center_ids - await queries.existing_profit_center_ids(
        session, tenant_id, profit_center_ids
    )
    if missing_profit_centers:
        raise ValidationFailedError(
            message="A journal line references an unknown profit centre",
            code="finance.journal_profit_center_not_found",
            details={"profit_center_ids": sorted(str(p) for p in missing_profit_centers)},
        )

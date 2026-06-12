"""Purpose-keyed account wiring (D-019), split out of service/fx.py to keep both under the cap.

A ``PostingDefault`` maps a purpose string (e.g. ``'fx_unrealized_gain'``) to a GL account, so any
flow that must post to a CONFIGURED account resolves it data-driven rather than hard-coding an
account code. The FX engine is the first consumer (gain/loss + revaluation adjustment); AP/AR and
inventory COGS reuse the same mechanism in later phases. Kept a distinct concern file (not in
fx.py) because it is account wiring, not FX rate math.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.modules.finance.constants import FX_POSTING_PURPOSES
from app.modules.finance.models import Account, PostingDefault


async def get_posting_default(
    session: AsyncSession, tenant_id: uuid.UUID, purpose: str
) -> uuid.UUID:
    """Resolve a purpose string to its mapped account id (D-019). Raises a clear 422 when the
    purpose is unmapped — a flow that must post to a configured account (FX gain/loss, revaluation
    adjustment) fails loud rather than guessing. The data-driven account wiring reused later by
    AP/AR and inventory COGS."""
    account_id = (
        await session.execute(
            select(PostingDefault.account_id).where(
                PostingDefault.tenant_id == tenant_id, PostingDefault.purpose == purpose
            )
        )
    ).scalar_one_or_none()
    if account_id is None:
        raise ValidationFailedError(
            message=f"No account is mapped for posting purpose '{purpose}'",
            code="finance.posting_default_unmapped",
            details={"purpose": purpose},
        )
    return account_id


async def set_posting_default(
    session: AsyncSession, tenant_id: uuid.UUID, purpose: str, account_id: uuid.UUID
) -> PostingDefault:
    """Map (or remap) a purpose to an account (D-019). Validates the purpose is a known FX purpose
    and the account exists in the tenant + is postable; upserts the (tenant, purpose) row.
    Loaded-object mutation on remap so audit captures the change."""
    if purpose not in FX_POSTING_PURPOSES:
        raise ValidationFailedError(
            message=f"Unknown posting purpose '{purpose}'",
            code="finance.posting_default_unknown_purpose",
            details={"purpose": purpose},
        )
    account = (
        await session.execute(
            select(Account).where(Account.tenant_id == tenant_id, Account.id == account_id)
        )
    ).scalar_one_or_none()
    if account is None:
        raise ValidationFailedError(
            message="The mapped account does not exist in this tenant",
            code="finance.posting_default_account_not_found",
            details={"account_id": str(account_id)},
        )
    if not account.is_postable:
        raise ValidationFailedError(
            message="A posting default must map to a postable account",
            code="finance.posting_default_account_not_postable",
            details={"account_id": str(account_id)},
        )
    existing = (
        await session.execute(
            select(PostingDefault).where(
                PostingDefault.tenant_id == tenant_id, PostingDefault.purpose == purpose
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.account_id = account_id
        await session.flush()
        return existing
    default = PostingDefault(tenant_id=tenant_id, purpose=purpose, account_id=account_id)
    session.add(default)
    await session.flush()
    return default


async def list_posting_defaults(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[PostingDefault]:
    stmt = (
        select(PostingDefault)
        .where(PostingDefault.tenant_id == tenant_id)
        .order_by(PostingDefault.purpose)
    )
    return list((await session.execute(stmt)).scalars().all())

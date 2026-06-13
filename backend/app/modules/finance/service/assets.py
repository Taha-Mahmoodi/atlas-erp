"""Asset register lifecycle (PLAN 4.10): create/update DRAFT assets, activate, read.

An asset is DRAFT until ``activate_asset`` claims its gapless AST number (the D-012
claim-at-permanence moment) and flips it ACTIVE — only ACTIVE assets are selected by
depreciation runs (service/depreciation.py). Activation with ``capitalize=True`` ALSO posts
the acquisition journal (Dr asset account / Cr the ``asset_acquisition_clearing`` posting
default, D-029-style data-driven wiring); ``capitalize=False`` just activates, for assets
entered with opening balances already on the books. Account links are validated by TYPE
(asset + accumulated-depreciation accounts are ASSET; the expense account is EXPENSE) and
postability; the cost-centre dimension is validated like a journal line's (D-022).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.money import currency_decimals, quantize_money
from app.core.numbering import claim_number, ensure_sequence
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.finance import queries
from app.modules.finance.assets_schemas import AssetCreate, AssetUpdate
from app.modules.finance.constants import (
    ASSET_ACQUISITION_CLEARING,
    ASSET_DOC_TYPE,
    ASSET_NUMBER_PADDING,
    ASSET_NUMBER_PREFIX,
    ASSET_POSTS_LINK,
    ASSET_SEQUENCE_NAME,
    AccountType,
    AssetStatus,
    DepreciationMethod,
    DocumentType,
)
from app.modules.finance.models import Account, Asset
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service.fx import functional_currency_or_none
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.finance.service.posting_defaults import get_posting_default

# (field name, expected account type) for the three account links.
_ACCOUNT_RULES: tuple[tuple[str, AccountType], ...] = (
    ("asset_account_id", AccountType.ASSET),
    ("accumulated_depreciation_account_id", AccountType.ASSET),
    ("depreciation_expense_account_id", AccountType.EXPENSE),
)


async def _require_typed_account(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    expected_type: AccountType,
    field: str,
) -> None:
    """The account must exist in the tenant, be postable, and carry the expected type —
    the service-level half of the composite FK (which cannot check type/postability)."""
    account = (
        await session.execute(
            select(Account).where(Account.tenant_id == tenant_id, Account.id == account_id)
        )
    ).scalar_one_or_none()
    if account is None or not account.is_postable or account.account_type != expected_type.value:
        raise ValidationFailedError(
            message=f"{field} must reference a postable {expected_type.value} account",
            code="finance.asset_account_invalid",
            details={"field": field, "account_id": str(account_id)},
        )


def _validate_method(method: str, declining_rate_percent: Decimal | None) -> None:
    """DECLINING_BALANCE requires a rate in (0, 100]; STRAIGHT_LINE must not carry one."""
    if method == DepreciationMethod.DECLINING_BALANCE.value:
        rate = declining_rate_percent
        if rate is None or not Decimal(0) < rate <= Decimal(100):
            raise ValidationFailedError(
                message="declining_rate_percent is required (0 < rate <= 100) for the "
                "declining-balance method",
                code="finance.asset_declining_rate_required",
            )
    elif declining_rate_percent is not None:
        raise ValidationFailedError(
            message="declining_rate_percent only applies to the declining-balance method",
            code="finance.asset_declining_rate_not_applicable",
        )


async def _validate_asset_fields(
    session: AsyncSession, tenant_id: uuid.UUID, asset: Asset
) -> None:
    """Cross-field + reference validation shared by create and update."""
    cost = Decimal(str(asset.acquisition_cost))
    salvage = Decimal(str(asset.salvage_value))
    if salvage >= cost:
        raise ValidationFailedError(
            message="salvage_value must be less than acquisition_cost",
            code="finance.asset_salvage_exceeds_cost",
            details={"acquisition_cost": str(cost), "salvage_value": str(salvage)},
        )
    _validate_method(asset.depreciation_method, asset.declining_rate_percent)
    for field, expected in _ACCOUNT_RULES:
        await _require_typed_account(session, tenant_id, getattr(asset, field), expected, field)
    if asset.cost_center_id is not None and not await queries.cost_center_exists(
        session, tenant_id, asset.cost_center_id
    ):
        raise ValidationFailedError(
            message="The cost centre does not exist in this tenant",
            code="finance.asset_cost_center_not_found",
            details={"cost_center_id": str(asset.cost_center_id)},
        )


async def create_asset(
    session: AsyncSession, tenant_id: uuid.UUID, payload: AssetCreate
) -> Asset:
    """Create a DRAFT asset (PLAN 4.10). Registers the document with doc_number NULL (the AST
    number is claimed at activation, D-012); amounts quantize to the asset currency's minor
    unit (D-015). Caller commits via uow."""
    currency = (
        payload.currency_code or await functional_currency_or_none(session, tenant_id) or "USD"
    )
    decimals = currency_decimals(currency)
    asset_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        ASSET_DOC_TYPE,
        asset_id,
        doc_number=None,
        status=AssetStatus.DRAFT.value,
    )
    asset = Asset(
        id=asset_id,
        tenant_id=tenant_id,
        document_id=document.id,
        name=payload.name,
        description=payload.description,
        acquisition_date=payload.acquisition_date,
        acquisition_cost=quantize_money(payload.acquisition_cost, decimals),
        salvage_value=quantize_money(payload.salvage_value, decimals),
        useful_life_months=payload.useful_life_months,
        depreciation_method=DepreciationMethod(payload.depreciation_method).value,
        declining_rate_percent=payload.declining_rate_percent,
        status=AssetStatus.DRAFT.value,
        asset_account_id=payload.asset_account_id,
        accumulated_depreciation_account_id=payload.accumulated_depreciation_account_id,
        depreciation_expense_account_id=payload.depreciation_expense_account_id,
        cost_center_id=payload.cost_center_id,
        currency_code=currency,
    )
    await _validate_asset_fields(session, tenant_id, asset)
    session.add(asset)
    await session.flush()
    return asset


async def update_asset(
    session: AsyncSession, tenant_id: uuid.UUID, asset_id: uuid.UUID, payload: AssetUpdate
) -> Asset:
    """Patch a DRAFT asset (409 once activated — an activated asset is on the books and only
    changes through postings). Loaded-object mutation so audit captures the diff (D-010)."""
    asset = await get_asset(session, tenant_id, asset_id)
    if asset.status != AssetStatus.DRAFT.value:
        raise ConflictError(
            message="Only a draft asset can be edited",
            code="finance.asset_not_draft",
            details={"status": asset.status},
        )
    changes = payload.model_dump(exclude_unset=True)
    decimals = currency_decimals(asset.currency_code)
    for field, value in changes.items():
        if field in ("acquisition_cost", "salvage_value") and value is not None:
            value = quantize_money(value, decimals)
        if field == "depreciation_method" and value is not None:
            value = DepreciationMethod(value).value
        setattr(asset, field, value)
    await _validate_asset_fields(session, tenant_id, asset)
    await session.flush()
    return asset


async def get_asset(session: AsyncSession, tenant_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    asset = await session.get(Asset, asset_id)
    if asset is None or asset.tenant_id != tenant_id:
        raise NotFoundError(message="Asset not found", code="finance.asset_not_found")
    return asset


async def list_assets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
    status: str | None = None,
) -> Page[Asset]:
    """Keyset-paginated assets, newest acquisition first, optionally filtered by status
    (covered by the (tenant_id, status) index)."""
    stmt = select(Asset).where(Asset.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(Asset.status == AssetStatus(status).value)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Asset.acquisition_date, SortDirection.DESC)],
        pk=Asset.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status),
    )


async def activate_asset(
    session: AsyncSession, tenant_id: uuid.UUID, asset_id: uuid.UUID, *, capitalize: bool
) -> Asset:
    """Activate a DRAFT asset (PLAN 4.10): claim the gapless AST number (D-012) and flip the
    status to ACTIVE. With ``capitalize=True`` also post the acquisition journal — Dr the
    asset's balance-sheet account / Cr the ``asset_acquisition_clearing`` posting default for
    the acquisition cost, dated ``acquisition_date`` (must fall in an OPEN period; the period
    triggers backstop) — and link asset->'posts'->entry in docflow. With ``capitalize=False``
    the balance is assumed already on the books (opening-balance assets). The HTTP endpoint
    is idempotent (D-013); a fresh activate on a non-draft asset is a 409. Caller commits via
    uow."""
    asset = await get_asset(session, tenant_id, asset_id)
    if asset.status != AssetStatus.DRAFT.value:
        raise ConflictError(
            message="Only a draft asset can be activated",
            code="finance.asset_not_draft",
            details={"status": asset.status},
        )

    await ensure_sequence(
        session,
        tenant_id,
        ASSET_SEQUENCE_NAME,
        ASSET_NUMBER_PREFIX,
        ASSET_NUMBER_PADDING,
        year_reset=True,
    )
    asset_number = await claim_number(
        session, tenant_id, ASSET_SEQUENCE_NAME, on_date=asset.acquisition_date
    )
    asset.asset_number = asset_number
    asset.status = AssetStatus.ACTIVE.value

    if capitalize:
        clearing_account_id = await get_posting_default(
            session, tenant_id, ASSET_ACQUISITION_CLEARING
        )
        cost = Decimal(str(asset.acquisition_cost))
        entry = await create_draft_entry(
            session,
            tenant_id,
            JournalEntryCreate(
                posting_date=asset.acquisition_date,
                currency_code=asset.currency_code,
                description=f"Asset acquisition {asset_number}",
                document_type=DocumentType.JOURNAL,
                lines=[
                    JournalLineCreate(
                        account_id=asset.asset_account_id,
                        description=f"Capitalize {asset.name}",
                        transaction_debit_amount=cost,
                        cost_center_id=asset.cost_center_id,
                    ),
                    JournalLineCreate(
                        account_id=clearing_account_id,
                        description=f"Acquisition clearing {asset_number}",
                        transaction_credit_amount=cost,
                    ),
                ],
            ),
        )
        await post_entry(session, tenant_id, entry.id)
        asset.capitalized_journal_entry_id = entry.id
        await docflow.link_documents(
            session,
            tenant_id,
            predecessor=asset.document_id,
            successor=entry.document_id,
            link_type=ASSET_POSTS_LINK,
        )

    await session.flush()
    await docflow.set_document_status(
        session,
        tenant_id,
        asset.document_id,
        status=AssetStatus.ACTIVE.value,
        doc_number=asset_number,
    )
    return asset

"""Asset register lifecycle (PLAN 4.10): create/update validation, activation + the AST
number claim, and the capitalize=True acquisition journal — through the real service layer."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.docflow import DocumentLink
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.assets_schemas import AssetCreate, AssetUpdate
from app.modules.finance.constants import (
    AssetStatus,
    DepreciationMethod,
    EntryStatus,
)
from app.modules.finance.models import Asset, JournalLine
from tests.modules.finance.factories_assets import AssetSetup


def _payload(setup: AssetSetup, **overrides) -> AssetCreate:
    base: dict = {
        "name": "CNC Lathe",
        "acquisition_date": date(2026, 1, 15),
        "acquisition_cost": Decimal("12000"),
        "salvage_value": Decimal("0"),
        "useful_life_months": 12,
        "depreciation_method": DepreciationMethod.STRAIGHT_LINE,
        "asset_account_id": setup.accounts["1500"],
        "accumulated_depreciation_account_id": setup.accounts["1510"],
        "depreciation_expense_account_id": setup.accounts["5100"],
        "currency_code": "USD",
    }
    base.update(overrides)
    return AssetCreate(**base)


async def _create(db_session: AsyncSession, setup: AssetSetup, **overrides) -> Asset:
    with tenant_context(setup.tenant_id):
        asset = await service.create_asset(
            db_session, setup.tenant_id, _payload(setup, **overrides)
        )
        await db_session.commit()
    return asset


async def test_create_asset_is_draft_and_unnumbered(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    """A new asset is DRAFT with no number (claimed at activation, D-012) and a registry
    entry; amounts quantize to the currency's minor unit (D-015)."""
    asset = await _create(db_session, asset_setup, acquisition_cost=Decimal("12000.005"))
    assert asset.status == AssetStatus.DRAFT.value
    assert asset.asset_number is None
    assert asset.document_id is not None
    assert Decimal(str(asset.acquisition_cost)) == Decimal("12000.01")


async def test_create_asset_rejects_salvage_at_or_above_cost(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    with tenant_context(asset_setup.tenant_id), pytest.raises(ValidationFailedError) as err:
        await service.create_asset(
            db_session,
            asset_setup.tenant_id,
            _payload(asset_setup, salvage_value=Decimal("12000")),
        )
    assert err.value.code == "finance.asset_salvage_exceeds_cost"


async def test_create_asset_declining_rate_pairing(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    """DECLINING_BALANCE requires a rate in (0, 100]; STRAIGHT_LINE must not carry one."""
    with tenant_context(asset_setup.tenant_id):
        with pytest.raises(ValidationFailedError) as missing:
            await service.create_asset(
                db_session,
                asset_setup.tenant_id,
                _payload(
                    asset_setup, depreciation_method=DepreciationMethod.DECLINING_BALANCE
                ),
            )
        with pytest.raises(ValidationFailedError) as out_of_range:
            await service.create_asset(
                db_session,
                asset_setup.tenant_id,
                _payload(
                    asset_setup,
                    depreciation_method=DepreciationMethod.DECLINING_BALANCE,
                    declining_rate_percent=Decimal("150"),
                ),
            )
        with pytest.raises(ValidationFailedError) as not_applicable:
            await service.create_asset(
                db_session,
                asset_setup.tenant_id,
                _payload(asset_setup, declining_rate_percent=Decimal("20")),
            )
    assert missing.value.code == "finance.asset_declining_rate_required"
    assert out_of_range.value.code == "finance.asset_declining_rate_required"
    assert not_applicable.value.code == "finance.asset_declining_rate_not_applicable"


async def test_create_asset_validates_account_types(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    """Asset + accumulated accounts must be ASSET, the expense account EXPENSE, all existing
    in the tenant."""
    cases = (
        {"asset_account_id": asset_setup.accounts["5100"]},  # EXPENSE as BS account
        {"accumulated_depreciation_account_id": asset_setup.accounts["2900"]},  # LIABILITY
        {"depreciation_expense_account_id": asset_setup.accounts["1500"]},  # ASSET as expense
        {"asset_account_id": uuid.uuid4()},  # unknown account
    )
    with tenant_context(asset_setup.tenant_id):
        for overrides in cases:
            with pytest.raises(ValidationFailedError) as err:
                await service.create_asset(
                    db_session, asset_setup.tenant_id, _payload(asset_setup, **overrides)
                )
            assert err.value.code == "finance.asset_account_invalid"


async def test_create_asset_validates_cost_center_dimension(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    with tenant_context(asset_setup.tenant_id), pytest.raises(ValidationFailedError) as err:
        await service.create_asset(
            db_session,
            asset_setup.tenant_id,
            _payload(asset_setup, cost_center_id=uuid.uuid4()),
        )
    assert err.value.code == "finance.asset_cost_center_not_found"


async def test_update_asset_draft_only_and_revalidates(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    asset = await _create(db_session, asset_setup)
    with tenant_context(asset_setup.tenant_id):
        updated = await service.update_asset(
            db_session, asset_setup.tenant_id, asset.id, AssetUpdate(name="Mill")
        )
        assert updated.name == "Mill"
        # Cross-field rules re-run on the patched combination.
        with pytest.raises(ValidationFailedError) as err:
            await service.update_asset(
                db_session,
                asset_setup.tenant_id,
                asset.id,
                AssetUpdate(salvage_value=Decimal("99999")),
            )
        assert err.value.code == "finance.asset_salvage_exceeds_cost"
        await service.activate_asset(
            db_session, asset_setup.tenant_id, asset.id, capitalize=False
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as conflict:
            await service.update_asset(
                db_session, asset_setup.tenant_id, asset.id, AssetUpdate(name="Too late")
            )
    assert conflict.value.code == "finance.asset_not_draft"


async def test_activation_claims_gapless_numbers(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    """Activation claims AST-2026-00001, 00002, ... and flips ACTIVE; capitalize=False posts
    no journal (opening-balance assets are assumed already on the books)."""
    first = await _create(db_session, asset_setup)
    second = await _create(db_session, asset_setup, name="Drill press")
    with tenant_context(asset_setup.tenant_id):
        activated_first = await service.activate_asset(
            db_session, asset_setup.tenant_id, first.id, capitalize=False
        )
        activated_second = await service.activate_asset(
            db_session, asset_setup.tenant_id, second.id, capitalize=False
        )
        await db_session.commit()
    assert activated_first.asset_number == "AST-2026-00001"
    assert activated_second.asset_number == "AST-2026-00002"
    assert activated_first.status == AssetStatus.ACTIVE.value
    assert activated_first.capitalized_journal_entry_id is None
    with tenant_context(asset_setup.tenant_id), pytest.raises(ConflictError) as err:
        await service.activate_asset(
            db_session, asset_setup.tenant_id, first.id, capitalize=False
        )
    assert err.value.code == "finance.asset_not_draft"


async def test_activation_with_capitalize_posts_acquisition_journal(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    """capitalize=True posts Dr asset account / Cr acquisition clearing for the cost — a
    balanced POSTED entry — and links asset->'posts'->entry in docflow (D-012)."""
    asset = await _create(db_session, asset_setup)
    with tenant_context(asset_setup.tenant_id):
        activated = await service.activate_asset(
            db_session, asset_setup.tenant_id, asset.id, capitalize=True
        )
        await db_session.commit()
        assert activated.capitalized_journal_entry_id is not None
        entry = await service.get_entry(
            db_session, asset_setup.tenant_id, activated.capitalized_journal_entry_id
        )
        assert entry.status == EntryStatus.POSTED.value
        lines = list(
            (
                await db_session.execute(
                    select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
                )
            )
            .scalars()
            .all()
        )
        by_account = {line.account_id: line for line in lines}
        debit = by_account[asset_setup.accounts["1500"]]
        credit = by_account[asset_setup.accounts["2900"]]
        assert Decimal(str(debit.transaction_debit_amount)) == Decimal("12000.00")
        assert Decimal(str(credit.transaction_credit_amount)) == Decimal("12000.00")
        link = (
            await db_session.execute(
                select(DocumentLink).where(
                    DocumentLink.predecessor_document_id == activated.document_id,
                    DocumentLink.successor_document_id == entry.document_id,
                )
            )
        ).scalar_one()
        assert link.link_type == "posts"


async def test_activation_capitalize_requires_clearing_default(
    db_session: AsyncSession, journal_setup
) -> None:
    """Without the asset_acquisition_clearing posting default, capitalize=True fails loud
    (422) — account wiring is configuration, never guessed (D-019 pattern)."""
    setup = AssetSetup(
        tenant_id=journal_setup.tenant_id,
        accounts=journal_setup.accounts,
        fiscal_year_id=journal_setup.fiscal_year_id,
    )
    with tenant_context(setup.tenant_id):
        asset = await service.create_asset(
            db_session,
            setup.tenant_id,
            AssetCreate(
                name="Unwired",
                acquisition_date=date(2026, 1, 15),
                acquisition_cost=Decimal("100"),
                useful_life_months=10,
                depreciation_method=DepreciationMethod.STRAIGHT_LINE,
                asset_account_id=setup.accounts["1000"],
                accumulated_depreciation_account_id=setup.accounts["1000"],
                depreciation_expense_account_id=setup.accounts["5000"],
                currency_code="USD",
            ),
        )
        with pytest.raises(ValidationFailedError) as err:
            await service.activate_asset(
                db_session, setup.tenant_id, asset.id, capitalize=True
            )
    assert err.value.code == "finance.posting_default_unmapped"

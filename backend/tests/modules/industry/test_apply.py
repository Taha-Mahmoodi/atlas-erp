"""PLAN 14.1 / D-060: applying a template to a fresh tenant instantiates every slice in ONE
transaction, idempotently, via the event-bus provisioning seam.

Proves: a service-layer apply (inside run_in_uow, the router's path) creates the finance slice (COA
accounts + groups, tax codes, currencies — via the finance handler), the inventory slice (UoMs +
item categories — via the inventory handler), the procurement slice (approval presets — via the
procurement handler), the core/admin slices (custom-field defs, numbering sequences, terminology +
module-toggle TenantSettings — applied directly by the loader), and the industry config record;
re-apply is idempotent (no duplicates); a different template is rejected; a handler failure rolls
the WHOLE apply back (one transaction). Handlers are wired by the autouse conftest fixture.
"""


import pytest
from sqlalchemy import func, select

from app.core.custom_fields import CustomFieldDef
from app.core.events import run_in_uow
from app.core.exceptions import ConflictError
from app.core.numbering import NumberSequence
from app.core.tenancy import system_context
from app.modules.admin.models import TenantSetting
from app.modules.finance.models import Account, AccountGroup, Currency, TaxCode
from app.modules.industry.constants import (
    MODULE_TOGGLES_SETTING_KEY,
    TERMINOLOGY_SETTING_KEY,
)
from app.modules.industry.loader import apply_template
from app.modules.industry.models import TenantIndustryConfig
from app.modules.inventory.models import ItemCategory, Uom
from app.modules.procurement.models import ApprovalRule


async def _apply(session, tenant_id, name):
    async def _work() -> None:
        await apply_template(session, tenant_id, name)

    await run_in_uow(session, _work)


async def _count(session, model, tenant_id) -> int:
    with system_context():
        stmt = select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
        return (await session.execute(stmt)).scalar_one()


async def test_apply_creates_every_slice(db_session, tenant_a):
    await _apply(db_session, tenant_a, "manufacturing")
    template_accounts = 13  # manufacturing COA account count
    # Finance slice (via the finance handler).
    assert await _count(db_session, Account, tenant_a) == template_accounts
    assert await _count(db_session, AccountGroup, tenant_a) == 5
    assert await _count(db_session, TaxCode, tenant_a) == 2
    assert await _count(db_session, Currency, tenant_a) == 1
    # Inventory slice (via the inventory handler).
    assert await _count(db_session, Uom, tenant_a) == 6
    assert await _count(db_session, ItemCategory, tenant_a) == 3
    # Procurement slice (via the procurement handler) — PO + requisition thresholds.
    assert await _count(db_session, ApprovalRule, tenant_a) == 2
    # Core slice: custom-field defs + numbering sequences (loader-applied directly).
    assert await _count(db_session, CustomFieldDef, tenant_a) == 1
    assert await _count(db_session, NumberSequence, tenant_a) == 4
    # The industry config record.
    assert await _count(db_session, TenantIndustryConfig, tenant_a) == 1


async def test_apply_sets_one_functional_currency(db_session, tenant_a):
    await _apply(db_session, tenant_a, "manufacturing")
    with system_context():
        functional = (
            await db_session.execute(
                select(Currency.code).where(
                    Currency.tenant_id == tenant_a, Currency.is_functional.is_(True)
                )
            )
        ).scalars().all()
    assert functional == ["USD"]


async def test_apply_sets_terminology_and_module_toggle_settings(db_session, tenant_a):
    await _apply(db_session, tenant_a, "healthcare")
    with system_context():
        rows = {
            key: value
            for key, value in (
                await db_session.execute(
                    select(TenantSetting.key, TenantSetting.value).where(
                        TenantSetting.tenant_id == tenant_a
                    )
                )
            ).all()
        }
    assert rows[TERMINOLOGY_SETTING_KEY]["customer"] == "Patient"
    assert rows[MODULE_TOGGLES_SETTING_KEY]["manufacturing"] is False


async def test_retail_registers_barcode_custom_field(db_session, tenant_a):
    await _apply(db_session, tenant_a, "retail")
    with system_context():
        keys = (
            await db_session.execute(
                select(CustomFieldDef.field_key).where(
                    CustomFieldDef.tenant_id == tenant_a,
                    CustomFieldDef.entity_key == "inventory.item",
                )
            )
        ).scalars().all()
    assert "barcode" in keys


async def test_retail_categories_default_to_fifo(db_session, tenant_a):
    await _apply(db_session, tenant_a, "retail")
    with system_context():
        methods = (
            await db_session.execute(
                select(ItemCategory.default_costing_method).where(
                    ItemCategory.tenant_id == tenant_a
                )
            )
        ).scalars().all()
    assert set(methods) == {"FIFO"}


async def test_reapply_same_template_is_idempotent(db_session, tenant_a):
    await _apply(db_session, tenant_a, "manufacturing")
    await _apply(db_session, tenant_a, "manufacturing")
    # No duplicates across any slice on the second apply.
    assert await _count(db_session, Account, tenant_a) == 13
    assert await _count(db_session, Uom, tenant_a) == 6
    assert await _count(db_session, TaxCode, tenant_a) == 2
    assert await _count(db_session, Currency, tenant_a) == 1
    assert await _count(db_session, ApprovalRule, tenant_a) == 2
    assert await _count(db_session, CustomFieldDef, tenant_a) == 1
    assert await _count(db_session, NumberSequence, tenant_a) == 4
    assert await _count(db_session, TenantIndustryConfig, tenant_a) == 1


async def test_hospitality_template_applies_idempotently(db_session, tenant_a):
    """PLAN 19.1: the SIXTH template goes through the same apply/idempotency path as the five —
    applying it twice leaves exactly the state one apply leaves, and its F&B slice (FIFO categories,
    the Guest Ledger control account) is really there."""
    await _apply(db_session, tenant_a, "hospitality")
    first = {
        model: await _count(db_session, model, tenant_a)
        for model in (Account, Uom, ItemCategory, TaxCode, Currency, ApprovalRule, CustomFieldDef)
    }
    await _apply(db_session, tenant_a, "hospitality")
    second = {
        model: await _count(db_session, model, tenant_a)
        for model in (Account, Uom, ItemCategory, TaxCode, Currency, ApprovalRule, CustomFieldDef)
    }
    assert first == second
    assert await _count(db_session, TenantIndustryConfig, tenant_a) == 1
    with system_context():
        names = (
            await db_session.execute(
                select(Account.name).where(Account.tenant_id == tenant_a)
            )
        ).scalars().all()
        methods = (
            await db_session.execute(
                select(ItemCategory.default_costing_method).where(
                    ItemCategory.tenant_id == tenant_a
                )
            )
        ).scalars().all()
    assert "Guest Ledger" in names
    assert set(methods) == {"FIFO"}


async def test_apply_different_template_is_rejected(db_session, tenant_a):
    await _apply(db_session, tenant_a, "manufacturing")
    with pytest.raises(ConflictError) as exc:
        await _apply(db_session, tenant_a, "retail")
    assert exc.value.code == "industry.template_conflict"


async def test_apply_is_tenant_scoped(db_session, tenant_a, tenant_b):
    await _apply(db_session, tenant_a, "manufacturing")
    # Tenant B got nothing.
    assert await _count(db_session, Account, tenant_b) == 0
    assert await _count(db_session, Uom, tenant_b) == 0
    assert await _count(db_session, TenantIndustryConfig, tenant_b) == 0


async def test_apply_is_one_transaction(db_session, tenant_a, monkeypatch):
    """A handler failure rolls the WHOLE apply back — no half-applied template persists (D-011)."""
    import app.modules.inventory.handlers as inv_handlers

    async def _boom(session, event):
        raise RuntimeError("inventory provisioning blew up")

    monkeypatch.setattr(inv_handlers, "provision_inventory_for_template", _boom)
    # Re-register so the patched handler is the one subscribed.
    from app.core.events import clear_subscriptions
    from app.main import register_event_handlers

    clear_subscriptions()
    register_event_handlers()

    with pytest.raises(RuntimeError):
        await _apply(db_session, tenant_a, "manufacturing")
    # The finance accounts the finance handler created, the config row, the custom-field defs — ALL
    # rolled back. Nothing from the apply persists.
    assert await _count(db_session, Account, tenant_a) == 0
    assert await _count(db_session, TenantIndustryConfig, tenant_a) == 0
    assert await _count(db_session, CustomFieldDef, tenant_a) == 0

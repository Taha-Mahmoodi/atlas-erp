"""Finance provisioning handler (PLAN 14.1 / D-060): the finance slice of an industry template.

Subscribes to the industry module's ``IndustryTemplateApplying`` event and creates finance's slice
of the template — currencies (one functional), the chart-of-accounts preset (groups + accounts) and
the default tax codes — IDEMPOTENTLY, in the SAME transaction as the apply (D-011 run_in_uow drains
before commit). This is the §5-clean provisioning seam: the INDUSTRY module never imports
finance/service; it publishes the event and finance reacts here, creating ITS OWN rows through its
own models (the inventory-COGS / payroll precedent — a publishing module never reaches across).

Idempotency (D-060): every create is SKIP-IF-EXISTS by code (the natural key), so re-applying the
same template never duplicates and a partly-applied template completes cleanly on a retry. Runs
under ``system_context`` (provisioning) so tenant_id is stamped explicitly on each row.

Registered via ``app.main.register_event_handlers`` (the D-011 seam), so the test harness
re-registers it after its per-test ``clear_subscriptions`` reset.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import system_context
from app.modules.finance.constants import AccountType, CashFlowCategory, normal_balance_for
from app.modules.finance.models import Account, AccountGroup, Currency, TaxCode
from app.modules.industry.events import IndustryTemplateApplying


async def provision_finance_for_template(
    session: AsyncSession, event: IndustryTemplateApplying
) -> None:
    """Create the finance slice (currencies + COA + tax codes) for an applied industry template
    (D-060), idempotently, in the apply's transaction."""
    template = event.template
    tenant_id = event.tenant_id
    with system_context():
        await _ensure_currencies(session, tenant_id, template)
        group_ids = await _ensure_account_groups(session, tenant_id, template)
        await _ensure_accounts(session, tenant_id, template, group_ids)
        await _ensure_tax_codes(session, tenant_id, template)


async def _ensure_currencies(
    session: AsyncSession, tenant_id, template: IndustryTemplateApplying
) -> None:
    for spec in template.currencies:
        existing = (
            await session.execute(
                select(Currency).where(
                    Currency.tenant_id == tenant_id, Currency.code == spec.code
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            Currency(
                tenant_id=tenant_id,
                code=spec.code,
                name=spec.name,
                decimal_places=spec.decimal_places,
                is_functional=spec.is_functional,
            )
        )
    await session.flush()


async def _ensure_account_groups(
    session: AsyncSession, tenant_id, template: IndustryTemplateApplying
) -> dict[str, object]:
    """Create the COA groups (parents before children — the templates list them top-down) and
    return a code -> id map the accounts use to resolve their group."""
    code_to_id: dict[str, object] = {}
    existing_rows = (
        await session.execute(
            select(AccountGroup.code, AccountGroup.id).where(
                AccountGroup.tenant_id == tenant_id
            )
        )
    ).all()
    code_to_id.update({code: gid for code, gid in existing_rows})
    for spec in template.chart_of_accounts.groups:
        if spec.code in code_to_id:
            continue
        parent_id = code_to_id.get(spec.parent_code) if spec.parent_code else None
        group = AccountGroup(
            tenant_id=tenant_id,
            code=spec.code,
            name=spec.name,
            parent_id=parent_id,
            sort_order=spec.sort_order,
        )
        session.add(group)
        await session.flush()
        code_to_id[spec.code] = group.id
    return code_to_id


async def _ensure_accounts(
    session: AsyncSession,
    tenant_id,
    template: IndustryTemplateApplying,
    group_ids: dict[str, object],
) -> None:
    existing_codes = {
        code
        for (code,) in (
            await session.execute(
                select(Account.code).where(Account.tenant_id == tenant_id)
            )
        ).all()
    }
    for spec in template.chart_of_accounts.accounts:
        if spec.code in existing_codes:
            continue
        account_type = AccountType(spec.account_type)
        cash_flow = (
            CashFlowCategory(spec.cash_flow_category).value
            if spec.cash_flow_category is not None
            else None
        )
        session.add(
            Account(
                tenant_id=tenant_id,
                code=spec.code,
                name=spec.name,
                account_type=account_type.value,
                normal_balance=normal_balance_for(account_type).value,
                is_postable=spec.is_postable,
                cash_flow_category=cash_flow,
                is_cash_equivalent=spec.is_cash_equivalent,
                account_group_id=group_ids.get(spec.group_code) if spec.group_code else None,
            )
        )
    await session.flush()


async def _ensure_tax_codes(
    session: AsyncSession, tenant_id, template: IndustryTemplateApplying
) -> None:
    existing_codes = {
        code
        for (code,) in (
            await session.execute(
                select(TaxCode.code).where(TaxCode.tenant_id == tenant_id)
            )
        ).all()
    }
    for spec in template.tax_codes:
        if spec.code in existing_codes:
            continue
        session.add(
            TaxCode(
                tenant_id=tenant_id,
                code=spec.code,
                name=spec.name,
                # rate_percent is a string in the template (D-015 no-float); MoneyType stores it
                # exactly as a Decimal.
                rate_percent=Decimal(spec.rate_percent),
                jurisdiction=spec.jurisdiction,
                is_inclusive=spec.is_inclusive,
            )
        )
    await session.flush()

"""Finance test data builders behind tests/modules/finance/conftest.py (issue #30).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy
stamping and audit fire exactly as in production. conftest.py keeps only the thin pytest
fixtures (STRUCTURE §6/§8.4); the 4.10 asset builders live in factories_assets.py (cap)."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service
from app.modules.finance.constants import (
    BANK_UNMATCHED_CLEARING,
    CO_ALLOCATION_CLEARING,
    CUSTOMER_ADVANCES,
    FX_REALIZED_GAIN,
    FX_REALIZED_LOSS,
    FX_REVALUATION_ADJUSTMENT,
    FX_UNREALIZED_GAIN,
    FX_UNREALIZED_LOSS,
    AccountType,
    RateKind,
)
from app.modules.finance.models import Account, FiscalYear
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate, TaxCodeCreate

# EVERY registered finance.* key (importing finance.constants above registers them), so a
# new finance permission is auto-granted to the full-rights principal (self-extending).
_FINANCE_KEYS = tuple(sorted(key for key in catalog_keys() if key.startswith("finance.")))

# A minimal but type-complete chart of accounts: one account per statement-deriving type.
_SMALL_COA: tuple[tuple[str, str, AccountType], ...] = (
    ("1000", "Cash", AccountType.ASSET),
    ("2000", "Accounts Payable", AccountType.LIABILITY),
    ("3000", "Share Capital", AccountType.EQUITY),
    ("4000", "Sales Revenue", AccountType.REVENUE),
    ("5000", "Cost of Goods Sold", AccountType.EXPENSE),
)


async def seed_small_coa(session: AsyncSession, tenant_id: uuid.UUID) -> list[Account]:
    """Create one account per account type through the real service (D-025)."""
    accounts: list[Account] = []
    with tenant_context(tenant_id):
        for code, name, account_type in _SMALL_COA:
            account = await service.create_account(
                session,
                tenant_id,
                AccountCreate(code=code, name=name, account_type=account_type),
            )
            accounts.append(account)
        await session.commit()
    return accounts


async def seed_fiscal_year(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str = "2026",
    start_date: date = date(2026, 1, 1),
) -> FiscalYear:
    """Create a 12-period fiscal year through the real service (D-025)."""
    with tenant_context(tenant_id):
        year = await service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code=code, name=f"FY{code}", start_date=start_date),
        )
        await session.commit()
    return year


@dataclass(frozen=True)
class JournalSetup:
    """A tenant ready to post: account ids by code + the open 2026 fiscal year id. Plain ids
    (not ORM objects) so a rollback — which expires every loaded ORM object — cannot break a
    follow-up payload with an out-of-greenlet lazy refresh."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    fiscal_year_id: uuid.UUID


async def build_journal_setup(session: AsyncSession, tenant_id: uuid.UUID) -> JournalSetup:
    """COA + open fiscal year — the precondition for posting (D-017)."""
    accounts = await seed_small_coa(session, tenant_id)
    year = await seed_fiscal_year(session, tenant_id)
    return JournalSetup(
        tenant_id=tenant_id,
        accounts={account.code: account.id for account in accounts},
        fiscal_year_id=year.id,
    )


@dataclass(frozen=True)
class ApSetup:
    """A tenant ready to bill + pay (PLAN 4.5): account ids by code (1000 bank, 2000 AP control,
    5000 expense, 6000 input-tax receivable), a wired 20% input tax code id, and the open 2026
    year. Plain ids so a rollback (expiring loaded objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    tax_code_id: uuid.UUID
    fiscal_year_id: uuid.UUID


async def build_ap_setup(session: AsyncSession, tenant_id: uuid.UUID) -> ApSetup:
    """COA + an input-tax receivable account + a 20% input tax code + open year (PLAN 4.5)."""
    accounts = await seed_small_coa(session, tenant_id)
    by_code = {a.code: a.id for a in accounts}
    with tenant_context(tenant_id):
        receivable = await service.create_account(
            session,
            tenant_id,
            AccountCreate(code="6000", name="Input VAT receivable", account_type=AccountType.ASSET),
        )
        by_code["6000"] = receivable.id
        tax_code = await service.create_tax_code(
            session,
            tenant_id,
            TaxCodeCreate(
                code="VAT20",
                name="Input VAT 20%",
                rate_percent=Decimal(20),
                tax_receivable_account_id=receivable.id,
            ),
        )
        await session.commit()
    year = await seed_fiscal_year(session, tenant_id)
    return ApSetup(
        tenant_id=tenant_id,
        accounts=by_code,
        tax_code_id=tax_code.id,
        fiscal_year_id=year.id,
    )


@dataclass(frozen=True)
class ArSetup:
    """A tenant ready to invoice + receive (PLAN 4.6): account ids by code (1000 bank, 1200 AR
    control, 4000 revenue, 2200 output-tax payable), a wired 20% output tax code id, and the open
    2026 year. Plain ids so a rollback (expiring loaded objects) can't break a follow-up payload."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    tax_code_id: uuid.UUID
    fiscal_year_id: uuid.UUID


async def build_ar_setup(session: AsyncSession, tenant_id: uuid.UUID) -> ArSetup:
    """COA + an AR control account + an output-tax payable account + a 20% output tax code + open
    year (PLAN 4.6). Reuses the small COA's 1000 (bank) and 4000 (revenue); adds 1200 (AR control)
    and 2200 (output-tax payable)."""
    accounts = await seed_small_coa(session, tenant_id)
    by_code = {a.code: a.id for a in accounts}
    with tenant_context(tenant_id):
        ar_control = await service.create_account(
            session,
            tenant_id,
            AccountCreate(code="1200", name="Accounts Receivable", account_type=AccountType.ASSET),
        )
        by_code["1200"] = ar_control.id
        payable = await service.create_account(
            session,
            tenant_id,
            AccountCreate(
                code="2200", name="Output VAT payable", account_type=AccountType.LIABILITY
            ),
        )
        by_code["2200"] = payable.id
        tax_code = await service.create_tax_code(
            session,
            tenant_id,
            TaxCodeCreate(
                code="VAT20O",
                name="Output VAT 20%",
                rate_percent=Decimal(20),
                tax_payable_account_id=payable.id,
            ),
        )
        await session.commit()
    year = await seed_fiscal_year(session, tenant_id)
    return ArSetup(
        tenant_id=tenant_id,
        accounts=by_code,
        tax_code_id=tax_code.id,
        fiscal_year_id=year.id,
    )


async def seed_advance_account(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """The advance-deposit control account an UNAPPLIED receipt credits, mapped to the
    ``customer_advances`` posting purpose (PLAN 20.4, D-086), and its id.

    "2100 Advance Deposits" is the hospitality template's own account: a LIABILITY, because money
    taken before arrival is owed back, not earned. Kept out of build_ar_setup so the mapping stays a
    deliberate act of a test that takes on-account money — an AR tenant that never configured one
    must still fail loud (finance.posting_default_unmapped)."""
    with tenant_context(tenant_id):
        account = await service.create_account(
            session,
            tenant_id,
            AccountCreate(
                code="2100", name="Advance Deposits", account_type=AccountType.LIABILITY
            ),
        )
        await service.set_posting_default(session, tenant_id, CUSTOMER_ADVANCES, account.id)
        await session.commit()
    return account.id


@dataclass(frozen=True)
class FxSetup:
    """A multi-currency-ready tenant (D-019): functional USD + foreign EUR, SPOT+CLOSING rates,
    FX posting defaults wired, a monetary EUR bank account, and the small COA + open 2026 year.
    Plain ids so a rollback (which expires loaded ORM objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    fiscal_year_id: uuid.UUID
    eur_bank_id: uuid.UUID


# FX posting-default accounts added to the small COA (one per FX purpose + the EUR bank).
_FX_ACCOUNTS: tuple[tuple[str, str, AccountType], ...] = (
    ("1100", "EUR Bank", AccountType.ASSET),
    ("7100", "FX Realized Gain", AccountType.REVENUE),
    ("7110", "FX Realized Loss", AccountType.EXPENSE),
    ("7200", "FX Unrealized Gain", AccountType.REVENUE),
    ("7210", "FX Unrealized Loss", AccountType.EXPENSE),
    ("1900", "FX Revaluation Adjustment", AccountType.ASSET),
)

# (rate_date, from, to, rate_type, rate) — USD is functional; EUR->USD direct pairs.
_FX_RATES: tuple[tuple[date, str, str, str, str], ...] = (
    (date(2026, 1, 1), "EUR", "USD", "SPOT", "1.10"),
    (date(2026, 3, 1), "EUR", "USD", "SPOT", "1.20"),
    (date(2026, 3, 31), "EUR", "USD", "CLOSING", "1.25"),
)


async def build_fx_setup(session: AsyncSession, tenant_id: uuid.UUID) -> FxSetup:
    """A tenant wired for multi-currency posting + revaluation (D-019)."""
    accounts = await seed_small_coa(session, tenant_id)
    by_code = {a.code: a.id for a in accounts}
    eur_bank_id = uuid.uuid4()
    with tenant_context(tenant_id):
        for code, name, atype in _FX_ACCOUNTS:
            is_eur_bank = code == "1100"
            account = await service.create_account(
                session,
                tenant_id,
                AccountCreate(
                    code=code,
                    name=name,
                    account_type=atype,
                    is_monetary=is_eur_bank,
                    currency_code="EUR" if is_eur_bank else None,
                ),
            )
            by_code[code] = account.id
            if is_eur_bank:
                eur_bank_id = account.id
        await service.create_currency(
            session, tenant_id, code="USD", name="US Dollar", is_functional=True
        )
        await service.create_currency(session, tenant_id, code="EUR", name="Euro")
        for rate_date, frm, to, rate_type, rate in _FX_RATES:
            await service.create_exchange_rate(
                session,
                tenant_id,
                rate_date=rate_date,
                from_currency_code=frm,
                to_currency_code=to,
                rate=Decimal(rate),
                rate_type=RateKind(rate_type),
            )
        for purpose, code in (
            (FX_REALIZED_GAIN, "7100"),
            (FX_REALIZED_LOSS, "7110"),
            (FX_UNREALIZED_GAIN, "7200"),
            (FX_UNREALIZED_LOSS, "7210"),
            (FX_REVALUATION_ADJUSTMENT, "1900"),
        ):
            await service.set_posting_default(session, tenant_id, purpose, by_code[code])
        await session.commit()
    year = await seed_fiscal_year(session, tenant_id)
    return FxSetup(
        tenant_id=tenant_id,
        accounts=by_code,
        fiscal_year_id=year.id,
        eur_bank_id=eur_bank_id,
    )


@dataclass(frozen=True)
class CoSetup:
    """A tenant ready for controlling (PLAN 4.7): the small COA + an expense account (5000) used to
    seed a source cost centre's balance + a dedicated cost-allocation clearing account (9000) wired
    as the ``cost_allocation`` posting default, three cost centres (SRC + three targets are created
    per-test), and the open 2026 fiscal year. Plain ids so a rollback (expiring loaded objects)
    cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    fiscal_year_id: uuid.UUID


async def build_co_setup(session: AsyncSession, tenant_id: uuid.UUID) -> CoSetup:
    """COA + a cost-allocation clearing account wired as the ``cost_allocation`` posting default +
    open 2026 year (PLAN 4.7)."""
    accounts = await seed_small_coa(session, tenant_id)
    by_code = {a.code: a.id for a in accounts}
    with tenant_context(tenant_id):
        clearing = await service.create_account(
            session,
            tenant_id,
            AccountCreate(
                code="9000",
                name="Cost Allocation Clearing",
                account_type=AccountType.EXPENSE,
            ),
        )
        by_code["9000"] = clearing.id
        await service.set_posting_default(session, tenant_id, CO_ALLOCATION_CLEARING, clearing.id)
        await session.commit()
    year = await seed_fiscal_year(session, tenant_id)
    return CoSetup(tenant_id=tenant_id, accounts=by_code, fiscal_year_id=year.id)


@dataclass(frozen=True)
class BankSetup:
    """A tenant ready for bank reconciliation (PLAN 4.9): the small COA + a cash-equivalent
    bank account (1010) + a suspense account (9100) wired as the ``bank_unmatched_clearing``
    posting default, and the open 2026 fiscal year. Plain ids so a rollback (expiring loaded
    objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    fiscal_year_id: uuid.UUID
    bank_account_id: uuid.UUID
    suspense_account_id: uuid.UUID


async def build_bank_setup(session: AsyncSession, tenant_id: uuid.UUID) -> BankSetup:
    """COA + a cash-equivalent bank account + the bank-clearing suspense default + open 2026
    year (PLAN 4.9). The 1000 Cash account from the small COA is deliberately NOT
    cash-equivalent, so the is_cash_equivalent import rule is actually exercised."""
    accounts = await seed_small_coa(session, tenant_id)
    by_code = {a.code: a.id for a in accounts}
    with tenant_context(tenant_id):
        bank = await service.create_account(
            session,
            tenant_id,
            AccountCreate(
                code="1010",
                name="Main Bank",
                account_type=AccountType.ASSET,
                is_cash_equivalent=True,
            ),
        )
        by_code["1010"] = bank.id
        suspense = await service.create_account(
            session,
            tenant_id,
            AccountCreate(
                code="9100",
                name="Bank Clearing Suspense",
                account_type=AccountType.EXPENSE,
            ),
        )
        by_code["9100"] = suspense.id
        await service.set_posting_default(session, tenant_id, BANK_UNMATCHED_CLEARING, suspense.id)
        await session.commit()
    year = await seed_fiscal_year(session, tenant_id)
    return BankSetup(
        tenant_id=tenant_id,
        accounts=by_code,
        fiscal_year_id=year.id,
        bank_account_id=bank.id,
        suspense_account_id=suspense.id,
    )


@dataclass(frozen=True)
class FinancePrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_finance_principal(
    session: AsyncSession,
    slug: str = "fin-acme",
    email: str = "cfo@fin-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _FINANCE_KEYS,
) -> FinancePrincipal:
    """Provision a tenant + user and grant a role with the finance permission keys through
    the real services (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Finance", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return FinancePrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )

"""Reporting test data builders behind tests/modules/reporting/conftest.py (STRUCTURE §6/§8.4).

Reporting is a READ-ONLY KPI aggregator over OTHER modules' queries (D-058), so its tests SEED
CROSS-MODULE data through the REAL service layers (D-025) and then assert the dashboard projects
each KPI correctly. Builders go through the owning module's service under the tenant context, so
tenancy stamping + audit fire exactly as in production.

``build_reporting_setup`` wires ONE tenant with EVERY KPI non-zero: a posted cash journal (cash
position), an open customer invoice (AR aging) + open vendor bill (AP aging), a posted WIP-clearing
journal (WIP), an on-hand stock receipt (inventory value), a confirmed sales order (open sales
orders), a sent purchase order (open purchase orders), and a delivered order whose delivery shipped
on time (OTD). ``create_reporting_principal`` mirrors the projects principal pattern with a narrowed
``keys`` grant for the role-based RBAC tests.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.rbac import sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service as finance_service
from app.modules.finance.constants import WIP_CLEARING, AccountType, DocumentType
from app.modules.finance.payables_schemas import VendorBillCreate, VendorBillLineCreate
from app.modules.finance.receivables_schemas import (
    CustomerInvoiceCreate,
    CustomerInvoiceLineCreate,
)
from app.modules.finance.schemas import (
    AccountCreate,
    FiscalYearCreate,
    JournalEntryCreate,
    JournalLineCreate,
)

# A COA broad enough for every finance-sourced KPI: a cash-equivalent bank (cash position), an
# expense + payable (the offsetting journal legs), an AR control + revenue + output-tax payable (the
# customer invoice), an input-tax receivable (the vendor bill), and a WIP-clearing account (WIP).
_COA: tuple[tuple[str, str, AccountType, bool], ...] = (
    ("1010", "Main Bank", AccountType.ASSET, True),  # is_cash_equivalent
    ("1200", "Accounts Receivable", AccountType.ASSET, False),
    ("1300", "Work in Process", AccountType.ASSET, False),
    ("1400", "Input VAT receivable", AccountType.ASSET, False),
    ("2000", "Accounts Payable", AccountType.LIABILITY, False),
    ("2200", "Output VAT payable", AccountType.LIABILITY, False),
    ("4000", "Revenue", AccountType.REVENUE, False),
    ("5000", "Operating Expense", AccountType.EXPENSE, False),
)


async def build_finance_base(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, uuid.UUID]:
    """A USD functional currency + the COA + the WIP-clearing posting default + an open 2026 year —
    the precondition for the finance-sourced KPIs (cash, AR, AP, WIP). Returns ids by code."""
    with tenant_context(tenant_id):
        await finance_service.create_currency(
            session, tenant_id, code="USD", name="US Dollar", is_functional=True
        )
        by_code: dict[str, uuid.UUID] = {}
        for code, name, account_type, is_cash in _COA:
            account = await finance_service.create_account(
                session,
                tenant_id,
                AccountCreate(
                    code=code,
                    name=name,
                    account_type=account_type,
                    is_cash_equivalent=is_cash,
                ),
            )
            by_code[code] = account.id
        # WIP balance reads the WIP-clearing posting default, so map it to the WIP account.
        await finance_service.set_posting_default(
            session, tenant_id, WIP_CLEARING, by_code["1300"]
        )
        await finance_service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await session.commit()
    return by_code


async def post_cash_journal(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    accounts: dict[str, uuid.UUID],
    amount: Decimal,
    *,
    posting_date: date = date(2026, 2, 1),
) -> None:
    """Post Dr 1010 cash / Cr 4000 revenue so the cash-equivalent bank carries ``amount`` — the
    cash-position KPI source (a posted journal to a cash account, D-058)."""
    await _post_balanced(
        session,
        tenant_id,
        debit_account=accounts["1010"],
        credit_account=accounts["4000"],
        amount=amount,
        posting_date=posting_date,
        description="Cash receipt",
    )


async def post_wip_journal(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    accounts: dict[str, uuid.UUID],
    amount: Decimal,
    *,
    wip_account_id: uuid.UUID,
    posting_date: date = date(2026, 2, 1),
) -> None:
    """Post Dr WIP-clearing / Cr 2000 payable so the WIP account carries ``amount`` — the WIP KPI
    source (the WIP-clearing balance, D-048/D-058). ``wip_account_id`` is the account mapped as the
    WIP-clearing posting default (its code differs between the standalone base and the combined
    setup), so the caller passes it explicitly rather than assuming a fixed code."""
    await _post_balanced(
        session,
        tenant_id,
        debit_account=wip_account_id,
        credit_account=accounts["2000"],
        amount=amount,
        posting_date=posting_date,
        description="Open WIP",
    )


async def _post_balanced(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    debit_account: uuid.UUID,
    credit_account: uuid.UUID,
    amount: Decimal,
    posting_date: date,
    description: str,
) -> None:
    """Create + post a balanced two-line journal entry through the real finance service (D-025)."""
    with tenant_context(tenant_id):
        entry = await finance_service.create_draft_entry(
            session,
            tenant_id,
            JournalEntryCreate(
                posting_date=posting_date,
                currency_code="USD",
                description=description,
                document_type=DocumentType.JOURNAL,
                lines=[
                    JournalLineCreate(
                        account_id=debit_account, transaction_debit_amount=amount
                    ),
                    JournalLineCreate(
                        account_id=credit_account, transaction_credit_amount=amount
                    ),
                ],
            ),
        )
        await finance_service.post_entry(session, tenant_id, entry.id)
        await session.commit()


async def post_open_customer_invoice(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    accounts: dict[str, uuid.UUID],
    net: Decimal,
    *,
    invoice_date: date = date(2026, 5, 1),
    due_date: date = date(2026, 5, 31),
) -> None:
    """Create + post a customer invoice with an open balance — the AR-aging KPI source. Posted on
    2026-05-01, due 2026-05-31, so as-of 2026-06-14 it lands in the 1-30-days bucket (D-058)."""
    payload = CustomerInvoiceCreate(
        partner_id=uuid.uuid4(),
        partner_name="Globex Inc",
        invoice_date=invoice_date,
        due_date=due_date,
        currency_code="USD",
        ar_account_id=accounts["1200"],
        description="Consulting",
        lines=[CustomerInvoiceLineCreate(account_id=accounts["4000"], net_amount=net)],
    )
    with tenant_context(tenant_id):
        invoice = await finance_service.create_customer_invoice(session, tenant_id, payload)
        await session.commit()

        async def work() -> None:
            await finance_service.post_customer_invoice(session, tenant_id, invoice.id)

        await run_in_uow(session, work)


async def post_open_vendor_bill(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    accounts: dict[str, uuid.UUID],
    net: Decimal,
    *,
    expense_account_id: uuid.UUID,
    bill_date: date = date(2026, 5, 1),
    due_date: date = date(2026, 5, 31),
) -> None:
    """Create + post a vendor bill with an open balance — the AP-aging KPI source. Posted on
    2026-05-01, due 2026-05-31, so as-of 2026-06-14 it lands in the 1-30-days bucket (D-058).
    ``expense_account_id`` is the bill-line expense account (its code differs between the standalone
    base and the combined setup), so the caller passes it explicitly."""
    payload = VendorBillCreate(
        partner_id=uuid.uuid4(),
        partner_name="Acme Supplies",
        bill_date=bill_date,
        due_date=due_date,
        currency_code="USD",
        ap_account_id=accounts["2000"],
        description="Materials",
        lines=[VendorBillLineCreate(account_id=expense_account_id, net_amount=net)],
    )
    with tenant_context(tenant_id):
        bill = await finance_service.create_vendor_bill(session, tenant_id, payload)
        await session.commit()

        async def work() -> None:
            await finance_service.post_vendor_bill(session, tenant_id, bill.id)

        await run_in_uow(session, work)


@dataclass(frozen=True)
class ReportingSetup:
    """A tenant with EVERY dashboard KPI non-zero (D-058) and the expected values the tests assert.
    Plain values so a rollback (expiring loaded ORM objects) cannot break a follow-up assertion."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    cash_position: Decimal
    ar_total: Decimal
    ap_total: Decimal
    wip_value: Decimal
    inventory_value: Decimal
    open_sales_count: int
    open_sales_total: Decimal
    open_po_count: int
    open_po_total: Decimal
    otd_on_time: int
    otd_total: int
    as_of: date


@dataclass(frozen=True)
class ReportingPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_reporting_principal(
    session: AsyncSession,
    *,
    slug: str = "rep-acme",
    email: str = "analyst@rep-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...],
) -> ReportingPrincipal:
    """Provision a tenant + user and grant a role with exactly ``keys`` through the real services
    (D-025) — ``keys`` is explicit so each role-based RBAC test grants precisely the keys it needs
    (the base dashboard key + a chosen subset of source read keys)."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Reporting", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return ReportingPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )

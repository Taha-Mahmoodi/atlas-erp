"""Cross-module reporting seeders + the combined ``build_reporting_setup`` (STRUCTURE §6/§8.4).

Split from ``factories.py`` (the finance-sourced seeders) to keep both under the 400-line cap. These
build the SALES / PROCUREMENT / INVENTORY KPI data and assemble the all-KPIs-non-zero tenant the
headline dashboard tests assert against — every value seeded through the OWNING module's service
(D-025). The foundation is the sales ``build_order_setup`` (it already provisions the USD currency,
the open 2026 fiscal year, the stock topology, the item + the customer), onto which the extra
finance accounts the finance KPIs need are layered with NON-COLLIDING codes (the stock setup owns
1300/5000/5900; reporting adds cash/AR/AP/WIP/revenue under different codes).
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.modules.finance import service as finance_service
from app.modules.finance.constants import WIP_CLEARING, AccountType
from app.modules.finance.schemas import AccountCreate
from app.modules.procurement import service as procurement_service
from app.modules.sales import service as sales_service
from app.modules.sales.schemas import (
    DeliveryCreate,
    DeliveryLineCreate,
    SalesOrderCreate,
    SalesOrderLineCreate,
)
from tests.modules.procurement.factories import build_approved_item, build_po, build_vendor
from tests.modules.reporting.factories import (
    ReportingSetup,
    post_cash_journal,
    post_open_customer_invoice,
    post_open_vendor_bill,
    post_wip_journal,
)
from tests.modules.sales.factories import (
    build_confirmed_order,
    build_order_setup,
    confirm_sales_order,
    seed_on_hand,
)

_AS_OF = date(2026, 6, 14)
# Finance accounts reporting adds on TOP of the stock setup's COA (which owns 1300/5000/5900) — all
# under codes the stock setup does not use, so create_account never hits a duplicate-code conflict.
_EXTRA_COA: tuple[tuple[str, str, AccountType, bool], ...] = (
    ("1010", "Main Bank", AccountType.ASSET, True),  # is_cash_equivalent
    ("1200", "Accounts Receivable", AccountType.ASSET, False),
    ("1310", "Work in Process", AccountType.ASSET, False),
    ("2000", "Accounts Payable", AccountType.LIABILITY, False),
    ("4000", "Revenue", AccountType.REVENUE, False),
)


async def _add_finance_accounts(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, uuid.UUID]:
    """Add the cash / AR / WIP / AP / revenue accounts the finance KPIs need (codes that do not
    collide with the stock setup's COA) + map the WIP-clearing posting default. Returns ids by code.
    """
    with tenant_context(tenant_id):
        by_code: dict[str, uuid.UUID] = {}
        for code, name, account_type, is_cash in _EXTRA_COA:
            account = await finance_service.create_account(
                session,
                tenant_id,
                AccountCreate(
                    code=code, name=name, account_type=account_type, is_cash_equivalent=is_cash
                ),
            )
            by_code[code] = account.id
        await finance_service.set_posting_default(
            session, tenant_id, WIP_CLEARING, by_code["1310"]
        )
        await session.commit()
    return by_code


async def seed_on_time_delivered_order(
    session: AsyncSession,
    order_setup,
    *,
    quantity: str = "3",
    unit_price: str = "10",
    requested_date: date = date(2026, 6, 30),
    delivery_date: date = date(2026, 6, 14),
) -> None:
    """Create → confirm → fully deliver an order whose ``delivery_date`` is on or before its
    ``requested_date`` — an ON-TIME delivery for the OTD KPI (D-058). Seeds the on-hand the delivery
    issues, then drives the real order → delivery flow (D-025). The default dates put delivery 2026-
    06-14 ahead of the 2026-06-30 promise (on time)."""
    await seed_on_hand(session, order_setup, "10")
    holder: dict[str, uuid.UUID] = {}

    async def create_work() -> None:
        with tenant_context(order_setup.tenant_id):
            order = await sales_service.create_sales_order(
                session,
                order_setup.tenant_id,
                SalesOrderCreate(
                    customer_id=order_setup.customer_id,
                    requested_date=requested_date,
                    lines=[
                        SalesOrderLineCreate(
                            item_id=order_setup.item_id,
                            quantity=Decimal(quantity),
                            uom_id=order_setup.uom_id,
                            unit_price=Decimal(unit_price),
                        )
                    ],
                ),
            )
            holder["order_id"] = order.id

    with tenant_context(order_setup.tenant_id):
        await run_in_uow(session, create_work)
    await confirm_sales_order(session, order_setup.tenant_id, holder["order_id"])

    with tenant_context(order_setup.tenant_id):
        lines = await sales_service.get_sales_order_lines(
            session, order_setup.tenant_id, holder["order_id"]
        )

    async def deliver_work() -> None:
        with tenant_context(order_setup.tenant_id):
            delivery = await sales_service.create_delivery(
                session,
                order_setup.tenant_id,
                DeliveryCreate(
                    sales_order_id=holder["order_id"],
                    warehouse_id=order_setup.warehouse_id,
                    delivery_date=delivery_date,
                    lines=[
                        DeliveryLineCreate(
                            sales_order_line_id=lines[0].id,
                            bin_id=order_setup.bin_id,
                            quantity=Decimal(quantity),
                        )
                    ],
                ),
            )
            holder["delivery_id"] = delivery.id

    with tenant_context(order_setup.tenant_id):
        await run_in_uow(session, deliver_work)

    async def post_work() -> None:
        with tenant_context(order_setup.tenant_id):
            await sales_service.post_delivery(
                session, order_setup.tenant_id, holder["delivery_id"]
            )

    with tenant_context(order_setup.tenant_id):
        await run_in_uow(session, post_work)


async def seed_open_purchase_order(
    session: AsyncSession,
    order_setup,
    *,
    quantity: str = "10",
    unit_cost: str = "5",
) -> Decimal:
    """Seed a SENT (open) purchase order for the setup's item (D-058): create a vendor, approve the
    item for it, create a DRAFT PO, then SEND it (no approval rule ⇒ auto-APPROVED → SENT). Returns
    the PO's total value. Reuses the setup's already-stocked item so no new inventory is needed."""
    vendor = await build_vendor(session, order_setup.tenant_id, vendor_code="REP-VEND")
    await build_approved_item(session, order_setup.tenant_id, vendor.id, order_setup.item_id)
    po = await build_po(
        session,
        order_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=order_setup.item_id,
        uom_id=order_setup.uom_id,
        quantity=quantity,
        unit_cost=unit_cost,
    )
    with tenant_context(order_setup.tenant_id):
        await procurement_service.send_purchase_order(session, order_setup.tenant_id, po.id)
        await session.commit()
        sent = await procurement_service.get_purchase_order(session, order_setup.tenant_id, po.id)
        return Decimal(str(sent.total_amount))


async def build_reporting_setup(
    session: AsyncSession, tenant_id: uuid.UUID
) -> ReportingSetup:
    """One tenant with EVERY dashboard KPI non-zero (D-058). The sales order-setup is the foundation
    (currency / year / stock / item / customer); reporting layers the finance accounts + posts the
    cash / WIP / AR / AP figures, seeds on-hand for inventory value, a confirmed sales order, a sent
    PO, and an on-time delivered order. Returns the expected KPI values for the assertions."""
    order_setup = await build_order_setup(session, tenant_id)
    accounts = await _add_finance_accounts(session, tenant_id)

    # Finance-sourced KPIs.
    cash = Decimal("1500.00")
    wip = Decimal("700.00")
    ar = Decimal("400.00")
    ap = Decimal("250.00")
    await post_cash_journal(session, tenant_id, accounts, cash)
    await post_wip_journal(session, tenant_id, accounts, wip, wip_account_id=accounts["1310"])
    await post_open_customer_invoice(session, tenant_id, accounts, ar)
    await post_open_vendor_bill(
        session, tenant_id, accounts, ap, expense_account_id=order_setup.cogs_account_id
    )

    # Inventory value: seed on-hand at a known unit cost (5 × 20 = 100).
    inventory_value = Decimal("100")
    await seed_on_hand_at_cost(session, order_setup, quantity="20", unit_cost="5")

    # Open sales order (confirmed-undelivered): 5 × 10 = 50.
    open_so = await build_confirmed_order(session, order_setup, quantity="5", unit_price="10")
    open_sales_total = Decimal(str(open_so.total_amount))

    # Open purchase order (sent): 10 × 5 = 50.
    open_po_total = await seed_open_purchase_order(
        session, order_setup, quantity="10", unit_cost="5"
    )

    # On-time delivered order (OTD numerator + denominator both 1).
    await seed_on_time_delivered_order(session, order_setup)

    return ReportingSetup(
        tenant_id=tenant_id,
        accounts=accounts,
        cash_position=cash,
        ar_total=ar,
        ap_total=ap,
        wip_value=wip,
        inventory_value=inventory_value,
        open_sales_count=1,
        open_sales_total=open_sales_total,
        open_po_count=1,
        open_po_total=open_po_total,
        otd_on_time=1,
        otd_total=1,
        as_of=_AS_OF,
    )


async def seed_on_hand_at_cost(
    session: AsyncSession, order_setup, *, quantity: str, unit_cost: str
) -> None:
    """Seed on-hand stock at a specific unit cost so inventory value is deterministic (D-025)."""
    from tests.modules.inventory.factories import build_stock

    await build_stock(
        session,
        order_setup.tenant_id,
        order_setup.item_id,
        order_setup.bin_id,
        Decimal(quantity),
        unit_cost=Decimal(unit_cost),
    )
